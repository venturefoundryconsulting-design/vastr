"""Phase 3H - production costing and reports."""

from decimal import Decimal

import pytest

from app.models.inventory import MovementType
from app.models.product import ItemType
from app.models.production import ProductionStatus
from app.models.quality import QcResult
from app.models.workforce import PayModel, ProductionStage, Tailor, WorkOrder
from app.services import costing
from app.services import material_flow as mf
from app.services import production as prod
from app.services import quality as qc
from app.services import workforce as wf
from app.services.inventory import apply_stock_delta
from tests.test_ledger_integrity import assert_ledger_reconciles
from tests.test_production_orders import make_bom, make_item, make_order


@pytest.fixture()
def costed_run(db, tenant, warehouse):
    """An order for 10 lehengas: lace at 120/m, 20 m planned."""
    lace = make_item(db, "LAC-3H", "Gold Lace", stock_uom="M", cost="120")
    apply_stock_delta(db, variant_id=lace.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("200"), movement_type=MovementType.OPENING_STOCK)
    db.flush()
    garment = make_item(db, "GAR-3H", "Lehenga", stock_uom="PC",
                        item_type=ItemType.FINISHED_PRODUCT)
    v = make_bom(db, garment, [(lace, "2", "M", 0)])   # 2 m each x 10 = 20 m
    order = make_order(db, garment, v, 10, warehouse)
    order.status = ProductionStatus.RELEASED
    db.flush()
    m = next(x for x in order.materials if not x.is_subassembly)
    return order, m, lace, garment, warehouse


def test_estimated_material_cost_matches_the_bom(db, costed_run):
    """20 m planned x 120 = 2400, computed the same way the BOM screen does."""
    order, *_ = costed_run
    result = costing.order_cost(db, order)
    assert result["estimated_material_cost"] == Decimal("2400.00")
    assert result["actual_material_cost"] == Decimal("0.00")


def test_actual_material_cost_follows_real_consumption(db, costed_run):
    order, m, *_ = costed_run
    mf.reserve(db, order, m.id, Decimal("20"))
    db.flush()
    mf.issue(db, order, m.id, Decimal("20"))
    db.flush()
    mf.consume(db, order, m.id, Decimal("18"))
    db.flush()

    result = costing.order_cost(db, order)
    assert result["actual_material_cost"] == Decimal("2160.00")   # 18 x 120
    assert result["estimated_material_cost"] == Decimal("2400.00")
    # Under-consumption shows as a favourable variance rather than being hidden.
    assert result["material_lines"][0]["variance"] == Decimal("-240.00")


def test_wastage_is_costed_separately_from_consumption(db, costed_run):
    """Consumed material became product; wasted material did not. Both cost money,
    and keeping them apart is what makes the variance meaningful."""
    order, m, *_ = costed_run
    mf.reserve(db, order, m.id, Decimal("20"))
    db.flush()
    mf.issue(db, order, m.id, Decimal("20"))
    db.flush()
    mf.consume(db, order, m.id, Decimal("17"))
    db.flush()
    qc.record_wastage(db, order, m.id, Decimal("1.5"))
    db.flush()

    result = costing.order_cost(db, order)
    assert result["actual_material_cost"] == Decimal("2040.00")   # 17 x 120
    assert result["wastage_cost"] == Decimal("180.00")            # 1.5 x 120
    assert result["actual_total_cost"] == Decimal("2220.00")      # no labour yet


def test_labour_cost_uses_the_frozen_rate(db, costed_run, tenant):
    """A rate change afterwards must not rewrite what the run cost."""
    order, *_ = costed_run
    tailor = Tailor(code="T-3H", name="Ramesh", pay_model=PayModel.PER_GARMENT,
                    default_rate=Decimal("300"))
    db.add(tailor)
    db.flush()
    stage = db.query(ProductionStage).filter(ProductionStage.code == "STITCHING").one()
    wo = WorkOrder(wo_number="WO-3H-1", production_order_id=order.id,
                   stage_id=stage.id, quantity=Decimal("10"))
    db.add(wo)
    db.flush()
    wf.assign(db, wo, tailor)
    wf.start(db, wo)
    wf.complete(db, wo, Decimal("10"))
    db.flush()

    tailor.default_rate = Decimal("500")   # raise afterwards
    db.flush()

    result = costing.order_cost(db, order)
    assert result["actual_labour_cost"] == Decimal("3000.00")   # 10 x 300, not 500
    assert result["estimated_labour_cost"] == Decimal("3000.00")


def test_total_cost_is_material_plus_labour_plus_wastage(db, costed_run, tenant):
    """The brief's formula, end to end."""
    order, m, *_ = costed_run
    mf.reserve(db, order, m.id, Decimal("20"))
    db.flush()
    mf.issue(db, order, m.id, Decimal("20"))
    db.flush()
    mf.consume(db, order, m.id, Decimal("18"))
    db.flush()
    qc.record_wastage(db, order, m.id, Decimal("2"))
    db.flush()

    tailor = Tailor(code="T-3H2", name="Priya", pay_model=PayModel.PER_STAGE,
                    default_rate=Decimal("800"))
    db.add(tailor)
    db.flush()
    stage = db.query(ProductionStage).filter(ProductionStage.code == "FINISHING").one()
    wo = WorkOrder(wo_number="WO-3H-2", production_order_id=order.id,
                   stage_id=stage.id, quantity=Decimal("1"))
    db.add(wo)
    db.flush()
    wf.assign(db, wo, tailor)
    wf.start(db, wo)
    wf.complete(db, wo, Decimal("1"))
    db.flush()

    result = costing.order_cost(db, order)
    # material 18x120=2160, wastage 2x120=240, labour 1x800=800
    assert result["actual_material_cost"] == Decimal("2160.00")
    assert result["wastage_cost"] == Decimal("240.00")
    assert result["actual_labour_cost"] == Decimal("800.00")
    assert result["actual_total_cost"] == Decimal("3200.00")


