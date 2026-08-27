"""Phase 5 - goods receipts and purchase returns.

Rule 2 made auditable: PURCHASE_RECEIPT is written only by
services.goods_receipt.post_receipt, and every posting is tied to a real
document with a date and a receiver.
"""

import threading
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from app.core.tenant_context import tenant_scope
from app.models.goods_receipt import (
    GoodsReceipt,
    GoodsReceiptItem,
    PurchaseReturn,
    PurchaseReturnItem,
    ReceiptStatus,
)
from app.models.inventory import MovementType, StockLevel
from app.models.outlet import Outlet
from app.models.product import Item, ItemType
from app.models.tenant import Tenant
from app.models.uom import ItemUomConversion, UnitOfMeasure, UomCategory
from app.models.purchase import PurchaseOrder, PurchaseOrderItem, PurchaseOrderStatus
from app.models.vendor import Vendor
from app.services import goods_receipt as gr
from app.services.inventory import apply_stock_delta
from tests.conftest import stock_of
from tests.test_ledger_integrity import assert_ledger_reconciles
from tests.test_production_orders import make_item, uom


@pytest.fixture()
def vendor(db, tenant):
    v = Vendor(name="Deepa Textiles")
    db.add(v)
    db.flush()
    return v


@pytest.fixture()
def lace(db, tenant):
    """Stocked in metres, purchased in rolls - 1 roll = 25 m for this vendor."""
    item = make_item(db, "LAC-P5", "Gold Lace", stock_uom="M", cost="0")
    db.flush()
    db.add(ItemUomConversion(
        item_id=item.id, from_uom_id=uom(db, "ROLL").id, to_uom_id=uom(db, "M").id,
        factor=Decimal("25"),
    ))
    db.flush()
    return item


def make_receipt(db, outlet, lines, *, vendor_id=None, po_id=None) -> GoodsReceipt:
    r = GoodsReceipt(
        receipt_number=f"GRN-TEST-{outlet.id}-{len(lines)}", vendor_id=vendor_id,
        purchase_order_id=po_id, outlet_id=outlet.id, status=ReceiptStatus.DRAFT,
    )
    db.add(r)
    db.flush()
    for item, qty, uom_id, cost, po_item_id in lines:
        db.add(GoodsReceiptItem(
            goods_receipt_id=r.id, item_id=item.id, quantity=Decimal(str(qty)),
            uom_id=uom_id, quantity_in_stock_uom=Decimal(str(qty)),
            unit_cost=Decimal(str(cost)), purchase_order_item_id=po_item_id,
        ))
    db.flush()
    db.refresh(r)
    return r


# ------------------------------------------------------------------- posting


def test_posting_moves_stock_and_writes_one_movement(db, tenant, warehouse, vendor):
    fabric = make_item(db, "FAB-P5", "Silk", stock_uom="M", cost="0")
    r = make_receipt(db, warehouse, [(fabric, "20", None, "800", None)], vendor_id=vendor.id)
    before = db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one()

    gr.post_receipt(db, r)
    db.flush()

    after = db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one()
    assert after == before + 1
    assert stock_of(db, fabric.id, warehouse.id) == Decimal("20.0000")
    assert r.status == ReceiptStatus.POSTED
    assert r.posted_at is not None
    kind = db.execute(sa.text(
        "SELECT movement_type, unit_cost FROM stock_movements WHERE id = :i"
    ), {"i": r.items[0].stock_movement_id}).one()
    assert kind.movement_type == "PURCHASE_RECEIPT"
    assert kind.unit_cost == Decimal("800.0000")
    assert_ledger_reconciles(db)


def test_a_draft_receipt_touches_no_stock(db, tenant, warehouse, vendor):
    fabric = make_item(db, "FAB-P5B", "Silk", stock_uom="M", cost="0")
    make_receipt(db, warehouse, [(fabric, "20", None, "800", None)], vendor_id=vendor.id)
    assert stock_of(db, fabric.id, warehouse.id) == Decimal("0")


def test_posting_twice_is_refused(db, tenant, warehouse, vendor):
    fabric = make_item(db, "FAB-P5C", "Silk", stock_uom="M", cost="0")
    r = make_receipt(db, warehouse, [(fabric, "5", None, "800", None)], vendor_id=vendor.id)
    gr.post_receipt(db, r)
    db.flush()
    with pytest.raises(gr.GoodsReceiptError, match="already been posted"):
        gr.post_receipt(db, r)


