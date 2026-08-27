"""Phase 4 - measurements, made-to-order customer orders, POS integration."""

from datetime import date
from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.models.inventory import MovementType
from app.models.made_to_order import (
    CustomerOrder,
    CustomerOrderItem,
    CustomerOrderStatus,
    Fulfilment,
    MeasurementField,
    MeasurementProfile,
    MeasurementValue,
)
from app.models.product import ItemType
from app.models.production import ProductionStatus
from app.services import made_to_order as mto
from app.services import production as prod
from app.services.inventory import apply_stock_delta
from tests.conftest import stock_of
from tests.test_ledger_integrity import assert_ledger_reconciles
from tests.test_production_orders import make_bom, make_item


def field(db, code: str) -> MeasurementField:
    return db.query(MeasurementField).filter(MeasurementField.code == code).one()


@pytest.fixture()
def catalogue(db, tenant, warehouse):
    """A garment with an active BOM, and material in stock to make it."""
    silk = make_item(db, "FAB-P4", "Silk", stock_uom="M", cost="800")
    apply_stock_delta(db, variant_id=silk.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("500"), movement_type=MovementType.OPENING_STOCK)
    db.flush()
    lehenga = make_item(db, "GAR-P4", "Bridal Lehenga", stock_uom="PC",
                        item_type=ItemType.FINISHED_PRODUCT)
    make_bom(db, lehenga, [(silk, "4.5", "M", 0)])
    dupatta = make_item(db, "DUP-P4", "Chiffon Dupatta", stock_uom="PC",
                        item_type=ItemType.FINISHED_PRODUCT)
    apply_stock_delta(db, variant_id=dupatta.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("5"), movement_type=MovementType.OPENING_STOCK)
    db.flush()
    return silk, lehenga, dupatta, warehouse


def make_order(db, customer, outlet, lines, advance="0"):
    o = CustomerOrder(
        order_number=f"CO-TEST-{customer.id}-{len(lines)}",
        customer_id=customer.id, outlet_id=outlet.id, order_date=date.today(),
        advance_amount=Decimal(advance), status=CustomerOrderStatus.DRAFT,
    )
    db.add(o)
    db.flush()
    for item, qty, price, ful in lines:
        db.add(CustomerOrderItem(
            customer_order_id=o.id, item_id=item.id, quantity=Decimal(str(qty)),
            unit_price=Decimal(str(price)), fulfilment=ful,
        ))
    db.flush()
    db.refresh(o)
    return o


# ------------------------------------------------------------- measurements


def test_measurement_fields_are_seeded_as_data(db, tenant):
    """Bust, waist, hip and the rest are rows - not columns, not an enum."""
    codes = {f.code for f in db.query(MeasurementField).all()}
    assert {"BUST", "WAIST", "HIP", "SHOULDER", "SLEEVE_LENGTH", "BLOUSE_LENGTH"} <= codes


def test_a_boutique_can_add_its_own_measurement(db, tenant):
    db.add(MeasurementField(code="CALF", name="Calf", sequence=200, group_name="Lower body"))
    db.flush()
    assert field(db, "CALF").name == "Calf"


def test_a_customer_can_hold_several_profiles(db, tenant, customer):
    """One person is not one set of numbers - blouse and lehenga differ."""
    for name in ("Blouse", "Lehenga"):
        p = MeasurementProfile(customer_id=customer.id, name=name)
        db.add(p)
        db.flush()
        db.add(MeasurementValue(profile_id=p.id, field_id=field(db, "WAIST").id,
                                value=Decimal("30.5")))
    db.flush()
    assert db.query(MeasurementProfile).filter(
        MeasurementProfile.customer_id == customer.id
    ).count() == 2


def test_measurements_are_numeric_and_comparable(db, tenant, customer):
    """Stored as numbers so a tailor can see how a customer has changed."""
    old = MeasurementProfile(customer_id=customer.id, name="2025")
    new = MeasurementProfile(customer_id=customer.id, name="2026")
    db.add_all([old, new])
    db.flush()
    db.add(MeasurementValue(profile_id=old.id, field_id=field(db, "WAIST").id, value=Decimal("30")))
    db.add(MeasurementValue(profile_id=new.id, field_id=field(db, "WAIST").id, value=Decimal("31.5")))
    db.flush()
    assert new.values[0].value - old.values[0].value == Decimal("1.5")


