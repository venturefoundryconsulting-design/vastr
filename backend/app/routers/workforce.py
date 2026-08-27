"""Tailors, production stages and work orders.

TAILOR SCOPING IS SERVER-SIDE. ``/api/work-orders/mine`` resolves the caller's
tailor record from their user id and filters on it; the client never supplies a
tailor id. A tailor holding only ``work_orders.own`` therefore cannot see or
touch anyone else's queue, however the request is shaped.

All routes gate on ``require_permission`` - never the admin>manager>staff ladder,
which the TAILOR role deliberately does not fit.
"""

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, get_db, require_permission
from app.models.production import ProductionOrder
from app.models.user import User
from app.models.workforce import (
    WO_TRANSITIONS,
    ProductionStage,
    Tailor,
    TailorSkill,
    WorkOrder,
    WorkOrderStatus,
)
from app.permissions.service import has_permission
from app.schemas.workforce import (
    AssignRequest,
    CompleteWorkOrderRequest,
    IssueNoteRequest,
    StageCreate,
    StageOut,
    StageUpdate,
    TailorCreate,
    TailorOut,
    TailorSkillIn,
    TailorUpdate,
    TailorWorkload,
    WorkOrderCreate,
    WorkOrderOut,
)
from app.services import workforce as wf
from app.services.audit import log_activity
from app.services.numbering import next_document_number

router = APIRouter(prefix="/api", tags=["workforce"])


def _guard(fn):
    try:
        return fn()
    except wf.WorkOrderError as e:
        raise HTTPException(409, str(e)) from e


def _stage_out(s: ProductionStage) -> StageOut:
    return StageOut(
        id=s.id, code=s.code, name=s.name, sequence=s.sequence,
        default_rate=s.default_rate, is_qc=s.is_qc, is_active=s.is_active,
    )


def _tailor_out(t: Tailor) -> TailorOut:
    return TailorOut(
        id=t.id, code=t.code, name=t.name, phone=t.phone, user_id=t.user_id,
        pay_model=t.pay_model, default_rate=t.default_rate, joined_on=t.joined_on,
        notes=t.notes, is_active=t.is_active,
        skills=[
            TailorSkillIn(name=s.name, stage_id=s.stage_id, proficiency=s.proficiency)
            for s in t.skills
        ],
    )


def _wo_out(w: WorkOrder) -> WorkOrderOut:
    return WorkOrderOut(
        id=w.id, wo_number=w.wo_number, production_order_id=w.production_order_id,
        po_number=w.production_order.po_number if w.production_order else None,
        item_name=(
            w.production_order.item.resolved_name
            if w.production_order and w.production_order.item
            else None
        ),
        stage_id=w.stage_id, stage_name=w.stage.name if w.stage else None,
        tailor_id=w.tailor_id, tailor_name=w.tailor.name if w.tailor else None,
        quantity=w.quantity, completed_quantity=w.completed_quantity,
        status=w.status, sequence=w.sequence, due_date=w.due_date,
        started_at=w.started_at, completed_at=w.completed_at,
        pay_model=w.pay_model, rate=w.rate, hours=w.hours,
        labour_cost=w.labour_cost, is_overdue=w.is_overdue,
        notes=w.notes, issue_note=w.issue_note,
        allowed_transitions=sorted(WO_TRANSITIONS.get(w.status, set()), key=lambda s: s.value),
    )


def _load_wo(db: Session, wo_id: int) -> WorkOrder:
    w = (
        db.query(WorkOrder)
        .options(
            joinedload(WorkOrder.stage), joinedload(WorkOrder.tailor),
            joinedload(WorkOrder.production_order).joinedload(ProductionOrder.item),
        )
        .filter(WorkOrder.id == wo_id)
        .first()
    )
    if not w:
        raise HTTPException(404, "Work order not found")
    return w


def _my_tailor(db: Session, user: User) -> Tailor:
    tailor = db.query(Tailor).filter(Tailor.user_id == user.id).first()
    if not tailor:
        raise HTTPException(404, "Your account isn't linked to a tailor record")
    return tailor


