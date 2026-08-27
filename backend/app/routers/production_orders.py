"""Production order planning API.

PHASE 3C IS READ-ONLY WITH RESPECT TO INVENTORY. No endpoint in this module
reserves, issues, consumes or moves stock, and none of them import
apply_stock_delta. `tests/test_production_orders.py::test_inventory_is_never_touched`
asserts that by snapshotting stock_levels and stock_movements around the whole
lifecycle.

Status is never settable as a field. Every change goes through an explicit
transition endpoint that validates against the state machine server-side, so a
client cannot PATCH its way to COMPLETED.
"""

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, require_permission
from app.models.audit import AuditLog
from app.models.bom import Bom, BomStatus, BomVersion
from app.models.outlet import Outlet
from app.models.product import Item
from app.models.production_output import ProductionOutput
from app.models.production import (
    ALLOWED_TRANSITIONS,
    ProductionOrder,
    ProductionOrderMaterial,
    ProductionStatus,
)
from app.models.user import User
from app.schemas.production import (
    AvailabilityOut,
    CloseShortRequest,
    HistoryEntry,
    MaterialLine,
    ProductionOrderCreate,
    ProductionOrderDetail,
    ProductionOrderOut,
    ProductionOrderUpdate,
    SnapshotLine,
    TraceStep,
    OutputOut,
    OutputRequest,
    TransitionRequest,
)
from app.services import material_flow
from app.services import production as prod
from app.services.bom import CircularBomError
from app.services.audit import log_activity
from app.services.numbering import next_document_number

router = APIRouter(prefix="/api/production-orders", tags=["production"])


# ------------------------------------------------------------------- helpers


def _load(db: Session, order_id: int) -> ProductionOrder:
    order = (
        db.query(ProductionOrder)
        .options(
            joinedload(ProductionOrder.item),
            joinedload(ProductionOrder.location),
            joinedload(ProductionOrder.uom),
            joinedload(ProductionOrder.bom_version),
            joinedload(ProductionOrder.materials).joinedload(ProductionOrderMaterial.item),
            joinedload(ProductionOrder.materials).joinedload(ProductionOrderMaterial.uom),
            joinedload(ProductionOrder.materials).joinedload(ProductionOrderMaterial.parent_item),
        )
        .filter(ProductionOrder.id == order_id)
        .first()
    )
    if not order:
        raise HTTPException(404, "Production order not found")
    return order


def _out(order: ProductionOrder) -> ProductionOrderOut:
    return ProductionOrderOut(
        id=order.id, po_number=order.po_number, item_id=order.item_id,
        item_sku=order.item.sku if order.item else None,
        item_name=order.item.resolved_name if order.item else None,
        bom_id=order.bom_id, bom_version_id=order.bom_version_id,
        bom_version_no=order.bom_version.version_no if order.bom_version else None,
        planned_quantity=order.planned_quantity, produced_quantity=order.produced_quantity,
        cancelled_quantity=order.cancelled_quantity, remaining_quantity=order.remaining_quantity,
        uom_id=order.uom_id, uom_code=order.uom.code if order.uom else None,
        location_id=order.location_id,
        location_name=order.location.name if order.location else None,
        planned_start=order.planned_start, planned_completion=order.planned_completion,
        actual_start=order.actual_start, actual_completion=order.actual_completion,
        status=order.status, priority=order.priority, notes=order.notes,
        is_editable=order.is_editable,
        allowed_transitions=sorted(ALLOWED_TRANSITIONS.get(order.status, set()), key=lambda s: s.value),
        material_count=len([m for m in order.materials if not m.is_subassembly]),
        created_by_id=order.created_by_id, released_by_id=order.released_by_id,
        released_at=order.released_at, close_short_reason=order.close_short_reason,
        closed_short_at=order.closed_short_at,
        created_at=order.created_at, updated_at=order.updated_at,
    )