def test_a_measurement_cannot_be_zero_or_negative(db, tenant, customer):
    p = MeasurementProfile(customer_id=customer.id, name="Bad")
    db.add(p)
    db.flush()
    db.add(MeasurementValue(profile_id=p.id, field_id=field(db, "BUST").id, value=Decimal("0")))
    with pytest.raises(sa.exc.IntegrityError):
        db.flush()


# ---------------------------------------------------------- order & confirm


def test_ready_stock_and_made_to_order_coexist(db, catalogue, customer, tenant):
    """One visit, one order - a dupatta off the rack and a commissioned lehenga."""
    _, lehenga, dupatta, wh = catalogue
    o = make_order(db, customer, wh, [
        (dupatta, 1, 2000, Fulfilment.READY_STOCK),
        (lehenga, 1, 45000, Fulfilment.MADE_TO_ORDER),
    ])
    assert len(o.items) == 2
    assert o.has_made_to_order is True
    assert o.total_amount == Decimal("47000")


def test_confirm_spawns_production_only_for_made_to_order(db, catalogue, customer, tenant):
    _, lehenga, dupatta, wh = catalogue
    o = make_order(db, customer, wh, [
        (dupatta, 1, 2000, Fulfilment.READY_STOCK),
        (lehenga, 2, 45000, Fulfilment.MADE_TO_ORDER),
    ])
    spawned = mto.confirm(db, o)
    db.flush()

    assert len(spawned) == 1
    assert spawned[0].planned_quantity == Decimal("2")
    assert spawned[0].status == ProductionStatus.DRAFT   # not auto-released
    assert o.status == CustomerOrderStatus.IN_PRODUCTION

    lines = {i.item_id: i for i in o.items}
    assert lines[lehenga.id].production_order_id == spawned[0].id
    assert lines[dupatta.id].production_order_id is None


def test_confirmed_production_carries_the_bom_requirements(db, catalogue, customer, tenant):
    """The spawned order is a real production order, snapshot and all."""
    silk, lehenga, _, wh = catalogue
    o = make_order(db, customer, wh, [(lehenga, 2, 45000, Fulfilment.MADE_TO_ORDER)])
    po = mto.confirm(db, o)[0]
    db.flush()
    mats = {m.item_id: m for m in po.materials if not m.is_subassembly}
    assert mats[silk.id].planned_quantity == Decimal("9")   # 4.5 x 2


def test_ready_stock_only_order_skips_production(db, catalogue, customer, tenant):
    _, _, dupatta, wh = catalogue
    o = make_order(db, customer, wh, [(dupatta, 1, 2000, Fulfilment.READY_STOCK)])
    spawned = mto.confirm(db, o)
    db.flush()
    assert spawned == []
    assert o.status == CustomerOrderStatus.CONFIRMED


def test_made_to_order_needs_an_active_bom(db, catalogue, customer, tenant, warehouse):
    """Commissioning something with no recipe is refused, with a useful message."""
    nobom = make_item(db, "GAR-NOBOM", "Unplanned Garment", stock_uom="PC",
                      item_type=ItemType.FINISHED_PRODUCT)
    o = make_order(db, customer, warehouse, [(nobom, 1, 1000, Fulfilment.MADE_TO_ORDER)])
    with pytest.raises(mto.CustomerOrderError, match="no active bill of materials"):
        mto.confirm(db, o)


def test_confirming_twice_is_refused_not_silently_duplicated(db, catalogue, customer, tenant):
    """A double-click must not spawn a second production run. The state machine
    refuses it outright, which is clearer than a silent no-op."""
    _, lehenga, _, wh = catalogue
    o = make_order(db, customer, wh, [(lehenga, 1, 45000, Fulfilment.MADE_TO_ORDER)])
    first = mto.confirm(db, o)
    db.flush()
    assert len(first) == 1

    with pytest.raises(mto.InvalidCustomerOrderTransition):
        mto.confirm(db, o)

    # Still exactly one production order for this line.
    assert db.query(CustomerOrderItem).filter(
        CustomerOrderItem.customer_order_id == o.id,
        CustomerOrderItem.production_order_id.isnot(None),
    ).count() == 1


def test_empty_order_cannot_be_confirmed(db, customer, warehouse, tenant):
    o = make_order(db, customer, warehouse, [])
    with pytest.raises(mto.CustomerOrderError, match="at least one item"):
        mto.confirm(db, o)