def test_empty_receipt_cannot_be_posted(db, tenant, warehouse):
    r = GoodsReceipt(receipt_number="GRN-EMPTY", outlet_id=warehouse.id, status=ReceiptStatus.DRAFT)
    db.add(r)
    db.flush()
    with pytest.raises(gr.GoodsReceiptError, match="at least one line"):
        gr.post_receipt(db, r)


# --------------------------------------------------------------- UoM on receipt


def test_roll_receipt_lands_in_metres(db, tenant, warehouse, vendor, lace):
    """The brief's worked example: 2 ROLL of lace = 50 m of stock."""
    r = make_receipt(
        db, warehouse, [(lace, "2", uom(db, "ROLL").id, "3000", None)], vendor_id=vendor.id
    )
    gr.post_receipt(db, r)
    db.flush()
    assert stock_of(db, lace.id, warehouse.id) == Decimal("50.0000")
    assert r.items[0].quantity_in_stock_uom == Decimal("50.0000")
    # 3000 per roll / 25 m per roll = 120 per metre.
    assert r.items[0].stock_movement_id is not None
    unit_cost = db.execute(sa.text(
        "SELECT unit_cost FROM stock_movements WHERE id = :i"
    ), {"i": r.items[0].stock_movement_id}).scalar_one()
    assert unit_cost == Decimal("120.0000")


def test_receiving_in_an_unconvertible_unit_is_refused(db, tenant, warehouse, vendor):
    """A garment stocked in pieces cannot be received in metres."""
    garment = make_item(db, "GAR-P5", "Kurti", stock_uom="PC", cost="0",
                        item_type=ItemType.FINISHED_PRODUCT)
    r = make_receipt(
        db, warehouse, [(garment, "5", uom(db, "M").id, "500", None)], vendor_id=vendor.id
    )
    with pytest.raises(gr.GoodsReceiptError, match="different things"):
        gr.post_receipt(db, r)


# --------------------------------------------------------------- weighted cost


def test_weighted_average_cost_updates_on_receipt(db, tenant, warehouse, vendor):
    """10 @ 100 already on hand; receive 10 @ 200 -> average 150."""
    fabric = make_item(db, "FAB-P5D", "Silk", stock_uom="M", cost="100")
    apply_stock_delta(db, variant_id=fabric.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("10"), movement_type=MovementType.OPENING_STOCK)
    db.flush()
    r = make_receipt(db, warehouse, [(fabric, "10", None, "200", None)], vendor_id=vendor.id)
    gr.post_receipt(db, r)
    db.flush()
    assert fabric.cost_price == Decimal("150.00")


def test_cost_stays_put_when_nothing_is_on_hand_yet(db, tenant, warehouse, vendor):
    fabric = make_item(db, "FAB-P5E", "Silk", stock_uom="M", cost="0")
    r = make_receipt(db, warehouse, [(fabric, "10", None, "350", None)], vendor_id=vendor.id)
    gr.post_receipt(db, r)
    db.flush()
    assert fabric.cost_price == Decimal("350.00")


# ------------------------------------------------------------ PO integration


def test_receipt_against_a_po_advances_quantity_received(db, tenant, warehouse, vendor):
    fabric = make_item(db, "FAB-P5F", "Silk", stock_uom="M", cost="0")
    po = PurchaseOrder(po_number="PO-P5", vendor_id=vendor.id, outlet_id=warehouse.id,
                       status=PurchaseOrderStatus.SENT,
                       order_date=datetime.now(timezone.utc))
    db.add(po)
    db.flush()
    po_item = PurchaseOrderItem(purchase_order_id=po.id, variant_id=fabric.id,
                                quantity_ordered=Decimal("20"), unit_cost=Decimal("800"))
    db.add(po_item)
    db.flush()

    receipt = gr.build_from_purchase_order(
        db, po, [{"purchase_order_item_id": po_item.id, "quantity": Decimal("20")}],
        receipt_number="GRN-PO-P5",
    )
    gr.post_receipt(db, receipt)
    db.flush()

    assert po_item.quantity_received == Decimal("20.0000")
    assert po.status == PurchaseOrderStatus.RECEIVED
    assert stock_of(db, fabric.id, warehouse.id) == Decimal("20.0000")