def _assert_may_touch(db: Session, user: User, work_order: WorkOrder) -> None:
    """A tailor may drive only their own work. Managers may drive anyone's.

    Checked here rather than in the query so the failure is an explicit 403
    instead of a confusing 404.
    """
    if has_permission(db, user, "work_orders.assign"):
        return
    tailor = db.query(Tailor).filter(Tailor.user_id == user.id).first()
    if not tailor or work_order.tailor_id != tailor.id:
        raise HTTPException(403, "This work order is not assigned to you")


# ------------------------------------------------------------------- stages


@router.get("/production-stages", response_model=list[StageOut])
def list_stages(
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
    include_inactive: bool = False,
):
    q = db.query(ProductionStage)
    if not include_inactive:
        q = q.filter(ProductionStage.is_active.is_(True))
    return [_stage_out(s) for s in q.order_by(ProductionStage.sequence).all()]


@router.post("/production-stages", response_model=StageOut, status_code=201)
def create_stage(
    payload: StageCreate, db: Session = Depends(get_db),
    _: User = Depends(require_permission("stages.manage")),
):
    if db.query(ProductionStage).filter(ProductionStage.code == payload.code).first():
        raise HTTPException(409, f"A stage with code '{payload.code}' already exists")
    stage = ProductionStage(**payload.model_dump())
    db.add(stage)
    db.commit()
    db.refresh(stage)
    return _stage_out(stage)