def _snapshot(order: ProductionOrder) -> list[SnapshotLine]:
    return [
        SnapshotLine(
            id=m.id, item_id=m.item_id,
            sku=m.item.sku if m.item else None,
            name=m.item.resolved_name if m.item else None,
            quantity_per_unit=m.quantity_per_unit, base_quantity=m.base_quantity,
            scrap_pct=m.scrap_pct, expected_wastage=m.expected_wastage,
            planned_quantity=m.planned_quantity, uom_id=m.uom_id,
            uom_code=m.uom.code if m.uom else None,
            level=m.level, parent_item_id=m.parent_item_id,
            parent_sku=m.parent_item.sku if m.parent_item else None,
            is_optional=m.is_optional, is_subassembly=m.is_subassembly, sequence=m.sequence,
        )
        for m in order.materials
    ]


def _availability(db: Session, order: ProductionOrder) -> AvailabilityOut:
    result = prod.availability(db, order)
    return AvailabilityOut(
        overall=result["overall"], lines=[MaterialLine(**line) for line in result["lines"]]
    )


def _transition(
    db: Session, order: ProductionOrder, target: ProductionStatus, user: User,
    *, reason: str | None = None, extra: dict | None = None,
) -> None:
    """The single chokepoint for status change. Validates, then audits."""
    previous = order.status
    try:
        prod.assert_transition(previous, target)
    except prod.InvalidTransition as e:
        raise HTTPException(409, str(e)) from e

    order.status = target
    log_activity(
        db, action=f"production.{target.value}", tenant_id=user.tenant_id, user_id=user.id,
        entity_type="ProductionOrder", entity_id=order.id,
        details={"from": previous.value, "to": target.value, "reason": reason, **(extra or {})},
    )


# --------------------------------------------------------------------- CRUD


@router.get("", response_model=list[ProductionOrderOut])
def list_orders(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("production.view")),
    status: ProductionStatus | None = None,
    item_id: int | None = None,
    location_id: int | None = None,
    priority: str | None = None,
    q: str | None = Query(None, description="Matches production number, item SKU or name"),
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    query = db.query(ProductionOrder).options(
        joinedload(ProductionOrder.item), joinedload(ProductionOrder.location),
        joinedload(ProductionOrder.uom), joinedload(ProductionOrder.bom_version),
    )
    if status:
        query = query.filter(ProductionOrder.status == status)
    if item_id:
        query = query.filter(ProductionOrder.item_id == item_id)
    if location_id:
        query = query.filter(ProductionOrder.location_id == location_id)
    if priority:
        query = query.filter(ProductionOrder.priority == priority)
    if q:
        like = f"%{q.strip()}%"
        query = query.join(Item, Item.id == ProductionOrder.item_id).filter(
            ProductionOrder.po_number.ilike(like) | Item.sku.ilike(like) | Item.name.ilike(like)
        )
    orders = query.order_by(ProductionOrder.id.desc()).offset(offset).limit(limit).all()
    return [_out(o) for o in orders]


@router.get("/{order_id}", response_model=ProductionOrderDetail)
def get_order(
    order_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("production.view")),
):
    order = _load(db, order_id)
    detail = ProductionOrderDetail(**_out(order).model_dump())
    detail.materials = _snapshot(order)
    detail.availability = _availability(db, order)
    return detail


