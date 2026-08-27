"""Phase 3G - QC, rework and wastage."""

from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.models.inventory import MovementType
from app.models.product import ItemType
from app.models.production import ProductionStatus
from app.models.quality import (
    DefectCategory,
    ProductionWastage,
    QcResult,
    ReworkOrder,
    ReworkStatus,
    WastageReason,
)
from app.models.workforce import ProductionStage, Tailor, WorkOrder, WorkOrderStatus
from app.services import material_flow as mf
from app.services import quality as qc
from app.services import workforce as wf
from app.services.inventory import apply_stock_delta
from tests.conftest import stock_of
from tests.test_ledger_integrity import assert_ledger_reconciles
from tests.test_production_orders import make_bom, make_item, make_order


@pytest.fixture()
def issued_order(db, tenant, warehouse):
    """An in-progress order with 20 m of lace already issued to the floor."""
    lace = make_item(db, "LAC-3G", "Gold Lace", stock_uom="M", cost="120")
    apply_stock_delta(db, variant_id=lace.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("100"), movement_type=MovementType.OPENING_STOCK)
    db.flush()
    garment = make_item(db, "GAR-3G", "Lehenga", stock_uom="PC",
                        item_type=ItemType.FINISHED_PRODUCT)
    v = make_bom(db, garment, [(lace, "20", "M", 0)])
    order = make_order(db, garment, v, 1, warehouse)
    order.status = ProductionStatus.RELEASED
    db.flush()
    m = next(x for x in order.materials if not x.is_subassembly)
    mf.reserve(db, order, m.id, Decimal("20"))
    db.flush()
    mf.issue(db, order, m.id, Decimal("20"))
    db.flush()
    order.status = ProductionStatus.IN_PROGRESS
    db.flush()
    return order, m, lace, warehouse


def defect(db, code="STITCHING") -> DefectCategory:
    return db.query(DefectCategory).filter(DefectCategory.code == code).one()


# ---------------------------------------------------------- reason catalogues


def test_defect_and_wastage_reasons_are_seeded_as_data(db, tenant):
    """Configurable lists, not enums - a boutique adds its own without a release."""
    assert db.query(DefectCategory).count() >= 8
    assert db.query(WastageReason).count() >= 6
    db.add(DefectCategory(code="ZIP_MISALIGNED", name="Zip misaligned"))
    db.flush()
    assert defect(db, "ZIP_MISALIGNED").name == "Zip misaligned"


# ------------------------------------------------------------ quality checks


def test_passing_check_records_the_split(db, issued_order):
    order, *_ = issued_order
    check = qc.record_check(db, order, result=QcResult.PASS, checked_quantity=10)
    db.flush()
    assert check.passed_quantity == Decimal("10")
    assert check.failed_quantity == Decimal("0")
    assert check.checked_at is not None


def test_partial_check_splits_pass_and_fail(db, issued_order):
    """8 of 10 fine, 2 to redo - the common boutique case."""
    order, *_ = issued_order
    check = qc.record_check(db, order, result=QcResult.PARTIAL,
                            checked_quantity=10, failed_quantity=2)
    db.flush()
    assert check.passed_quantity == Decimal("8")
    assert check.failed_quantity == Decimal("2")


def test_a_pass_cannot_carry_failures(db, issued_order):
    order, *_ = issued_order
    with pytest.raises(qc.QualityError, match="passing check cannot have failures"):
        qc.record_check(db, order, result=QcResult.PASS, checked_quantity=10, failed_quantity=2)


def test_a_fail_must_say_how_many(db, issued_order):
    order, *_ = issued_order
    with pytest.raises(qc.QualityError, match="how many pieces failed"):
        qc.record_check(db, order, result=QcResult.FAIL, checked_quantity=10, failed_quantity=0)


def test_failures_cannot_exceed_what_was_inspected(db, issued_order):
    order, *_ = issued_order
    with pytest.raises(qc.QualityError, match="cannot exceed"):
        qc.record_check(db, order, result=QcResult.FAIL, checked_quantity=5, failed_quantity=8)