@router.patch("/production-stages/{stage_id}", response_model=StageOut)
def update_stage(
    stage_id: int, payload: StageUpdate, db: Session = Depends(get_db),
    _: User = Depends(require_permission("stages.manage")),
):
    stage = db.get(ProductionStage, stage_id)
    if not stage:
        raise HTTPException(404, "Stage not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(stage, field, value)
    db.commit()
    db.refresh(stage)
    return _stage_out(stage)


# ------------------------------------------------------------------ tailors


@router.get("/tailors", response_model=list[TailorOut])
def list_tailors(
    db: Session = Depends(get_db), _: User = Depends(require_permission("tailors.view")),
    is_active: bool | None = None,
):
    q = db.query(Tailor).options(joinedload(Tailor.skills))
    if is_active is not None:
        q = q.filter(Tailor.is_active.is_(is_active))
    return [_tailor_out(t) for t in q.order_by(Tailor.name).all()]


@router.get("/tailors/workload", response_model=list[TailorWorkload])
def tailor_workload(
    db: Session = Depends(get_db), _: User = Depends(require_permission("tailors.view")),
):
    tailors = {t.id: t for t in db.query(Tailor).filter(Tailor.is_active.is_(True)).all()}
    rows = {r["tailor_id"]: r for r in wf.workload(db, list(tailors))}
    return [
        TailorWorkload(
            tailor_id=t.id, name=t.name,
            **{k: rows.get(t.id, {}).get(k, 0) for k in ("active", "pending", "completed", "overdue")},
        )
        for t in tailors.values()
    ]


@router.post("/tailors", response_model=TailorOut, status_code=201)
def create_tailor(
    payload: TailorCreate, db: Session = Depends(get_db),
    _: User = Depends(require_permission("tailors.manage")),
):
    if db.query(Tailor).filter(Tailor.code == payload.code).first():
        raise HTTPException(409, f"A tailor with code '{payload.code}' already exists")
    data = payload.model_dump(exclude={"skills"})
    tailor = Tailor(**data)
    db.add(tailor)
    db.flush()
    for s in payload.skills:
        db.add(TailorSkill(tailor_id=tailor.id, **s.model_dump()))
    db.commit()
    db.refresh(tailor)
    return _tailor_out(tailor)


@router.patch("/tailors/{tailor_id}", response_model=TailorOut)
def update_tailor(
    tailor_id: int, payload: TailorUpdate, db: Session = Depends(get_db),
    _: User = Depends(require_permission("tailors.manage")),
):
    tailor = db.get(Tailor, tailor_id)
    if not tailor:
        raise HTTPException(404, "Tailor not found")
    changes = payload.model_dump(exclude_unset=True, exclude={"skills"})
    for field, value in changes.items():
        setattr(tailor, field, value)
    if payload.skills is not None:
        for existing in list(tailor.skills):
            db.delete(existing)
        db.flush()
        for s in payload.skills:
            db.add(TailorSkill(tailor_id=tailor.id, **s.model_dump()))
    db.commit()
    db.refresh(tailor)
    return _tailor_out(tailor)


# -------------------------------------------------------------- work orders


@router.get("/work-orders", response_model=list[WorkOrderOut])
def list_work_orders(
    db: Session = Depends(get_db), _: User = Depends(require_permission("work_orders.view")),
    production_order_id: int | None = None,
    tailor_id: int | None = None,
    stage_id: int | None = None,
    status: WorkOrderStatus | None = None,
    overdue: bool = False,
    limit: int = Query(100, le=500),
):
    q = db.query(WorkOrder).options(
        joinedload(WorkOrder.stage), joinedload(WorkOrder.tailor),
        joinedload(WorkOrder.production_order).joinedload(ProductionOrder.item),
    )
    if production_order_id:
        q = q.filter(WorkOrder.production_order_id == production_order_id)
    if tailor_id:
        q = q.filter(WorkOrder.tailor_id == tailor_id)
    if stage_id:
        q = q.filter(WorkOrder.stage_id == stage_id)
    if status:
        q = q.filter(WorkOrder.status == status)
    rows = q.order_by(WorkOrder.production_order_id, WorkOrder.sequence).limit(limit).all()
    if overdue:
        rows = [w for w in rows if w.is_overdue]
    return [_wo_out(w) for w in rows]


@router.get("/work-orders/mine", response_model=list[WorkOrderOut])
def my_work_orders(
    db: Session = Depends(get_db), user: User = Depends(require_permission("work_orders.own")),
    include_done: bool = False,
):
    """The caller's own queue.

    The tailor is resolved from the authenticated user, never from a query
    parameter - a tailor cannot ask for someone else's work by changing an id.
    """
    tailor = _my_tailor(db, user)
    q = (
        db.query(WorkOrder)
        .options(
            joinedload(WorkOrder.stage),
            joinedload(WorkOrder.production_order).joinedload(ProductionOrder.item),
            joinedload(WorkOrder.tailor),
        )
        .filter(WorkOrder.tailor_id == tailor.id)
    )
    if not include_done:
        q = q.filter(WorkOrder.status.notin_([WorkOrderStatus.COMPLETED, WorkOrderStatus.CANCELLED]))
    return [_wo_out(w) for w in q.order_by(WorkOrder.due_date, WorkOrder.sequence).all()]


@router.post("/work-orders", response_model=WorkOrderOut, status_code=201)
def create_work_order(
    payload: WorkOrderCreate, db: Session = Depends(get_db),
    user: User = Depends(require_permission("work_orders.assign")),
):
    order = db.get(ProductionOrder, payload.production_order_id)
    if not order:
        raise HTTPException(404, "Production order not found")
    stage = db.get(ProductionStage, payload.stage_id)
    if not stage:
        raise HTTPException(404, "Production stage not found")

    tailor = None
    if payload.tailor_id:
        tailor = db.get(Tailor, payload.tailor_id)
        if not tailor:
            raise HTTPException(404, "Tailor not found")

    pay_model, rate = wf.resolve_rate(tailor, stage)
    wo = WorkOrder(
        wo_number=next_document_number(db, WorkOrder, WorkOrder.wo_number, "WO"),
        production_order_id=order.id, stage_id=stage.id,
        quantity=payload.quantity or order.planned_quantity,
        sequence=payload.sequence if payload.sequence is not None else stage.sequence,
        due_date=payload.due_date, notes=payload.notes,
        pay_model=pay_model, rate=payload.rate if payload.rate is not None else rate,
    )
    db.add(wo)
    db.flush()
    if tailor:
        _guard(lambda: wf.assign(db, wo, tailor, user_id=user.id, rate=payload.rate))

    log_activity(db, action="work_order.create", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="WorkOrder", entity_id=wo.id,
                 details={"wo_number": wo.wo_number, "stage": stage.code,
                          "tailor_id": payload.tailor_id})
    db.commit()
    return _wo_out(_load_wo(db, wo.id))


@router.post("/work-orders/{wo_id}/assign", response_model=WorkOrderOut)
def assign_work_order(
    wo_id: int, payload: AssignRequest, db: Session = Depends(get_db),
    user: User = Depends(require_permission("work_orders.assign")),
):
    wo = _load_wo(db, wo_id)
    tailor = db.get(Tailor, payload.tailor_id)
    if not tailor:
        raise HTTPException(404, "Tailor not found")
    _guard(lambda: wf.assign(db, wo, tailor, user_id=user.id, rate=payload.rate))
    log_activity(db, action="work_order.assign", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="WorkOrder", entity_id=wo.id, details={"tailor_id": tailor.id})
    db.commit()
    return _wo_out(_load_wo(db, wo_id))


@router.post("/work-orders/{wo_id}/start", response_model=WorkOrderOut)
def start_work_order(
    wo_id: int, db: Session = Depends(get_db),
    user: User = Depends(require_permission("work_orders.own")),
):
    wo = _load_wo(db, wo_id)
    _assert_may_touch(db, user, wo)
    _guard(lambda: wf.start(db, wo))
    log_activity(db, action="work_order.start", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="WorkOrder", entity_id=wo.id, details={})
    db.commit()
    return _wo_out(_load_wo(db, wo_id))


@router.post("/work-orders/{wo_id}/pause", response_model=WorkOrderOut)
def pause_work_order(
    wo_id: int, payload: IssueNoteRequest, db: Session = Depends(get_db),
    user: User = Depends(require_permission("work_orders.own")),
):
    wo = _load_wo(db, wo_id)
    _assert_may_touch(db, user, wo)
    _guard(lambda: wf.pause(db, wo, payload.reason))
    log_activity(db, action="work_order.pause", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="WorkOrder", entity_id=wo.id, details={"reason": payload.reason})
    db.commit()
    return _wo_out(_load_wo(db, wo_id))


@router.post("/work-orders/{wo_id}/complete", response_model=WorkOrderOut)
def complete_work_order(
    wo_id: int, payload: CompleteWorkOrderRequest, db: Session = Depends(get_db),
    user: User = Depends(require_permission("work_orders.own")),
):
    wo = _load_wo(db, wo_id)
    _assert_may_touch(db, user, wo)
    _guard(lambda: wf.complete(db, wo, payload.completed_quantity, hours=payload.hours))
    log_activity(db, action="work_order.complete", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="WorkOrder", entity_id=wo.id,
                 details={"completed": wo.completed_quantity, "labour_cost": wo.labour_cost})
    db.commit()
    return _wo_out(_load_wo(db, wo_id))


@router.post("/work-orders/{wo_id}/report-issue", response_model=WorkOrderOut)
def report_issue(
    wo_id: int, payload: IssueNoteRequest, db: Session = Depends(get_db),
    user: User = Depends(require_permission("work_orders.own")),
):
    """A tailor flags a problem without changing status - the manager decides."""
    wo = _load_wo(db, wo_id)
    _assert_may_touch(db, user, wo)
    if not (payload.reason or "").strip():
        raise HTTPException(400, "Describe the issue you're reporting")
    wo.issue_note = payload.reason
    log_activity(db, action="work_order.issue", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="WorkOrder", entity_id=wo.id, details={"issue": payload.reason})
    db.commit()
    return _wo_out(_load_wo(db, wo_id))


@router.post("/work-orders/{wo_id}/cancel", response_model=WorkOrderOut)
def cancel_work_order(
    wo_id: int, payload: IssueNoteRequest, db: Session = Depends(get_db),
    user: User = Depends(require_permission("work_orders.assign")),
):
    wo = _load_wo(db, wo_id)
    _guard(lambda: wf.cancel(db, wo, payload.reason))
    log_activity(db, action="work_order.cancel", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="WorkOrder", entity_id=wo.id, details={"reason": payload.reason})
    db.commit()
    return _wo_out(_load_wo(db, wo_id))
