"""Phase 3F - tailors, stages and work orders.

The tests that matter most are the isolation ones: a tailor must be able to drive
their own work and nothing else, and that has to hold at the server, not by the
client asking nicely.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.models.inventory import MovementType
from app.models.product import ItemType
from app.models.production import ProductionStatus
from app.models.user import User, UserRole
from app.models.workforce import PayModel, ProductionStage, Tailor, WorkOrder, WorkOrderStatus
from app.services import workforce as wf
from app.services.inventory import apply_stock_delta
from tests.test_ledger_integrity import assert_ledger_reconciles
from tests.test_production_orders import make_bom, make_item, make_order


def stage(db, code: str) -> ProductionStage:
    return db.query(ProductionStage).filter(ProductionStage.code == code).one()


@pytest.fixture()
def tailors(db, tenant):
    ramesh = Tailor(code="T-001", name="Ramesh", pay_model=PayModel.PER_STAGE,
                    default_rate=Decimal("800"))
    priya = Tailor(code="T-002", name="Priya", pay_model=PayModel.PER_GARMENT,
                   default_rate=Decimal("1200"))
    db.add_all([ramesh, priya])
    db.flush()
    return ramesh, priya


@pytest.fixture()
def order(db, tenant, warehouse):
    silk = make_item(db, "FAB-3F", "Silk", stock_uom="M")
    apply_stock_delta(db, variant_id=silk.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("200"), movement_type=MovementType.OPENING_STOCK)
    db.flush()
    garment = make_item(db, "GAR-3F", "Lehenga", stock_uom="PC",
                        item_type=ItemType.FINISHED_PRODUCT)
    v = make_bom(db, garment, [(silk, "4.5", "M", 0)])
    o = make_order(db, garment, v, 10, warehouse)
    o.status = ProductionStatus.IN_PROGRESS
    db.flush()
    return o


def make_wo(db, order, code, tailor=None, qty="10", due=None, seq=0):
    wo = WorkOrder(
        wo_number=f"WO-{code}-{order.id}-{seq}", production_order_id=order.id,
        stage_id=stage(db, code).id, quantity=Decimal(qty), sequence=seq, due_date=due,
    )
    db.add(wo)
    db.flush()
    if tailor:
        wf.assign(db, wo, tailor)
    return wo


# ------------------------------------------------------------------- stages


def test_default_stages_are_seeded_as_data(db, tenant):
    """Nine stages, configurable - not a hard-coded list in the code."""
    codes = [s.code for s in db.query(ProductionStage).order_by(ProductionStage.sequence).all()]
    assert codes == ["DESIGN", "MATERIAL_PREP", "CUTTING", "STITCHING", "EMBROIDERY",
                     "HANDWORK", "FINISHING", "QUALITY_CHECK", "COMPLETED"]


def test_a_stage_can_be_added_without_code_changes(db, tenant):
    db.add(ProductionStage(code="BEADING", name="Beading", sequence=55))
    db.flush()
    assert db.query(ProductionStage).filter(ProductionStage.code == "BEADING").one().name == "Beading"


def test_exactly_one_stage_is_marked_for_qc(db, tenant):
    qc = db.query(ProductionStage).filter(ProductionStage.is_qc.is_(True)).all()
    assert [s.code for s in qc] == ["QUALITY_CHECK"]


# ------------------------------------------------------------------ tailors


def test_a_tailor_needs_no_user_account(db, tenant):
    """Most boutique tailors are contracted and never log in."""
    t = Tailor(code="T-EXT", name="External Embroiderer")
    db.add(t)
    db.flush()
    assert t.user_id is None and t.is_active


def test_tailor_code_is_unique(db, tailors):
    db.add(Tailor(code="T-001", name="Clash"))
    with pytest.raises(sa.exc.IntegrityError):
        db.flush()


def test_no_stock_table_references_a_tailor(db, tenant):
    """The architectural decision, asserted rather than just documented:
    tailors are resources, not inventory locations."""
    referencing = {
        r[0]
        for r in db.execute(sa.text("""
            SELECT tc.table_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name = ccu.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name = 'tailors'
        """)).fetchall()
    }
    assert "stock_levels" not in referencing
    assert "stock_movements" not in referencing
    assert "stock_reservations" not in referencing


# -------------------------------------------------------------- assignment


def test_assignment_freezes_the_pay_terms(db, order, tailors):
    """A later rate change must not rewrite what past work cost."""
    ramesh, _ = tailors
    wo = make_wo(db, order, "STITCHING", ramesh)
    assert wo.status == WorkOrderStatus.ASSIGNED
    assert wo.rate == Decimal("800.00")
    assert wo.pay_model == PayModel.PER_STAGE

    ramesh.default_rate = Decimal("950")
    db.flush()
    assert wo.rate == Decimal("800.00")


def test_stage_default_rate_is_the_fallback(db, order, tenant):
    """Set "stitching is 800" once instead of on every tailor."""
    st = stage(db, "STITCHING")
    st.default_rate = Decimal("750")
    db.flush()
    t = Tailor(code="T-NORATE", name="No Rate", default_rate=Decimal("0"))
    db.add(t)
    db.flush()
    wo = make_wo(db, order, "STITCHING", t)
    assert wo.rate == Decimal("750.00")


def test_inactive_tailor_cannot_be_assigned(db, order, tailors):
    ramesh, _ = tailors
    ramesh.is_active = False
    db.flush()
    wo = make_wo(db, order, "CUTTING")
    with pytest.raises(wf.WorkOrderError, match="not an active tailor"):
        wf.assign(db, wo, ramesh)


# ---------------------------------------------------------- state machine


def test_full_work_order_lifecycle(db, order, tailors):
    ramesh, _ = tailors
    wo = make_wo(db, order, "STITCHING", ramesh)
    wf.start(db, wo)
    assert wo.status == WorkOrderStatus.IN_PROGRESS and wo.started_at is not None
    wf.pause(db, wo, "waiting for lace")
    assert wo.status == WorkOrderStatus.PAUSED and wo.issue_note == "waiting for lace"
    wf.start(db, wo)
    wf.complete(db, wo)
    assert wo.status == WorkOrderStatus.COMPLETED
    assert wo.completed_quantity == Decimal("10.0000")
    assert wo.completed_at is not None


def test_cannot_start_without_a_tailor(db, order):
    wo = make_wo(db, order, "CUTTING")
    with pytest.raises(wf.WorkOrderError, match="Assign a tailor"):
        wf.start(db, wo)


@pytest.mark.parametrize("frm,to", [
    (WorkOrderStatus.PENDING, WorkOrderStatus.IN_PROGRESS),   # must assign first
    (WorkOrderStatus.PENDING, WorkOrderStatus.COMPLETED),     # cannot skip
    (WorkOrderStatus.CANCELLED, WorkOrderStatus.IN_PROGRESS),  # terminal
    (WorkOrderStatus.ASSIGNED, WorkOrderStatus.COMPLETED),    # must start first
])
def test_invalid_transitions_are_refused(frm, to):
    with pytest.raises(wf.InvalidWorkOrderTransition):
        wf.assert_transition(frm, to)


def test_partial_completion_is_recorded_honestly(db, order, tailors):
    """A stage that got through 6 of 10 records 6, not a rounded-up 10."""
    ramesh, _ = tailors
    wo = make_wo(db, order, "STITCHING", ramesh)
    wf.start(db, wo)
    wf.complete(db, wo, Decimal("6"))
    assert wo.completed_quantity == Decimal("6.0000")


def test_cannot_complete_more_than_the_work_order_covers(db, order, tailors):
    ramesh, _ = tailors
    wo = make_wo(db, order, "STITCHING", ramesh)
    wf.start(db, wo)
    with pytest.raises(wf.WorkOrderError, match="covers 10"):
        wf.complete(db, wo, Decimal("12"))


def test_rework_reopens_completed_work(db, order, tailors):
    ramesh, _ = tailors
    wo = make_wo(db, order, "STITCHING", ramesh)
    wf.start(db, wo)
    wf.complete(db, wo)
    wf.send_to_rework(db, wo, "seam puckering on three pieces")
    assert wo.status == WorkOrderStatus.REWORK
    assert wo.completed_at is None
    assert "puckering" in wo.issue_note
    wf.start(db, wo)
    assert wo.status == WorkOrderStatus.IN_PROGRESS


def test_rework_requires_a_reason(db, order, tailors):
    ramesh, _ = tailors
    wo = make_wo(db, order, "STITCHING", ramesh)
    wf.start(db, wo)
    wf.complete(db, wo)
    with pytest.raises(wf.WorkOrderError, match="reason is required"):
        wf.send_to_rework(db, wo, "   ")


# ------------------------------------------------------------ labour cost


@pytest.mark.parametrize("model,rate,qty,hours,expected", [
    (PayModel.PER_STAGE, "800", "1", "0", "800.00"),
    (PayModel.PER_GARMENT, "1200", "3", "0", "3600.00"),
    (PayModel.PER_PIECE, "50", "12", "0", "600.00"),
    (PayModel.HOURLY, "150", "5", "6.5", "975.00"),
    (PayModel.FIXED, "5000", "10", "0", "5000.00"),
])
def test_labour_cost_by_pay_model(db, order, tenant, model, rate, qty, hours, expected):
    t = Tailor(code=f"T-{model.value}", name=model.value, pay_model=model,
               default_rate=Decimal(rate))
    db.add(t)
    db.flush()
    wo = make_wo(db, order, "STITCHING", t, qty="12")
    wf.start(db, wo)
    wf.complete(db, wo, Decimal(qty), hours=Decimal(hours))
    assert wo.labour_cost == Decimal(expected)


def test_order_labour_cost_sums_its_work_orders(db, order, tailors):
    ramesh, priya = tailors
    for i, (code, t) in enumerate([("CUTTING", ramesh), ("STITCHING", priya)]):
        wo = make_wo(db, order, code, t, qty="1", seq=i)
        wf.start(db, wo)
        wf.complete(db, wo, Decimal("1"))
    # Ramesh per-stage 800 x 1, Priya per-garment 1200 x 1
    assert wf.labour_cost_for_order(db, order) == Decimal("2000.00")


# --------------------------------------------------------------- workload


def test_workload_counts_by_tailor(db, order, tailors):
    ramesh, priya = tailors
    yesterday = date.today() - timedelta(days=1)
    a = make_wo(db, order, "CUTTING", ramesh, seq=0)
    wf.start(db, a)
    make_wo(db, order, "STITCHING", ramesh, seq=1)
    overdue = make_wo(db, order, "FINISHING", ramesh, due=yesterday, seq=2)
    done = make_wo(db, order, "EMBROIDERY", priya, seq=3)
    wf.start(db, done)
    wf.complete(db, done)
    db.flush()

    rows = {r["tailor_id"]: r for r in wf.workload(db)}
    assert rows[ramesh.id]["active"] == 1
    assert rows[ramesh.id]["pending"] == 2
    assert rows[ramesh.id]["overdue"] == 1
    assert rows[priya.id]["completed"] == 1
    assert overdue.is_overdue is True


# ------------------------------------------------- isolation (the key tests)


def test_tailor_role_grants_only_its_own_queue(db, tenant):
    """A tailor gets work_orders.own and materials.view. Nothing else."""
    from app.permissions.catalog import ROLE_GRANTS

    granted = ROLE_GRANTS[UserRole.TAILOR]
    assert granted == {"work_orders.own", "materials.view"}
    for forbidden in (
        "purchase_orders.view", "reports.view", "settings.manage", "users.manage",
        "inventory.edit", "payroll.manage", "materials.issue", "production.create",
    ):
        assert forbidden not in granted, f"tailor must not have {forbidden}"


def test_my_work_orders_resolves_the_tailor_from_the_user(db, order, tenant, outlet):
    """The queue is scoped server-side; the client never names a tailor."""
    from app.routers import workforce as wf_router

    u = User(tenant_id=tenant.id, name="Ramesh Login", email="ramesh@example.test",
             hashed_password="x", role=UserRole.TAILOR, outlet_id=outlet.id)
    db.add(u)
    db.flush()
    mine = Tailor(code="T-MINE", name="Ramesh", user_id=u.id)
    other = Tailor(code="T-OTHER", name="Someone Else")
    db.add_all([mine, other])
    db.flush()

    make_wo(db, order, "CUTTING", mine, seq=0)
    make_wo(db, order, "STITCHING", other, seq=1)
    db.flush()

    rows = wf_router.my_work_orders(db, u)
    assert len(rows) == 1
    assert rows[0].tailor_id == mine.id


def test_a_tailor_cannot_drive_someone_elses_work_order(db, order, tenant, outlet):
    from fastapi import HTTPException

    from app.routers import workforce as wf_router

    u = User(tenant_id=tenant.id, name="Tailor A", email="tailor-a@example.test",
             hashed_password="x", role=UserRole.TAILOR, outlet_id=outlet.id)
    db.add(u)
    db.flush()
    mine = Tailor(code="T-A", name="A", user_id=u.id)
    other = Tailor(code="T-B", name="B")
    db.add_all([mine, other])
    db.flush()
    theirs = make_wo(db, order, "STITCHING", other)
    db.flush()

    with pytest.raises(HTTPException) as exc:
        wf_router._assert_may_touch(db, u, theirs)
    assert exc.value.status_code == 403


def test_a_manager_may_drive_any_work_order(db, order, tenant, user, tailors):
    from app.routers import workforce as wf_router

    ramesh, _ = tailors
    wo = make_wo(db, order, "STITCHING", ramesh)
    db.flush()
    wf_router._assert_may_touch(db, user, wo)  # admin - must not raise


def test_work_orders_move_no_inventory(db, order, tailors, warehouse):
    """The tailor layer is labour, not stock."""
    ramesh, _ = tailors
    before = db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one()
    wo = make_wo(db, order, "STITCHING", ramesh)
    wf.start(db, wo)
    wf.complete(db, wo)
    db.flush()
    assert db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one() == before
    assert_ledger_reconciles(db)