def test_partial_receipt_leaves_the_po_partially_received(db, tenant, warehouse, vendor):
    fabric = make_item(db, "FAB-P5G", "Silk", stock_uom="M", cost="0")
    po = PurchaseOrder(po_number="PO-P5B", vendor_id=vendor.id, outlet_id=warehouse.id,
                       status=PurchaseOrderStatus.SENT,
                       order_date=datetime.now(timezone.utc))
    db.add(po)
    db.flush()
    po_item = PurchaseOrderItem(purchase_order_id=po.id, variant_id=fabric.id,
                                quantity_ordered=Decimal("20"), unit_cost=Decimal("800"))
    db.add(po_item)
    db.flush()

    receipt = gr.build_from_purchase_order(
        db, po, [{"purchase_order_item_id": po_item.id, "quantity": Decimal("12")}],
        receipt_number="GRN-PO-P5B",
    )
    gr.post_receipt(db, receipt)
    db.flush()
    assert po.status == PurchaseOrderStatus.PARTIALLY_RECEIVED
    assert po_item.quantity_received == Decimal("12.0000")


def test_receiving_beyond_what_was_ordered_is_refused(db, tenant, warehouse, vendor):
    fabric = make_item(db, "FAB-P5H", "Silk", stock_uom="M", cost="0")
    po = PurchaseOrder(po_number="PO-P5C", vendor_id=vendor.id, outlet_id=warehouse.id,
                       status=PurchaseOrderStatus.SENT,
                       order_date=datetime.now(timezone.utc))
    db.add(po)
    db.flush()
    po_item = PurchaseOrderItem(purchase_order_id=po.id, variant_id=fabric.id,
                                quantity_ordered=Decimal("20"), unit_cost=Decimal("800"))
    db.add(po_item)
    db.flush()

    receipt = gr.build_from_purchase_order(
        db, po, [{"purchase_order_item_id": po_item.id, "quantity": Decimal("25")}],
        receipt_number="GRN-PO-P5D",
    )
    with pytest.raises(gr.GoodsReceiptError, match="exceeds the 20"):
        gr.post_receipt(db, receipt)


# -------------------------------------------------------------- purchase returns


def test_purchase_return_writes_a_compensating_movement(db, tenant, warehouse, vendor):
    """The original receipt is never edited - a return is a new, negative row."""
    fabric = make_item(db, "FAB-P5I", "Silk", stock_uom="M", cost="0")
    r = make_receipt(db, warehouse, [(fabric, "100", None, "800", None)], vendor_id=vendor.id)
    gr.post_receipt(db, r)
    db.flush()
    original_qty = r.items[0].quantity

    ret = PurchaseReturn(return_number="PRET-P5", goods_receipt_id=r.id, vendor_id=vendor.id,
                         outlet_id=warehouse.id)
    db.add(ret)
    db.flush()
    db.add(PurchaseReturnItem(purchase_return_id=ret.id, goods_receipt_item_id=r.items[0].id,
                              item_id=fabric.id, quantity=Decimal("10"), unit_cost=Decimal("800")))
    db.flush()

    gr.post_return(db, ret)
    db.flush()

    assert stock_of(db, fabric.id, warehouse.id) == Decimal("90.0000")
    assert r.items[0].quantity == original_qty  # untouched
    kind = db.execute(sa.text(
        "SELECT movement_type FROM stock_movements WHERE id = :i"
    ), {"i": ret.items[0].stock_movement_id}).scalar_one()
    assert kind == "PURCHASE_RETURN"
    assert_ledger_reconciles(db)


def test_return_cannot_exceed_what_was_received(db, tenant, warehouse, vendor):
    fabric = make_item(db, "FAB-P5J", "Silk", stock_uom="M", cost="0")
    r = make_receipt(db, warehouse, [(fabric, "10", None, "800", None)], vendor_id=vendor.id)
    gr.post_receipt(db, r)
    db.flush()

    ret = PurchaseReturn(return_number="PRET-P5B", goods_receipt_id=r.id, outlet_id=warehouse.id)
    db.add(ret)
    db.flush()
    db.add(PurchaseReturnItem(purchase_return_id=ret.id, goods_receipt_item_id=r.items[0].id,
                              item_id=fabric.id, quantity=Decimal("15")))
    db.flush()
    with pytest.raises(gr.GoodsReceiptError, match="at most 10"):
        gr.post_return(db, ret)


