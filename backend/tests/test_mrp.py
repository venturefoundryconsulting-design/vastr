"""MRP - aggregated multi-order requirement planning.

Stateless: every test proves a *computed* answer, and several assert that
nothing was written anywhere except the one explicit draft-PO action.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.models.inventory import MovementType
from app.models.product import ItemType
from app.models.production import ProductionStatus
from app.models.purchase import PurchaseOrderStatus
from app.models.vendor import Vendor, VendorItem
from app.services import material_flow as mf
from app.services import mrp
from app.services.inventory import apply_stock_delta
from tests.test_production_orders import make_bom, make_item, make_order


_counter = iter(range(10000))


def released(db, item, version, qty, outlet):
    order = make_order(db, item, version, qty, outlet)
    order.po_number = f"{order.po_number}-{next(_counter)}"  # keep fixture calls unique
    order.status = ProductionStatus.RELEASED
    db.flush()
    return order


@pytest.fixture()
def lace(db, tenant):
    return make_item(db, "LAC-MRP", "Gold Lace", stock_uom="M", cost="120")


@pytest.fixture()
def garment(db, tenant):
    return make_item(db, "GAR-MRP", "Lehenga", stock_uom="PC", item_type=ItemType.FINISHED_PRODUCT)


def test_no_open_orders_means_no_requirements(db, tenant):
    assert mrp.requirements(db) == []


def test_a_released_order_shows_up_as_demand(db, tenant, warehouse, garment, lace):
    v = make_bom(db, garment, [(lace, "8", "M", 0)])
    released(db, garment, v, 1, warehouse)
    rows = mrp.requirements(db)
    assert len(rows) == 1
    assert rows[0]["sku"] == "LAC-MRP"
    assert rows[0]["required"] == Decimal("8")


def test_draft_and_planned_orders_are_not_demand(db, tenant, warehouse, garment, lace):
    """A DRAFT order is a plan nobody committed to - MRP must not count it."""
    v = make_bom(db, garment, [(lace, "8", "M", 0)])
    make_order(db, garment, v, 1, warehouse)  # stays DRAFT
    assert mrp.requirements(db) == []


def test_completed_and_cancelled_orders_are_not_demand(db, tenant, warehouse, garment, lace):
    v = make_bom(db, garment, [(lace, "8", "M", 0)])
    done = released(db, garment, v, 1, warehouse)
    done.status = ProductionStatus.COMPLETED
    cancelled = released(db, garment, v, 1, warehouse)
    cancelled.status = ProductionStatus.CANCELLED
    db.flush()
    assert mrp.requirements(db) == []


def test_two_orders_for_the_same_material_are_aggregated(db, tenant, warehouse, garment, lace):
    """The brief's shape: two production orders both needing the same lace."""
    v = make_bom(db, garment, [(lace, "8", "M", 0)])
    a = released(db, garment, v, 1, warehouse)
    b = released(db, garment, v, 1, warehouse)
    rows = mrp.requirements(db)
    assert len(rows) == 1
    assert rows[0]["required"] == Decimal("16")
    order_ids = {o["production_order_id"] for o in rows[0]["contributing_orders"]}
    assert order_ids == {a.id, b.id}


def test_already_issued_material_reduces_outstanding_demand(db, tenant, warehouse, garment, lace):
    """Required 8, already issued 5 - only 3 is still outstanding demand."""
    apply_stock_delta(db, variant_id=lace.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("20"), movement_type=MovementType.OPENING_STOCK)
    db.flush()
    v = make_bom(db, garment, [(lace, "8", "M", 0)])
    order = released(db, garment, v, 1, warehouse)
    m = next(x for x in order.materials if not x.is_subassembly)
    mf.reserve(db, order, m.id, Decimal("5"))
    db.flush()
    mf.issue(db, order, m.id, Decimal("5"))
    db.flush()

    rows = mrp.requirements(db)
    assert rows[0]["required"] == Decimal("3")


def test_available_nets_on_hand_against_reserved(db, tenant, warehouse, garment, lace):
    """20 on hand, 15 reserved to some order -> only 5 truly available."""
    apply_stock_delta(db, variant_id=lace.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("20"), movement_type=MovementType.OPENING_STOCK)
    db.flush()
    v = make_bom(db, garment, [(lace, "30", "M", 0)])
    order = released(db, garment, v, 1, warehouse)
    m = next(x for x in order.materials if not x.is_subassembly)
    mf.reserve(db, order, m.id, Decimal("15"))
    db.flush()

    rows = mrp.requirements(db)
    row = rows[0]
    assert row["on_hand"] == Decimal("20")
    assert row["reserved"] == Decimal("15")
    assert row["available"] == Decimal("5")
    assert row["shortage"] == Decimal("25")  # 30 required - 5 available


def test_no_shortage_when_stock_covers_demand(db, tenant, warehouse, garment, lace):
    apply_stock_delta(db, variant_id=lace.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("50"), movement_type=MovementType.OPENING_STOCK)
    db.flush()
    v = make_bom(db, garment, [(lace, "8", "M", 0)])
    released(db, garment, v, 1, warehouse)
    row = mrp.requirements(db)[0]
    assert row["shortage"] == Decimal("0")
    assert row["suggested_purchase_qty"] == Decimal("0")


