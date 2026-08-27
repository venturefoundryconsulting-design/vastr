"""Work order lifecycle and tailor workload.

Moves no inventory. A work order records who is doing which stage of which
production order, and what that labour costs - material custody stays with the
production order, because tailors are resources rather than stock locations.

Status is never assigned directly; every change goes through ``transition``,
which validates against WO_TRANSITIONS the same way production orders do.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.money import money, to_decimal
from app.models.production import ProductionOrder
from app.models.workforce import (
    WO_TRANSITIONS,
    PayModel,
    ProductionStage,
    Tailor,
    WorkOrder,
    WorkOrderStatus,
)


class WorkOrderError(ValueError):
    """A work order rule was violated. Message is user-facing."""


class InvalidWorkOrderTransition(WorkOrderError):
    pass


def assert_transition(current: WorkOrderStatus, target: WorkOrderStatus) -> None:
    if current == target:
        raise InvalidWorkOrderTransition(f"This work order is already {target.value}")
    allowed = WO_TRANSITIONS.get(current, set())
    if target not in allowed:
        if not allowed:
            raise InvalidWorkOrderTransition(
                f"A {current.value} work order is final and cannot change state."
            )
        raise InvalidWorkOrderTransition(
            f"Cannot go from {current.value} to {target.value}. From {current.value} you can "
            f"move to: {', '.join(sorted(s.value for s in allowed))}."
        )


def resolve_rate(tailor: Tailor | None, stage: ProductionStage) -> tuple[PayModel | None, Decimal]:
    """Pick the rate to freeze onto a work order at assignment.

    The tailor's own rate wins; the stage's default is the fallback so a boutique
    can set "stitching is 800" once instead of on every tailor. Whatever is
    chosen is copied onto the work order, so changing a rate later never rewrites
    the cost of work already done.
    """
    if tailor is None:
        return None, to_decimal(stage.default_rate)
    rate = to_decimal(tailor.default_rate)
    if rate <= 0:
        rate = to_decimal(stage.default_rate)
    return tailor.pay_model, rate


def assign(
    db: Session,
    work_order: WorkOrder,
    tailor: Tailor,
    *,
    user_id: int | None = None,
    rate: Decimal | None = None,
) -> None:
    """Put a tailor on a work order and freeze the pay terms."""
    if not tailor.is_active:
        raise WorkOrderError(f"{tailor.name} is not an active tailor")
    assert_transition(work_order.status, WorkOrderStatus.ASSIGNED)

    pay_model, resolved = resolve_rate(tailor, work_order.stage)
    work_order.tailor_id = tailor.id
    work_order.pay_model = pay_model
    work_order.rate = money(rate if rate is not None else resolved)
    work_order.status = WorkOrderStatus.ASSIGNED
    work_order.assigned_by_id = user_id
    db.flush()


def start(db: Session, work_order: WorkOrder) -> None:
    if work_order.tailor_id is None:
        raise WorkOrderError("Assign a tailor before starting this work order")
    assert_transition(work_order.status, WorkOrderStatus.IN_PROGRESS)
    work_order.status = WorkOrderStatus.IN_PROGRESS
    if work_order.started_at is None:
        work_order.started_at = datetime.now(timezone.utc)
    db.flush()


def pause(db: Session, work_order: WorkOrder, reason: str | None = None) -> None:
    assert_transition(work_order.status, WorkOrderStatus.PAUSED)
    work_order.status = WorkOrderStatus.PAUSED
    if reason:
        work_order.issue_note = reason
    db.flush()


def complete(
    db: Session,
    work_order: WorkOrder,
    completed_quantity: Decimal | int | float | str | None = None,
    *,
    hours: Decimal | None = None,
) -> None:
    """Finish a work order, recording how much was actually done.

    Defaults to the full quantity, because that is the ordinary case; a smaller
    number is accepted so a stage that only got through part of the batch is
    honestly recorded rather than rounded up.
    """
    assert_transition(work_order.status, WorkOrderStatus.COMPLETED)

    qty = (
        to_decimal(completed_quantity)
        if completed_quantity is not None
        else to_decimal(work_order.quantity)
    )
    if qty <= 0:
        raise WorkOrderError("Completed quantity must be greater than zero")
    if qty > to_decimal(work_order.quantity):
        raise WorkOrderError(
            f"Cannot complete {qty}: this work order covers {work_order.quantity}."
        )

    work_order.completed_quantity = qty
    if hours is not None:
        work_order.hours = to_decimal(hours)
    work_order.status = WorkOrderStatus.COMPLETED
    work_order.completed_at = datetime.now(timezone.utc)
    db.flush()


def send_to_rework(db: Session, work_order: WorkOrder, reason: str) -> None:
    """Re-open completed work. Phase 3G's QC failure path calls this."""
    if not (reason or "").strip():
        raise WorkOrderError("A reason is required when sending work back for rework")
    assert_transition(work_order.status, WorkOrderStatus.REWORK)
    work_order.status = WorkOrderStatus.REWORK
    work_order.issue_note = reason
    work_order.completed_at = None
    db.flush()


