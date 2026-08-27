"""Phase 3E - production output and partial completion."""

from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.models.inventory import MovementType
from app.models.product import ItemType
from app.models.production import ProductionStatus
from app.models.production_output import ProductionOutput
from app.services import production as prod
from app.services.inventory import apply_stock_delta
from tests.conftest import stock_of
from tests.test_ledger_integrity import assert_ledger_reconciles
from tests.test_production_orders import make_bom, make_item, make_order


@pytest.fixture()
def run(db, tenant, warehouse):
    """An in-progress order for 10 lehengas, with material stocked."""
    silk = make_item(db, "FAB-3E", "Silk", stock_uom="M", cost="800")
    apply_stock_delta(db, variant_id=silk.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("500"), movement_type=MovementType.OPENING_STOCK)
    db.flush()
    garment = make_item(db, "GAR-3E", "Lehenga", stock_uom="PC",
                        item_type=ItemType.FINISHED_PRODUCT)
    v = make_bom(db, garment, [(silk, "4.5", "M", 0)])
    order = make_order(db, garment, v, 10, warehouse)
    order.status = ProductionStatus.IN_PROGRESS
    db.flush()
    return order, garment, warehouse


def test_output_creates_finished_stock(db, run):
    order, garment, wh = run
    assert stock_of(db, garment.id, wh.id) == Decimal("0")

    rec = prod.record_output(db, order, Decimal("4"))
    db.flush()

    assert stock_of(db, garment.id, wh.id) == Decimal("4.0000")
    kind = db.execute(sa.text("SELECT movement_type FROM stock_movements WHERE id = :i"),
                      {"i": rec.stock_movement_id}).scalar_one()
    assert kind == "PRODUCTION_OUTPUT"
    assert_ledger_reconciles(db)


def test_output_is_linked_to_its_order(db, run):
    order, garment, wh = run
    rec = prod.record_output(db, order, Decimal("2"))
    db.flush()
    assert rec.production_order_id == order.id
    assert rec.item_id == garment.id
    assert rec.stock_movement_id is not None


def test_partial_output_does_not_close_the_order(db, run):
    """10 ordered, 6 made -> PARTIALLY_COMPLETED with 4 remaining, still open."""
    order, garment, wh = run
    prod.record_output(db, order, Decimal("6"))
    db.flush()

    assert order.status == ProductionStatus.PARTIALLY_COMPLETED
    assert order.produced_quantity == Decimal("6.0000")
    assert order.remaining_quantity == Decimal("4.0000")
    assert order.actual_completion is None


def test_multiple_outputs_accumulate(db, run):
    order, garment, wh = run
    for part in ("3", "3", "2"):
        prod.record_output(db, order, Decimal(part))
        db.flush()
    assert order.produced_quantity == Decimal("8.0000")
    assert order.status == ProductionStatus.PARTIALLY_COMPLETED
    assert stock_of(db, garment.id, wh.id) == Decimal("8.0000")
    assert db.query(ProductionOutput).filter(
        ProductionOutput.production_order_id == order.id
    ).count() == 3


def test_reaching_the_planned_quantity_completes_the_order(db, run):
    """Nothing is abandoned at full quantity, so there is no decision to record."""
    order, garment, wh = run
    prod.record_output(db, order, Decimal("10"))
    db.flush()
    assert order.status == ProductionStatus.COMPLETED
    assert order.remaining_quantity == Decimal("0.0000")
    assert order.actual_completion is not None


def test_output_beyond_the_plan_is_refused(db, run):
    """Overshooting in a single record is caught by the quantity guard."""
    order, _, _ = run
    prod.record_output(db, order, Decimal("6"))
    db.flush()
    with pytest.raises(prod.ProductionError, match="plans 10"):
        prod.record_output(db, order, Decimal("5"))  # 6 + 5 > 10


def test_completed_order_accepts_no_further_output(db, run):
    """Once the plan is met the order is closed, so the status guard fires first."""
    order, _, _ = run
    prod.record_output(db, order, Decimal("10"))
    db.flush()
    assert order.status == ProductionStatus.COMPLETED
    with pytest.raises(prod.ProductionError, match="released or in-progress"):
        prod.record_output(db, order, Decimal("1"))