def test_suggestion_rounds_up_to_vendor_minimum_order(db, tenant, warehouse, garment, lace):
    """Short by 3, but the preferred vendor's MOQ is 10 - suggest 10, not 3."""
    v = make_bom(db, garment, [(lace, "8", "M", 0)])
    released(db, garment, v, 1, warehouse)
    vendor = Vendor(name="Lace Co")
    db.add(vendor)
    db.flush()
    db.add(VendorItem(vendor_id=vendor.id, variant_id=lace.id, is_preferred=True,
                      min_order_qty=Decimal("10"), cost_price=Decimal("120")))
    db.flush()

    row = mrp.requirements(db)[0]
    assert row["shortage"] == Decimal("8")
    assert row["suggested_purchase_qty"] == Decimal("10")
    assert row["preferred_vendor_name"] == "Lace Co"


def test_suggestion_ignores_moq_when_it_is_smaller_than_the_shortage(db, tenant, warehouse, garment, lace):
    v = make_bom(db, garment, [(lace, "50", "M", 0)])
    released(db, garment, v, 1, warehouse)
    vendor = Vendor(name="Lace Co 2")
    db.add(vendor)
    db.flush()
    db.add(VendorItem(vendor_id=vendor.id, variant_id=lace.id, is_preferred=True,
                      min_order_qty=Decimal("10")))
    db.flush()
    row = mrp.requirements(db)[0]
    assert row["suggested_purchase_qty"] == Decimal("50")


def test_sub_assembly_lines_are_excluded_from_demand(db, tenant, warehouse, garment, lace):
    """Only raw materials count - the sub-assembly itself is not something to buy."""
    panel = make_item(db, "SEMI-MRP", "Panel", stock_uom="PC", item_type=ItemType.SEMI_FINISHED)
    make_bom(db, panel, [(lace, "2", "M", 0)])
    v = make_bom(db, garment, [(panel, "1", "PC", 0)])
    released(db, garment, v, 3, warehouse)

    rows = mrp.requirements(db)
    skus = {r["sku"] for r in rows}
    assert "SEMI-MRP" not in skus
    assert "LAC-MRP" in skus


def test_decimal_requirements_are_exact(db, tenant, warehouse, garment, lace):
    v = make_bom(db, garment, [(lace, "4.5", "M", 0)])
    released(db, garment, v, "0.3333", warehouse)
    row = mrp.requirements(db)[0]
    from app.core.money import quantity as q
    assert row["required"] == q(Decimal("4.5") * Decimal("0.3333"))


# --------------------------------------------------------------- draft PO


def test_generate_draft_po_is_a_real_draft_never_sent(db, tenant, warehouse, garment, lace):
    v = make_bom(db, garment, [(lace, "8", "M", 0)])
    released(db, garment, v, 1, warehouse)
    vendor = Vendor(name="Lace Co 3")
    db.add(vendor)
    db.flush()
    db.add(VendorItem(vendor_id=vendor.id, variant_id=lace.id, is_preferred=True))
    db.flush()

    created = mrp.generate_draft_purchase_orders(db, outlet_id=warehouse.id)
    assert len(created) == 1
    po = created[0]
    assert po.status == PurchaseOrderStatus.DRAFT
    assert po.vendor_id == vendor.id
    assert po.items[0].quantity_ordered == Decimal("8")


def test_generating_a_draft_po_touches_no_inventory(db, tenant, warehouse, garment, lace):
    """MRP must never move stock, even when it writes a purchase order."""
    v = make_bom(db, garment, [(lace, "8", "M", 0)])
    released(db, garment, v, 1, warehouse)
    vendor = Vendor(name="Lace Co 4")
    db.add(vendor)
    db.flush()
    db.add(VendorItem(vendor_id=vendor.id, variant_id=lace.id, is_preferred=True))
    db.flush()

    before_levels = db.execute(sa.text("SELECT count(*) FROM stock_levels")).scalar_one()
    before_moves = db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one()
    mrp.generate_draft_purchase_orders(db, outlet_id=warehouse.id)
    db.flush()
    assert db.execute(sa.text("SELECT count(*) FROM stock_levels")).scalar_one() == before_levels
    assert db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one() == before_moves


def test_multiple_vendors_produce_multiple_draft_pos(db, tenant, warehouse, garment):
    silk = make_item(db, "FAB-MRP", "Silk", stock_uom="M", cost="800")
    lace2 = make_item(db, "LAC-MRP2", "Lace", stock_uom="M", cost="120")
    v = make_bom(db, garment, [(silk, "4.5", "M", 0), (lace2, "8", "M", 0)])
    released(db, garment, v, 1, warehouse)

    va, vb = Vendor(name="Silk Co"), Vendor(name="Lace Co 5")
    db.add_all([va, vb])
    db.flush()
    db.add(VendorItem(vendor_id=va.id, variant_id=silk.id, is_preferred=True))
    db.add(VendorItem(vendor_id=vb.id, variant_id=lace2.id, is_preferred=True))
    db.flush()

    created = mrp.generate_draft_purchase_orders(db, outlet_id=warehouse.id)
    assert len(created) == 2
    assert {po.vendor_id for po in created} == {va.id, vb.id}


def test_generate_refuses_when_nothing_is_short(db, tenant, warehouse, garment, lace):
    apply_stock_delta(db, variant_id=lace.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("50"), movement_type=MovementType.OPENING_STOCK)
    db.flush()
    v = make_bom(db, garment, [(lace, "8", "M", 0)])
    released(db, garment, v, 1, warehouse)
    with pytest.raises(mrp.MrpError, match="Nothing is currently short"):
        mrp.generate_draft_purchase_orders(db, outlet_id=warehouse.id)


def test_generate_refuses_items_with_no_preferred_vendor(db, tenant, warehouse, garment, lace):
    v = make_bom(db, garment, [(lace, "8", "M", 0)])
    released(db, garment, v, 1, warehouse)
    with pytest.raises(mrp.MrpError, match="no preferred vendor"):
        mrp.generate_draft_purchase_orders(db, outlet_id=warehouse.id)