def cancel(db: Session, work_order: WorkOrder, reason: str | None = None) -> None:
    assert_transition(work_order.status, WorkOrderStatus.CANCELLED)
    work_order.status = WorkOrderStatus.CANCELLED
    if reason:
        work_order.issue_note = reason
    db.flush()


def workload(db: Session, tailor_ids: list[int] | None = None) -> list[dict]:
    """Per-tailor counts for the production dashboard.

    One grouped query rather than a query per tailor, so the board stays cheap as
    the roster grows.
    """
    q = (
        db.query(
            WorkOrder.tailor_id,
            WorkOrder.status,
            func.count(WorkOrder.id),
        )
        .filter(WorkOrder.tailor_id.isnot(None))
        .group_by(WorkOrder.tailor_id, WorkOrder.status)
    )
    if tailor_ids:
        q = q.filter(WorkOrder.tailor_id.in_(tailor_ids))

    by_tailor: dict[int, dict] = {}
    for tailor_id, status, count in q.all():
        entry = by_tailor.setdefault(
            tailor_id,
            {"tailor_id": tailor_id, "active": 0, "pending": 0, "completed": 0, "overdue": 0},
        )
        if status in (WorkOrderStatus.IN_PROGRESS, WorkOrderStatus.REWORK):
            entry["active"] += count
        elif status in (WorkOrderStatus.PENDING, WorkOrderStatus.ASSIGNED, WorkOrderStatus.PAUSED):
            entry["pending"] += count
        elif status == WorkOrderStatus.COMPLETED:
            entry["completed"] += count

    overdue_q = (
        db.query(WorkOrder.tailor_id, func.count(WorkOrder.id))
        .filter(
            WorkOrder.tailor_id.isnot(None),
            WorkOrder.due_date < date.today(),
            WorkOrder.status.notin_([WorkOrderStatus.COMPLETED, WorkOrderStatus.CANCELLED]),
        )
        .group_by(WorkOrder.tailor_id)
    )
    if tailor_ids:
        overdue_q = overdue_q.filter(WorkOrder.tailor_id.in_(tailor_ids))
    for tailor_id, count in overdue_q.all():
        by_tailor.setdefault(
            tailor_id,
            {"tailor_id": tailor_id, "active": 0, "pending": 0, "completed": 0, "overdue": 0},
        )["overdue"] = count

    return list(by_tailor.values())


def labour_cost_for_order(db: Session, order: ProductionOrder) -> Decimal:
    """Total labour booked against a production order - Phase 3H reads this."""
    rows = db.query(WorkOrder).filter(WorkOrder.production_order_id == order.id).all()
    return money(sum((wo.labour_cost for wo in rows), Decimal("0")))