def test_defects_are_categorised_for_reporting(db, issued_order):
    order, *_ = issued_order
    check = qc.record_check(
        db, order, result=QcResult.FAIL, checked_quantity=10, failed_quantity=3,
        defects=[{"defect_category_id": defect(db).id, "quantity": 3, "notes": "left seam"}],
    )
    db.flush()
    assert len(check.defects) == 1
    assert check.defects[0].category.code == "STITCHING"


def test_quality_check_moves_no_inventory(db, issued_order):
    order, _, lace, wh = issued_order
    before_qty = stock_of(db, lace.id, wh.id)
    before_moves = db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one()

    qc.record_check(db, order, result=QcResult.FAIL, checked_quantity=10, failed_quantity=4)
    db.flush()

    assert stock_of(db, lace.id, wh.id) == before_qty
    assert db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one() == before_moves
    assert_ledger_reconciles(db)


# -------------------------------------------------------------------- rework


def test_rework_stays_on_the_original_production_order(db, issued_order):
    """No duplicate production order - the fault stays linked to the run."""
    order, *_ = issued_order
    check = qc.record_check(db, order, result=QcResult.FAIL,
                            checked_quantity=10, failed_quantity=3)
    db.flush()
    rw = qc.raise_rework(db, order, quantity=3, reason="seam puckering",
                         quality_check_id=check.id)
    db.flush()

    assert rw.production_order_id == order.id
    assert rw.status == ReworkStatus.OPEN
    # Exactly one production order still - rework did not spawn another.
    assert db.execute(sa.text(
        "SELECT count(*) FROM production_orders WHERE item_id = :i"
    ), {"i": order.item_id}).scalar_one() == 1


def test_rework_requires_a_reason(db, issued_order):
    order, *_ = issued_order
    with pytest.raises(qc.QualityError, match="reason is required"):
        qc.raise_rework(db, order, quantity=2, reason="  ")


def test_rework_reopens_the_completed_work_order(db, issued_order, tenant):
    """QC failure puts the stage back in the tailor's queue."""
    order, *_ = issued_order
    tailor = Tailor(code="T-3G", name="Ramesh")
    db.add(tailor)
    db.flush()
    stage = db.query(ProductionStage).filter(ProductionStage.code == "STITCHING").one()
    wo = WorkOrder(wo_number="WO-3G-1", production_order_id=order.id,
                   stage_id=stage.id, quantity=Decimal("10"))
    db.add(wo)
    db.flush()
    wf.assign(db, wo, tailor)
    wf.start(db, wo)
    wf.complete(db, wo)
    assert wo.status == WorkOrderStatus.COMPLETED

    qc.raise_rework(db, order, quantity=3, reason="seam puckering", work_order_id=wo.id)
    db.flush()
    assert wo.status == WorkOrderStatus.REWORK
    assert wo.completed_at is None


def test_rework_can_be_resolved(db, issued_order):
    order, *_ = issued_order
    rw = qc.raise_rework(db, order, quantity=2, reason="loose thread")
    db.flush()
    qc.resolve_rework(db, rw)
    assert rw.status == ReworkStatus.RESOLVED
    assert rw.resolved_at is not None
    with pytest.raises(qc.QualityError, match="already resolved"):
        qc.resolve_rework(db, rw)


def test_qc_fail_to_rework_to_pass(db, issued_order):
    """The full loop the brief describes."""
    order, *_ = issued_order
    fail = qc.record_check(db, order, result=QcResult.FAIL,
                           checked_quantity=10, failed_quantity=2)
    db.flush()
    rw = qc.raise_rework(db, order, quantity=2, reason="hem uneven", quality_check_id=fail.id)
    db.flush()
    qc.resolve_rework(db, rw)
    retest = qc.record_check(db, order, result=QcResult.PASS, checked_quantity=2)
    db.flush()
    assert retest.result == QcResult.PASS
    assert rw.status == ReworkStatus.RESOLVED


# ------------------------------------------------------------------ wastage