def test_return_cannot_exceed_physical_stock(db, tenant, warehouse, vendor):
    """Received 10, but 8 were already sold - only 2 can physically go back."""
    fabric = make_item(db, "FAB-P5K", "Silk", stock_uom="M", cost="0")
    r = make_receipt(db, warehouse, [(fabric, "10", None, "800", None)], vendor_id=vendor.id)
    gr.post_receipt(db, r)
    db.flush()
    apply_stock_delta(db, variant_id=fabric.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("-8"), movement_type=MovementType.SALE)
    db.flush()

    ret = PurchaseReturn(return_number="PRET-P5C", goods_receipt_id=r.id, outlet_id=warehouse.id)
    db.add(ret)
    db.flush()
    db.add(PurchaseReturnItem(purchase_return_id=ret.id, goods_receipt_item_id=r.items[0].id,
                              item_id=fabric.id, quantity=Decimal("5")))
    db.flush()
    with pytest.raises(gr.GoodsReceiptError, match="only 2"):
        gr.post_return(db, ret)


def test_multiple_partial_returns_accumulate_against_the_limit(db, tenant, warehouse, vendor):
    fabric = make_item(db, "FAB-P5L", "Silk", stock_uom="M", cost="0")
    r = make_receipt(db, warehouse, [(fabric, "20", None, "800", None)], vendor_id=vendor.id)
    gr.post_receipt(db, r)
    db.flush()

    def do_return(qty):
        ret = PurchaseReturn(return_number=f"PRET-{qty}", goods_receipt_id=r.id, outlet_id=warehouse.id)
        db.add(ret)
        db.flush()
        db.add(PurchaseReturnItem(purchase_return_id=ret.id, goods_receipt_item_id=r.items[0].id,
                                  item_id=fabric.id, quantity=Decimal(str(qty))))
        db.flush()
        gr.post_return(db, ret)
        db.flush()

    do_return(6)
    do_return(4)
    assert gr.returnable(db, r.items[0]) == Decimal("10")
    with pytest.raises(gr.GoodsReceiptError):
        do_return(11)


# -------------------------------------------------------------------- decimal


@pytest.mark.parametrize("qty", ["4.5", "0.125", "12.75"])
def test_decimal_quantities_are_exact(db, tenant, warehouse, vendor, qty):
    fabric = make_item(db, f"FAB-DEC-{qty}", "Silk", stock_uom="M", cost="0")
    r = make_receipt(db, warehouse, [(fabric, qty, None, "800", None)], vendor_id=vendor.id)
    gr.post_receipt(db, r)
    db.flush()
    assert stock_of(db, fabric.id, warehouse.id) == Decimal(qty)


# ---------------------------------------------------------------- atomicity


def test_failed_posting_rolls_back_completely(db, tenant, warehouse, vendor):
    fabric = make_item(db, "FAB-P5M", "Silk", stock_uom="M", cost="0")
    r = make_receipt(db, warehouse, [(fabric, "10", None, "800", None)], vendor_id=vendor.id)
    before_moves = db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one()

    sp = db.begin_nested()
    try:
        gr.post_receipt(db, r)
        raise RuntimeError("simulated failure after the ledger row")
    except RuntimeError:
        sp.rollback()

    assert stock_of(db, fabric.id, warehouse.id) == Decimal("0")
    assert db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one() == before_moves
    assert_ledger_reconciles(db)


# ------------------------------------------------------------ concurrency
#
# Phase 10 hardening. post_receipt() reads Item.cost_price, recomputes the
# weighted average, then writes it back - a classic lost-update shape if two
# receipts for the same item land at once. It is only safe because
# get_or_create_stock_level() takes the stock_levels row lock *before* that
# read, serializing the two postings on the same row. This test proves it on
# real threads and real connections rather than trusting the ordering by
# inspection - a mocked lock would prove nothing about the actual DB.
#
# The assertion works regardless of which posting wins the race: weighted
# average is path-independent when each step correctly sees the other's
# result, so 10 @ 100 (opening) + 5 @ 200 + 5 @ 300, in EITHER order, must
# land on exactly (1000 + 1000 + 1500) / 20 = 175. A lost update (one
# posting working off a stale on-hand/cost pair) would not land on 175.

_GR_TENANT_SEQ = iter(range(9700, 9800))