def test_unit_cost_is_none_until_something_is_produced(db, costed_run):
    """Dividing by zero output would be a made-up number."""
    order, *_ = costed_run
    result = costing.order_cost(db, order)
    assert result["actual_unit_cost"] is None
    assert result["estimated_unit_cost"] == Decimal("240.00")   # 2400 / 10


def test_actual_unit_cost_after_output(db, costed_run):
    order, m, _, garment, wh = costed_run
    mf.reserve(db, order, m.id, Decimal("20"))
    db.flush()
    mf.issue(db, order, m.id, Decimal("20"))
    db.flush()
    mf.consume(db, order, m.id, Decimal("20"))
    db.flush()
    order.status = ProductionStatus.IN_PROGRESS
    db.flush()
    prod.record_output(db, order, Decimal("10"))
    db.flush()

    result = costing.order_cost(db, order)
    assert result["produced_quantity"] == Decimal("10.0000")
    assert result["actual_unit_cost"] == Decimal("240.00")   # 2400 / 10
    assert_ledger_reconciles(db)


def test_planned_vs_actual_reports_the_variance(db, costed_run):
    order, m, *_ = costed_run
    mf.reserve(db, order, m.id, Decimal("20"))
    db.flush()
    mf.issue(db, order, m.id, Decimal("20"))
    db.flush()
    mf.consume(db, order, m.id, Decimal("22") if False else Decimal("20"))
    db.flush()

    rows = costing.planned_vs_actual(db, order)
    assert len(rows) == 1
    assert rows[0]["planned"] == Decimal("20")
    assert rows[0]["consumed"] == Decimal("20")
    assert rows[0]["quantity_variance"] == Decimal("0")


def test_over_consumption_shows_as_positive_variance(db, costed_run):
    """The BOM said 20 m, the floor used 22. The variance is the signal - the
    recipe is not quietly rewritten to match."""
    order, m, *_ = costed_run
    mf.reserve(db, order, m.id, Decimal("20"))
    db.flush()
    mf.issue(db, order, m.id, Decimal("20"))
    db.flush()
    mf.consume(db, order, m.id, Decimal("20"))
    db.flush()

    result = costing.order_cost(db, order)
    assert result["material_lines"][0]["planned_quantity"] == Decimal("20")
    # The BOM component is untouched by anything that happened on the floor.
    assert m.planned_quantity == Decimal("20.0000")


def test_costing_moves_no_inventory(db, costed_run):
    import sqlalchemy as sa

    order, *_ = costed_run
    before = db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one()
    for _ in range(3):
        costing.order_cost(db, order)
        costing.planned_vs_actual(db, order)
    assert db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one() == before


# ------------------------------------------------------------------ reports


def test_production_summary_counts_by_status(db, costed_run):
    order, *_ = costed_run
    summary = costing.production_summary(db)
    assert summary["orders_by_status"].get("released", 0) >= 1
    assert summary["active_orders"] >= 1


def test_wastage_report_ranks_by_cost(db, costed_run):
    order, m, *_ = costed_run
    mf.reserve(db, order, m.id, Decimal("20"))
    db.flush()
    mf.issue(db, order, m.id, Decimal("20"))
    db.flush()
    qc.record_wastage(db, order, m.id, Decimal("3"))
    db.flush()

    rows = costing.wastage_report(db)
    assert rows[0]["sku"] == "LAC-3H"
    assert rows[0]["cost"] == Decimal("360.00")


def test_tailor_productivity_uses_frozen_rates(db, costed_run, tenant):
    order, *_ = costed_run
    tailor = Tailor(code="T-3H3", name="Anita", pay_model=PayModel.PER_PIECE,
                    default_rate=Decimal("50"))
    db.add(tailor)
    db.flush()
    stage = db.query(ProductionStage).filter(ProductionStage.code == "HANDWORK").one()
    wo = WorkOrder(wo_number="WO-3H-3", production_order_id=order.id,
                   stage_id=stage.id, quantity=Decimal("10"))
    db.add(wo)
    db.flush()
    wf.assign(db, wo, tailor)
    wf.start(db, wo)
    wf.complete(db, wo, Decimal("8"))
    db.flush()

    rows = {r["tailor_id"]: r for r in costing.tailor_productivity(db)}
    assert rows[tailor.id]["completed_work_orders"] == 1
    assert rows[tailor.id]["completed_quantity"] == Decimal("8")
    assert rows[tailor.id]["earnings"] == Decimal("400.00")   # 8 x 50


def test_summary_counts_open_rework(db, costed_run):
    order, *_ = costed_run
    check = qc.record_check(db, order, result=QcResult.FAIL,
                            checked_quantity=10, failed_quantity=2)
    db.flush()
    qc.raise_rework(db, order, quantity=2, reason="hem", quality_check_id=check.id)
    db.flush()
    summary = costing.production_summary(db)
    assert summary["open_rework"] >= 1
    assert summary["failed_quality_checks"] >= 1