# ---------------------------------------------------------------- readiness


def test_ready_stock_line_is_ready_when_stock_exists(db, catalogue, customer, tenant):
    _, _, dupatta, wh = catalogue
    o = make_order(db, customer, wh, [(dupatta, 2, 2000, Fulfilment.READY_STOCK)])
    state = mto.readiness(db, o)
    assert state["all_ready"] is True


def test_ready_stock_line_is_not_ready_without_stock(db, catalogue, customer, tenant):
    _, _, dupatta, wh = catalogue
    o = make_order(db, customer, wh, [(dupatta, 99, 2000, Fulfilment.READY_STOCK)])
    state = mto.readiness(db, o)
    assert state["all_ready"] is False
    assert "in stock" in state["lines"][0]["note"]


def test_made_to_order_line_waits_for_production(db, catalogue, customer, tenant):
    _, lehenga, _, wh = catalogue
    o = make_order(db, customer, wh, [(lehenga, 2, 45000, Fulfilment.MADE_TO_ORDER)])
    po = mto.confirm(db, o)[0]
    db.flush()

    assert mto.readiness(db, o)["all_ready"] is False

    po.status = ProductionStatus.IN_PROGRESS
    db.flush()
    prod.record_output(db, po, Decimal("1"))
    db.flush()
    assert mto.readiness(db, o)["all_ready"] is False   # 1 of 2

    prod.record_output(db, po, Decimal("1"))
    db.flush()
    db.refresh(o)
    assert mto.readiness(db, o)["all_ready"] is True


def test_mark_ready_refuses_while_something_is_outstanding(db, catalogue, customer, tenant):
    _, lehenga, _, wh = catalogue
    o = make_order(db, customer, wh, [(lehenga, 1, 45000, Fulfilment.MADE_TO_ORDER)])
    mto.confirm(db, o)
    db.flush()
    with pytest.raises(mto.CustomerOrderError, match="Not everything is ready"):
        mto.mark_ready(db, o)


# ------------------------------------------------- POS integration (delivery)


def test_delivery_sells_through_the_normal_pos_path(db, catalogue, customer, tenant, user):
    """The whole point: a made-to-order garment leaves stock exactly like any other.

    Production output puts the lehenga into inventory; delivery sells it with the
    same checkout the counter uses, producing an ordinary SALE ledger row.
    """
    from app.routers import made_to_order as mto_router
    from app.routers.made_to_order import DeliverRequest

    _, lehenga, dupatta, wh = catalogue
    o = make_order(db, customer, wh, [
        (dupatta, 1, 2000, Fulfilment.READY_STOCK),
        (lehenga, 1, 45000, Fulfilment.MADE_TO_ORDER),
    ], advance="10000")
    po = mto.confirm(db, o)[0]
    db.flush()
    po.status = ProductionStatus.IN_PROGRESS
    db.flush()
    prod.record_output(db, po, Decimal("1"))
    db.flush()
    db.refresh(o)
    mto.mark_ready(db, o)
    db.flush()

    lehenga_before = stock_of(db, lehenga.id, wh.id)
    dupatta_before = stock_of(db, dupatta.id, wh.id)

    result = mto_router.deliver_order(o.id, DeliverRequest(), db, user)

    assert result["status"] == CustomerOrderStatus.DELIVERED
    assert result["sale_id"] is not None
    # Both lines left stock - the commissioned one and the off-the-rack one.
    assert stock_of(db, lehenga.id, wh.id) == lehenga_before - Decimal("1")
    assert stock_of(db, dupatta.id, wh.id) == dupatta_before - Decimal("1")

    kinds = db.execute(sa.text(
        "SELECT DISTINCT movement_type FROM stock_movements WHERE variant_id = :v"
    ), {"v": lehenga.id}).scalars().all()
    assert "PRODUCTION_OUTPUT" in kinds and "SALE" in kinds
    assert_ledger_reconciles(db)