@router.post("", response_model=ProductionOrderDetail, status_code=201)
def create_order(
    payload: ProductionOrderCreate, db: Session = Depends(get_db),
    user: User = Depends(require_permission("production.create")),
):
    """Creates in DRAFT and snapshots the material requirement immediately.

    A shortage does NOT block creation - a boutique legitimately plans a run
    before the lace arrives. The shortage is reported, not enforced.
    """
    item = db.get(Item, payload.item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    if not db.get(Outlet, payload.location_id):
        raise HTTPException(404, "Location not found")

    bom = db.query(Bom).filter(Bom.item_id == payload.item_id).first()
    version = None
    if payload.bom_version_id:
        version = db.get(BomVersion, payload.bom_version_id)
        if not version:
            raise HTTPException(404, "BOM version not found")
        if not bom or version.bom_id != bom.id:
            raise HTTPException(400, "That BOM version does not belong to this item")
    elif bom:
        version = next((v for v in bom.versions if v.status == BomStatus.ACTIVE), None)
        if not version:
            raise HTTPException(
                400,
                f"{item.sku} has a bill of materials but no active version. "
                "Activate one before planning production.",
            )
    else:
        raise HTTPException(
            400,
            f"{item.sku} has no bill of materials. Create one before planning production.",
        )

    order = ProductionOrder(
        po_number=next_document_number(db, ProductionOrder, ProductionOrder.po_number, "PRD"),
        item_id=payload.item_id, bom_id=bom.id if bom else None,
        bom_version_id=version.id if version else None,
        planned_quantity=payload.planned_quantity,
        uom_id=payload.uom_id or item.stock_uom_id,
        location_id=payload.location_id,
        planned_start=payload.planned_start, planned_completion=payload.planned_completion,
        priority=payload.priority, notes=payload.notes,
        status=ProductionStatus.DRAFT, created_by_id=user.id,
    )
    db.add(order)
    db.flush()

    try:
        prod.rebuild_materials(db, order)
    except (prod.ProductionError, CircularBomError) as e:
        raise HTTPException(400, str(e)) from e

    log_activity(
        db, action="production.create", tenant_id=user.tenant_id, user_id=user.id,
        entity_type="ProductionOrder", entity_id=order.id,
        details={
            "po_number": order.po_number, "item_sku": item.sku,
            "quantity": order.planned_quantity,
            "bom_version": version.version_no if version else None,
        },
    )
    db.commit()
    return get_order(order.id, db, user)


@router.patch("/{order_id}", response_model=ProductionOrderDetail)
def update_order(
    order_id: int, payload: ProductionOrderUpdate, db: Session = Depends(get_db),
    user: User = Depends(require_permission("production.edit")),
):
    order = _load(db, order_id)
    if not order.is_editable:
        raise HTTPException(
            409,
            f"A {order.status.value} production order cannot be edited. "
            "Only draft and planned orders are editable.",
        )

    changes = payload.model_dump(exclude_unset=True)
    if "bom_version_id" in changes and changes["bom_version_id"]:
        version = db.get(BomVersion, changes["bom_version_id"])
        if not version or version.bom_id != order.bom_id:
            raise HTTPException(400, "That BOM version does not belong to this order's item")

    for field, value in changes.items():
        setattr(order, field, value)
    db.flush()

    # Quantity or recipe changed, so the requirement snapshot is stale.
    if {"planned_quantity", "bom_version_id"} & set(changes):
        try:
            prod.rebuild_materials(db, order)
        except prod.ProductionError as e:
            raise HTTPException(400, str(e)) from e

    log_activity(
        db, action="production.update", tenant_id=user.tenant_id, user_id=user.id,
        entity_type="ProductionOrder", entity_id=order.id,
        details={"fields": sorted(changes)},
    )
    db.commit()
    return get_order(order_id, db, user)


# --------------------------------------------------------------- transitions


@router.post("/{order_id}/plan", response_model=ProductionOrderDetail)
def plan_order(
    order_id: int, db: Session = Depends(get_db),
    user: User = Depends(require_permission("production.plan")),
):
    order = _load(db, order_id)
    _transition(db, order, ProductionStatus.PLANNED, user)
    db.commit()
    return get_order(order_id, db, user)


@router.post("/{order_id}/release", response_model=ProductionOrderDetail)
def release_order(
    order_id: int, db: Session = Depends(get_db),
    user: User = Depends(require_permission("production.release")),
):
    """Releasing freezes the plan. It does NOT reserve anything - that is 3D.

    A shortage is reported but does not block release: the business may
    deliberately release ahead of a delivery.
    """
    order = _load(db, order_id)
    if not order.materials:
        raise HTTPException(400, "This production order has no material requirements to release")

    avail = prod.availability(db, order)
    _transition(
        db, order, ProductionStatus.RELEASED, user,
        extra={"material_status": avail["overall"].value},
    )
    order.released_by_id = user.id
    order.released_at = datetime.now(timezone.utc)

    # First actual use of this recipe: freeze it permanently. Phase 3B defined
    # is_locked and deliberately left setting it to whoever consumed a version.
    if order.bom_version_id:
        version = db.get(BomVersion, order.bom_version_id)
        if version and not version.is_locked:
            version.is_locked = True

    db.commit()
    return get_order(order_id, db, user)


@router.post("/{order_id}/start", response_model=ProductionOrderDetail)
def start_order(
    order_id: int, db: Session = Depends(get_db),
    user: User = Depends(require_permission("production.release")),
):
    """RELEASED -> IN_PROGRESS. Records the start time; moves no material."""
    order = _load(db, order_id)
    _transition(db, order, ProductionStatus.IN_PROGRESS, user)
    if not order.actual_start:
        order.actual_start = datetime.now(timezone.utc)
    db.commit()
    return get_order(order_id, db, user)


@router.post("/{order_id}/hold", response_model=ProductionOrderDetail)
def hold_order(
    order_id: int, payload: TransitionRequest, db: Session = Depends(get_db),
    user: User = Depends(require_permission("production.hold")),
):
    order = _load(db, order_id)
    resume_to = order.status
    _transition(db, order, ProductionStatus.ON_HOLD, user, reason=payload.reason)
    order.resume_status = resume_to
    db.commit()
    return get_order(order_id, db, user)


@router.post("/{order_id}/resume", response_model=ProductionOrderDetail)
def resume_order(
    order_id: int, db: Session = Depends(get_db),
    user: User = Depends(require_permission("production.hold")),
):
    order = _load(db, order_id)
    if order.status != ProductionStatus.ON_HOLD:
        raise HTTPException(409, "Only an order that is on hold can be resumed")
    target = order.resume_status or ProductionStatus.RELEASED
    _transition(db, order, target, user)
    order.resume_status = None
    db.commit()
    return get_order(order_id, db, user)


@router.post("/{order_id}/cancel", response_model=ProductionOrderDetail)
def cancel_order(
    order_id: int, payload: TransitionRequest, db: Session = Depends(get_db),
    user: User = Depends(require_permission("production.cancel")),
):
    """Cancels the order and frees every outstanding reservation - Rule 8.

    Already-issued material is deliberately untouched: it has physically left the
    store and comes back through a return, not by releasing a promise.
    """
    order = _load(db, order_id)
    _transition(db, order, ProductionStatus.CANCELLED, user, reason=payload.reason)
    freed = material_flow.release_all_for_order(
        db, order, user_id=user.id, reason=f"Production order cancelled: {payload.reason or ''}".strip()
    )
    if freed:
        log_activity(
            db, action="materials.release_all", tenant_id=user.tenant_id, user_id=user.id,
            entity_type="ProductionOrder", entity_id=order.id,
            details={"freed": freed, "trigger": "cancel"},
        )
    db.commit()
    return get_order(order_id, db, user)


@router.post("/{order_id}/close-short", response_model=ProductionOrderDetail)
def close_short(
    order_id: int, payload: CloseShortRequest, db: Session = Depends(get_db),
    user: User = Depends(require_permission("production.close_short")),
):
    """Ends an order below its planned quantity - deliberately, never silently.

    Records what was actually produced, what is being abandoned, who decided and
    when. The schema makes produced_quantity and reason mandatory.
    """
    order = _load(db, order_id)
    if payload.produced_quantity > order.planned_quantity:
        raise HTTPException(
            400,
            f"Produced quantity ({payload.produced_quantity}) cannot exceed the planned "
            f"quantity ({order.planned_quantity}).",
        )

    cancelled = Decimal(str(order.planned_quantity)) - Decimal(str(payload.produced_quantity))
    _transition(
        db, order, ProductionStatus.CLOSED_SHORT, user, reason=payload.reason,
        extra={"produced": payload.produced_quantity, "cancelled": cancelled},
    )
    order.produced_quantity = payload.produced_quantity
    order.cancelled_quantity = cancelled
    order.close_short_reason = payload.reason
    order.closed_short_by_id = user.id
    order.closed_short_at = datetime.now(timezone.utc)
    order.actual_completion = order.actual_completion or datetime.now(timezone.utc)

    # The remaining material was promised for units that will never be built.
    freed = material_flow.release_all_for_order(
        db, order, user_id=user.id, reason=f"Closed short: {payload.reason}"
    )
    if freed:
        log_activity(
            db, action="materials.release_all", tenant_id=user.tenant_id, user_id=user.id,
            entity_type="ProductionOrder", entity_id=order.id,
            details={"freed": freed, "trigger": "close_short"},
        )
    db.commit()
    return get_order(order_id, db, user)


# ------------------------------------------------------------- projections


@router.get("/{order_id}/availability", response_model=AvailabilityOut)
def order_availability(
    order_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("production.view")),
):
    """Read-only. Safe to poll - reserves nothing."""
    return _availability(db, _load(db, order_id))