def test_concurrent_receipts_do_not_lose_a_cost_update(_database):
    tenant_id = next(_GR_TENANT_SEQ)
    Session = sessionmaker(bind=_database)
    s = Session()
    s.execute(sa.text("SET LOCAL lock_timeout = '10s'"))
    with tenant_scope(tenant_id):
        s.add(Tenant(id=tenant_id, company_name="GR Co", slug=f"gr-co-{tenant_id}"))
        s.flush()
        outlet = Outlet(name="GR Store", code="GRS")
        s.add(outlet)
        category = UomCategory(code="LENGTH", name="Length")
        s.add(category)
        s.flush()
        metre = UnitOfMeasure(code="M", name="Meter", category_id=category.id,
                              factor_to_base=Decimal("1"), is_base=True)
        s.add(metre)
        s.flush()
        item = Item(sku=f"GR-RACE-{tenant_id}", name="GR Race Fabric",
                    item_type=ItemType.RAW_MATERIAL, stock_uom_id=metre.id,
                    cost_price=Decimal("100"))
        s.add(item)
        s.flush()
        s.add(StockLevel(variant_id=item.id, outlet_id=outlet.id, quantity=Decimal("10")))
        from app.models.inventory import StockMovement
        s.add(StockMovement(variant_id=item.id, outlet_id=outlet.id,
                            movement_type=MovementType.OPENING_STOCK,
                            quantity_delta=Decimal("10"), unit_cost=Decimal("100")))
        s.commit()
        item_id, outlet_id, metre_id = item.id, outlet.id, metre.id
    s.close()

    def worker(cost):
        s = Session()
        try:
            s.execute(sa.text("SET LOCAL lock_timeout = '10s'"))
            with tenant_scope(tenant_id):
                r = GoodsReceipt(
                    receipt_number=f"GRN-RACE-{tenant_id}-{cost}", outlet_id=outlet_id,
                    status=ReceiptStatus.DRAFT,
                )
                s.add(r)
                s.flush()
                s.add(GoodsReceiptItem(
                    goods_receipt_id=r.id, item_id=item_id, quantity=Decimal("5"),
                    uom_id=metre_id, quantity_in_stock_uom=Decimal("5"),
                    unit_cost=Decimal(cost),
                ))
                s.flush()
                s.refresh(r)
                gr.post_receipt(s, r)
                s.commit()
        finally:
            s.close()

    threads = [threading.Thread(target=worker, args=(c,)) for c in ("200", "300")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    s = Session()
    try:
        with tenant_scope(tenant_id):
            level = s.query(StockLevel).filter(
                StockLevel.variant_id == item_id, StockLevel.outlet_id == outlet_id
            ).first()
            item = s.get(Item, item_id)
            replay = s.execute(sa.text(
                "SELECT coalesce(sum(quantity_delta),0) FROM stock_movements WHERE variant_id = :i"
            ), {"i": item_id}).scalar_one()

        assert level.quantity == Decimal("20"), f"expected 20 on hand, got {level.quantity}"
        assert level.quantity == replay, "ledger and cached stock disagree after concurrent receipts"
        assert item.cost_price == Decimal("175.0000"), (
            f"expected weighted average 175 regardless of posting order, got {item.cost_price} - "
            "a lost update means one receipt's cost recalculation overwrote the other's"
        )
    finally:
        with tenant_scope(None):
            for stmt, params in (
                ("DELETE FROM goods_receipt_items WHERE goods_receipt_id IN "
                 "(SELECT id FROM goods_receipts WHERE tenant_id = :t)", {"t": tenant_id}),
                ("DELETE FROM goods_receipts WHERE tenant_id = :t", {"t": tenant_id}),
                ("DELETE FROM stock_movements WHERE variant_id = :i", {"i": item_id}),
                ("DELETE FROM stock_levels WHERE variant_id = :i", {"i": item_id}),
                ("DELETE FROM items WHERE tenant_id = :t", {"t": tenant_id}),
                ("DELETE FROM units_of_measure WHERE tenant_id = :t", {"t": tenant_id}),
                ("DELETE FROM uom_categories WHERE tenant_id = :t", {"t": tenant_id}),
                ("DELETE FROM outlets WHERE tenant_id = :t", {"t": tenant_id}),
                ("DELETE FROM tenants WHERE id = :t", {"t": tenant_id}),
            ):
                s.execute(sa.text(stmt), params)
            s.commit()
        s.close()