def test_output_respects_already_cancelled_quantity(db, run):
    """6 produced + 4 cancelled leaves no room for more."""
    order, _, _ = run
    prod.record_output(db, order, Decimal("6"))
    db.flush()
    order.cancelled_quantity = Decimal("4")
    db.flush()
    with pytest.raises(prod.ProductionError, match="leaving 0"):
        prod.record_output(db, order, Decimal("1"))


def test_output_refused_before_release(db, tenant, warehouse):
    silk = make_item(db, "FAB-3E2", "Silk", stock_uom="M")
    garment = make_item(db, "GAR-3E2", "Lehenga", stock_uom="PC",
                        item_type=ItemType.FINISHED_PRODUCT)
    v = make_bom(db, garment, [(silk, "1", "M", 0)])
    order = make_order(db, garment, v, 5, warehouse)  # DRAFT
    with pytest.raises(prod.ProductionError, match="released or in-progress"):
        prod.record_output(db, order, Decimal("1"))


def test_decimal_output_for_a_semi_finished_run(db, tenant, warehouse):
    """12.5 m of piping, not 12 or 13."""
    silk = make_item(db, "FAB-3E3", "Silk", stock_uom="M")
    apply_stock_delta(db, variant_id=silk.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("100"), movement_type=MovementType.OPENING_STOCK)
    db.flush()
    piping = make_item(db, "SEMI-3E", "Piping", stock_uom="M",
                       item_type=ItemType.SEMI_FINISHED)
    v = make_bom(db, piping, [(silk, "0.2", "M", 0)])
    order = make_order(db, piping, v, "12.5", warehouse)
    order.status = ProductionStatus.IN_PROGRESS
    db.flush()

    prod.record_output(db, order, Decimal("12.5"))
    db.flush()
    assert stock_of(db, piping.id, warehouse.id) == Decimal("12.5000")
    assert order.status == ProductionStatus.COMPLETED
    assert_ledger_reconciles(db)


def test_complete_refuses_below_plan(db, run):
    order, _, _ = run
    prod.record_output(db, order, Decimal("6"))
    db.flush()
    with pytest.raises(prod.ProductionError, match="close the order short"):
        prod.complete_order(db, order)


def test_output_never_double_counts_after_partial(db, run):
    """The classic error: 6 then 4 must be 10 in stock, not 16."""
    order, garment, wh = run
    prod.record_output(db, order, Decimal("6"))
    db.flush()
    prod.record_output(db, order, Decimal("4"))
    db.flush()
    assert stock_of(db, garment.id, wh.id) == Decimal("10.0000")
    assert order.produced_quantity == Decimal("10.0000")
    assert_ledger_reconciles(db)


def test_output_rollback_leaves_no_stock(db, run):
    """Atomicity: a failure after the ledger row must unwind it."""
    order, garment, wh = run
    before = stock_of(db, garment.id, wh.id)
    moves = db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one()

    sp = db.begin_nested()
    try:
        prod.record_output(db, order, Decimal("5"))
        raise RuntimeError("simulated failure after the ledger row")
    except RuntimeError:
        sp.rollback()

    assert stock_of(db, garment.id, wh.id) == before
    assert db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one() == moves
    assert_ledger_reconciles(db)


def test_close_short_after_partial_output(db, run):
    """6 of 10 made, the rest abandoned - produced and cancelled must sum to plan."""
    order, garment, wh = run
    prod.record_output(db, order, Decimal("6"))
    db.flush()

    order.status = ProductionStatus.CLOSED_SHORT
    order.produced_quantity = Decimal("6")
    order.cancelled_quantity = Decimal("4")
    db.flush()

    assert order.produced_quantity + order.cancelled_quantity == order.planned_quantity
    assert stock_of(db, garment.id, wh.id) == Decimal("6.0000")
    assert_ledger_reconciles(db)