@router.get("/{order_id}/trace/{item_id}", response_model=list[list[TraceStep]])
def requirement_trace(
    order_id: int, item_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("production.view")),
):
    """Answers "why do I need 45 m of silk?" as an explicit chain."""
    order = _load(db, order_id)
    chains = prod.trace(db, order, item_id)
    if not chains:
        raise HTTPException(404, "That material is not required by this production order")
    return [[TraceStep(**step) for step in chain] for chain in chains]


@router.get("/{order_id}/history", response_model=list[HistoryEntry])
def order_history(
    order_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("production.view")),
):
    """State-change trail, read from the shared audit log."""
    _load(db, order_id)
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "ProductionOrder", AuditLog.entity_id == order_id)
        .order_by(AuditLog.id)
        .all()
    )
    return [
        HistoryEntry(action=r.action, user_id=r.user_id, created_at=r.created_at, details=r.details)
        for r in rows
    ]


# ------------------------------------------------------------------- output


@router.get("/{order_id}/outputs", response_model=list[OutputOut])
def list_outputs(
    order_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("production.view")),
):
    _load(db, order_id)
    rows = (
        db.query(ProductionOutput)
        .options(joinedload(ProductionOutput.item), joinedload(ProductionOutput.uom))
        .filter(ProductionOutput.production_order_id == order_id)
        .order_by(ProductionOutput.id)
        .all()
    )
    return [
        OutputOut(
            id=r.id, production_order_id=r.production_order_id, item_id=r.item_id,
            sku=r.item.sku if r.item else None,
            name=r.item.resolved_name if r.item else None,
            location_id=r.location_id, quantity=r.quantity, uom_id=r.uom_id,
            uom_code=r.uom.code if r.uom else None,
            stock_movement_id=r.stock_movement_id, note=r.note,
            produced_by_id=r.produced_by_id, created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/{order_id}/output", response_model=ProductionOrderDetail)
def record_output(
    order_id: int, payload: OutputRequest, db: Session = Depends(get_db),
    user: User = Depends(require_permission("production.output")),
):
    """Put finished goods into stock and advance progress.

    Below plan the order becomes PARTIALLY_COMPLETED and stays there - stopping
    short is a decision, made explicitly through close-short. Reaching plan
    completes the order, because nothing is being abandoned.
    """
    order = _load(db, order_id)
    previous = order.status
    try:
        rec = prod.record_output(
            db, order, payload.quantity, user_id=user.id,
            location_id=payload.location_id, note=payload.note,
        )
    except prod.ProductionError as e:
        raise HTTPException(409, str(e)) from e

    log_activity(
        db, action="production.output", tenant_id=user.tenant_id, user_id=user.id,
        entity_type="ProductionOrder", entity_id=order.id,
        details={
            "quantity": payload.quantity, "output_id": rec.id,
            "movement_id": rec.stock_movement_id,
            "from": previous.value, "to": order.status.value,
            "produced_total": order.produced_quantity,
        },
    )
    db.commit()
    return get_order(order_id, db, user)


@router.post("/{order_id}/complete", response_model=ProductionOrderDetail)
def complete_order(
    order_id: int, db: Session = Depends(get_db),
    user: User = Depends(require_permission("production.complete")),
):
    """Close an order that has met its planned quantity.

    Refuses below plan - that path is close-short, which requires a reason.
    """
    order = _load(db, order_id)
    previous = order.status
    try:
        prod.complete_order(db, order)
    except prod.InvalidTransition as e:
        raise HTTPException(409, str(e)) from e
    except prod.ProductionError as e:
        raise HTTPException(409, str(e)) from e

    log_activity(
        db, action="production.completed", tenant_id=user.tenant_id, user_id=user.id,
        entity_type="ProductionOrder", entity_id=order.id,
        details={"from": previous.value, "to": order.status.value},
    )
    db.commit()
    return get_order(order_id, db, user)