def test_wastage_records_without_moving_stock(db, issued_order):
    """The material left at issue - deducting again would double-count."""
    order, m, lace, wh = issued_order
    before_qty = stock_of(db, lace.id, wh.id)
    before_moves = db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one()

    qc.record_wastage(db, order, m.id, Decimal("0.5"))
    db.flush()

    assert stock_of(db, lace.id, wh.id) == before_qty
    assert db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one() == before_moves
    assert m.wasted_quantity == Decimal("0.5000")
    assert_ledger_reconciles(db)


def test_wastage_reduces_what_is_still_on_the_floor(db, issued_order):
    """Issued 20, consumed 15, wasted 0.5 -> 4.5 still with production."""
    order, m, _, _ = issued_order
    mf.consume(db, order, m.id, Decimal("15"))
    db.flush()
    qc.record_wastage(db, order, m.id, Decimal("0.5"))
    db.flush()
    assert m.still_with_production == Decimal("4.5000")
    assert m.returnable_quantity == Decimal("4.5000")


def test_cannot_waste_more_than_is_on_the_floor(db, issued_order):
    order, m, _, _ = issued_order
    mf.consume(db, order, m.id, Decimal("19"))
    db.flush()
    with pytest.raises(qc.QualityError, match="already accounted for"):
        qc.record_wastage(db, order, m.id, Decimal("2"))


def test_wasted_material_cannot_also_be_returned(db, issued_order):
    """Waste and return are mutually exclusive claims on the same metre."""
    order, m, _, _ = issued_order
    mf.consume(db, order, m.id, Decimal("15"))
    db.flush()
    qc.record_wastage(db, order, m.id, Decimal("3"))
    db.flush()
    with pytest.raises(mf.MaterialFlowError, match="at most 2"):
        mf.return_material(db, order, m.id, Decimal("3"))


def test_wastage_is_attributable_to_a_tailor(db, issued_order, tenant):
    order, m, _, _ = issued_order
    tailor = Tailor(code="T-W", name="Priya")
    db.add(tailor)
    db.flush()
    reason = db.query(WastageReason).filter(WastageReason.code == "MISCUT").one()
    rec = qc.record_wastage(db, order, m.id, Decimal("1.25"),
                            tailor_id=tailor.id, reason_id=reason.id, notes="cut against grain")
    db.flush()
    assert rec.tailor_id == tailor.id
    assert rec.reason.code == "MISCUT"


def test_wastage_cost_uses_standard_cost(db, issued_order):
    """0.5 m of lace at 120 = 60.00 - same source as the BOM estimate."""
    order, m, _, _ = issued_order
    qc.record_wastage(db, order, m.id, Decimal("0.5"))
    db.flush()
    assert qc.wastage_cost(db, order) == Decimal("60.00")


def test_wastage_summary_groups_by_material(db, issued_order):
    order, m, _, _ = issued_order
    qc.record_wastage(db, order, m.id, Decimal("0.5"))
    db.flush()
    qc.record_wastage(db, order, m.id, Decimal("0.25"))
    db.flush()
    rows = qc.wastage_summary(db, order)
    assert len(rows) == 1
    assert rows[0]["quantity"] == Decimal("0.7500")
    assert rows[0]["entries"] == 2
    assert rows[0]["cost"] == Decimal("90.00")


def test_full_material_reconciliation_with_wastage(db, issued_order):
    """Issued 20 = consumed 16 + wasted 1.5 + returned 2.5 + on floor 0."""
    order, m, lace, wh = issued_order
    mf.consume(db, order, m.id, Decimal("16"))
    db.flush()
    qc.record_wastage(db, order, m.id, Decimal("1.5"))
    db.flush()
    mf.return_material(db, order, m.id, Decimal("2.5"))
    db.flush()

    assert m.issued_quantity == Decimal("20.0000")
    assert m.consumed_quantity == Decimal("16.0000")
    assert m.wasted_quantity == Decimal("1.5000")
    assert m.returned_quantity == Decimal("2.5000")
    assert m.still_with_production == Decimal("0.0000")
    # 100 - 20 issued + 2.5 returned
    assert stock_of(db, lace.id, wh.id) == Decimal("82.5000")
    assert_ledger_reconciles(db)