def test_advance_is_deducted_not_charged_twice(db, catalogue, customer, tenant, user):
    """A 10,000 advance on a 47,000 order leaves 37,000 to collect."""
    from app.models.sale import Sale
    from app.routers import made_to_order as mto_router
    from app.routers.made_to_order import DeliverRequest

    _, _, dupatta, wh = catalogue
    o = make_order(db, customer, wh, [(dupatta, 1, 2000, Fulfilment.READY_STOCK)],
                   advance="500")
    mto.confirm(db, o)
    db.flush()
    mto.mark_ready(db, o)
    db.flush()

    result = mto_router.deliver_order(o.id, DeliverRequest(), db, user)
    sale = db.get(Sale, result["sale_id"])
    assert sale.discount_amount == Decimal("500.00")
    assert sale.total == Decimal("1500.00")   # 2000 - 500 advance


def test_delivery_is_refused_before_ready(db, catalogue, customer, tenant, user):
    from fastapi import HTTPException

    from app.routers import made_to_order as mto_router
    from app.routers.made_to_order import DeliverRequest

    _, _, dupatta, wh = catalogue
    o = make_order(db, customer, wh, [(dupatta, 1, 2000, Fulfilment.READY_STOCK)])
    with pytest.raises(HTTPException) as exc:
        mto_router.deliver_order(o.id, DeliverRequest(), db, user)
    assert exc.value.status_code == 409


def test_delivery_refused_when_stock_vanished(db, catalogue, customer, tenant, user, warehouse):
    """Checkout's own stock validation is what protects the ledger."""
    from fastapi import HTTPException

    from app.routers import made_to_order as mto_router
    from app.routers.made_to_order import DeliverRequest

    _, _, dupatta, wh = catalogue
    o = make_order(db, customer, wh, [(dupatta, 2, 2000, Fulfilment.READY_STOCK)])
    mto.confirm(db, o)
    db.flush()
    mto.mark_ready(db, o)
    db.flush()
    apply_stock_delta(db, variant_id=dupatta.id, outlet_id=wh.id,
                      quantity_delta=Decimal("-5"), movement_type=MovementType.ADJUSTMENT)
    db.flush()

    with pytest.raises(HTTPException) as exc:
        mto_router.deliver_order(o.id, DeliverRequest(), db, user)
    assert exc.value.status_code == 400
    assert "Insufficient stock" in exc.value.detail
    db.rollback()


# ----------------------------------------------------------------- cancel


def test_cancelling_releases_the_production_it_spawned(db, catalogue, customer, tenant):
    """Rule 8 reaching through from the counter: a cancelled commission must not
    keep holding fabric."""
    _, lehenga, _, wh = catalogue
    o = make_order(db, customer, wh, [(lehenga, 1, 45000, Fulfilment.MADE_TO_ORDER)])
    po = mto.confirm(db, o)[0]
    db.flush()

    to_cancel = mto.cancel(db, o, "customer changed their mind")
    db.flush()
    assert o.status == CustomerOrderStatus.CANCELLED
    assert o.cancel_reason == "customer changed their mind"
    assert [p.id for p in to_cancel] == [po.id]


def test_delivered_order_is_terminal(db, catalogue, customer, tenant):
    _, _, dupatta, wh = catalogue
    o = make_order(db, customer, wh, [(dupatta, 1, 2000, Fulfilment.READY_STOCK)])
    o.status = CustomerOrderStatus.DELIVERED
    db.flush()
    with pytest.raises(mto.InvalidCustomerOrderTransition, match="final"):
        mto.cancel(db, o, "too late")


@pytest.mark.parametrize("frm,to", [
    (CustomerOrderStatus.DRAFT, CustomerOrderStatus.DELIVERED),   # cannot skip
    (CustomerOrderStatus.DRAFT, CustomerOrderStatus.READY),       # must confirm first
    (CustomerOrderStatus.CANCELLED, CustomerOrderStatus.CONFIRMED),
])
def test_invalid_transitions_are_refused(frm, to):
    with pytest.raises(mto.InvalidCustomerOrderTransition):
        mto.assert_transition(frm, to)


def test_order_totals_include_tax(db, catalogue, customer, tenant, warehouse):
    _, _, dupatta, wh = catalogue
    o = CustomerOrder(order_number="CO-TAX", customer_id=customer.id, outlet_id=wh.id,
                      status=CustomerOrderStatus.DRAFT)
    db.add(o)
    db.flush()
    db.add(CustomerOrderItem(customer_order_id=o.id, item_id=dupatta.id,
                             quantity=Decimal("2"), unit_price=Decimal("1000"),
                             tax_rate=Decimal("5")))
    db.flush()
    db.refresh(o)
    assert o.total_amount == Decimal("2100.00")   # 2000 + 5%
