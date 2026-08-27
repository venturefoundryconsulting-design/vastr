"""Material reservation, issue, consumption and return.

Mounted under /api/production-orders/{id}/... - material flow belongs to an
order, and a top-level /api/reservations would invite operating on it without one.

EVERY MUTATION IS ONE TRANSACTION. The service layer flushes but never commits;
these handlers commit exactly once at the end. A stock movement and its
production record therefore land together or not at all - there is no path that
leaves a ledger row without its paperwork.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, require_permission
from app.models.material_flow import (
    ProductionMaterialConsumption,
    ProductionMaterialIssue,
    ProductionMaterialReturn,
    StockReservation,
)
from app.models.production import ProductionOrder, ProductionOrderMaterial
from app.models.user import User
from app.permissions.service import has_permission
from app.schemas.material_flow import (
    ConsumeRequest,
    ConsumptionOut,
    IssueOut,
    IssueRequest,
    MaterialPosition,
    OrderMaterialSummary,
    ReleaseRequest,
    ReservationOut,
    ReserveRequest,
    ReturnOut,
    ReturnRequest,
)
from app.services import material_flow as mf
from app.services.audit import log_activity

router = APIRouter(prefix="/api/production-orders", tags=["materials"])


def _order(db: Session, order_id: int) -> ProductionOrder:
    order = (
        db.query(ProductionOrder)
        .options(
            joinedload(ProductionOrder.materials).joinedload(ProductionOrderMaterial.item),
            joinedload(ProductionOrder.materials).joinedload(ProductionOrderMaterial.uom),
        )
        .filter(ProductionOrder.id == order_id)
        .first()
    )
    if not order:
        raise HTTPException(404, "Production order not found")
    return order


def _audit(db: Session, user: User, action: str, order: ProductionOrder, **details) -> None:
    log_activity(
        db, action=action, tenant_id=user.tenant_id, user_id=user.id,
        entity_type="ProductionOrder", entity_id=order.id,
        details={"po_number": order.po_number, **details},
    )


def _guard(fn):
    """Translate a service rule violation into a 409 with its own message.

    409 rather than 400: these are conflicts with the current state of the world
    (someone else took the stock, more was consumed than issued), not malformed
    requests, and the messages carry the numbers the user needs.
    """
    try:
        return fn()
    except mf.MaterialFlowError as e:
        raise HTTPException(409, str(e)) from e


# ------------------------------------------------------------------ read side


@router.get("/{order_id}/materials", response_model=OrderMaterialSummary)
def material_summary(
    order_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("materials.view")),
):
    """Required / reserved / issued / consumed / returned / still-with-production."""
    order = _order(db, order_id)
    lines = [
        MaterialPosition(**mf.material_position(db, m))
        for m in order.materials
        if not m.is_subassembly
    ]
    return OrderMaterialSummary(
        production_order_id=order.id, po_number=order.po_number,
        status=order.status, lines=lines,
        fully_reserved=all(line.remaining_to_reserve == 0 for line in lines) if lines else False,
        fully_issued=all(line.remaining_to_issue == 0 for line in lines) if lines else False,
    )


@router.get("/{order_id}/reservations", response_model=list[ReservationOut])
def list_reservations(
    order_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("materials.view")),
):
    _order(db, order_id)
    rows = (
        db.query(StockReservation)
        .options(joinedload(StockReservation.item), joinedload(StockReservation.uom))
        .filter(StockReservation.production_order_id == order_id)
        .order_by(StockReservation.id)
        .all()
    )
    return [
        ReservationOut(
            id=r.id, production_order_material_id=r.production_order_material_id,
            item_id=r.item_id, sku=r.item.sku if r.item else None,
            name=r.item.resolved_name if r.item else None,
            location_id=r.location_id, quantity=r.quantity,
            issued_quantity=r.issued_quantity, outstanding=r.outstanding,
            uom_id=r.uom_id, uom_code=r.uom.code if r.uom else None,
            status=r.status, note=r.note, released_at=r.released_at,
            release_reason=r.release_reason, created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/{order_id}/issues", response_model=list[IssueOut])
def list_issues(
    order_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("materials.view")),
):
    _order(db, order_id)
    rows = (
        db.query(ProductionMaterialIssue)
        .options(joinedload(ProductionMaterialIssue.item), joinedload(ProductionMaterialIssue.uom))
        .filter(ProductionMaterialIssue.production_order_id == order_id)
        .order_by(ProductionMaterialIssue.id)
        .all()
    )
    return [
        IssueOut(
            id=r.id, production_order_material_id=r.production_order_material_id,
            item_id=r.item_id, sku=r.item.sku if r.item else None,
            name=r.item.resolved_name if r.item else None,
            quantity=r.quantity, uom_id=r.uom_id,
            uom_code=r.uom.code if r.uom else None,
            stock_movement_id=r.stock_movement_id,
            unreserved_reason=r.unreserved_reason, note=r.note,
            issued_by_id=r.issued_by_id, created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/{order_id}/consumption", response_model=list[ConsumptionOut])
def list_consumption(
    order_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("materials.view")),
):
    _order(db, order_id)
    rows = (
        db.query(ProductionMaterialConsumption)
        .options(
            joinedload(ProductionMaterialConsumption.item),
            joinedload(ProductionMaterialConsumption.uom),
        )
        .filter(ProductionMaterialConsumption.production_order_id == order_id)
        .order_by(ProductionMaterialConsumption.id)
        .all()
    )
    return [
        ConsumptionOut(
            id=r.id, production_order_material_id=r.production_order_material_id,
            item_id=r.item_id, sku=r.item.sku if r.item else None,
            name=r.item.resolved_name if r.item else None,
            quantity=r.quantity, uom_id=r.uom_id,
            uom_code=r.uom.code if r.uom else None,
            over_consumption_reason=r.over_consumption_reason, note=r.note,
            recorded_by_id=r.recorded_by_id, created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/{order_id}/returns", response_model=list[ReturnOut])
def list_returns(
    order_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("materials.view")),
):
    _order(db, order_id)
    rows = (
        db.query(ProductionMaterialReturn)
        .options(joinedload(ProductionMaterialReturn.item), joinedload(ProductionMaterialReturn.uom))
        .filter(ProductionMaterialReturn.production_order_id == order_id)
        .order_by(ProductionMaterialReturn.id)
        .all()
    )
    return [
        ReturnOut(
            id=r.id, production_order_material_id=r.production_order_material_id,
            item_id=r.item_id, sku=r.item.sku if r.item else None,
            name=r.item.resolved_name if r.item else None,
            quantity=r.quantity, uom_id=r.uom_id,
            uom_code=r.uom.code if r.uom else None,
            stock_movement_id=r.stock_movement_id, reason=r.reason,
            restock=r.restock, returned_by_id=r.returned_by_id, created_at=r.created_at,
        )
        for r in rows
    ]


# ----------------------------------------------------------------- mutations


@router.post("/{order_id}/reserve", response_model=OrderMaterialSummary)
def reserve_materials(
    order_id: int, payload: ReserveRequest, db: Session = Depends(get_db),
    user: User = Depends(require_permission("materials.reserve")),
):
    """Reserve one or more materials. Moves no stock.

    All lines succeed or none do - a partly-applied batch would leave the user
    guessing which half committed.
    """
    order = _order(db, order_id)
    for line in payload.lines:
        r = _guard(lambda line=line: mf.reserve(
            db, order, line.material_id, line.quantity, user_id=user.id, note=line.note
        ))
        _audit(db, user, "materials.reserve", order,
               material_id=line.material_id, quantity=line.quantity, reservation_id=r.id)
    db.commit()
    return material_summary(order_id, db, user)


@router.post("/{order_id}/release-reservation", response_model=OrderMaterialSummary)
def release_reservations(
    order_id: int, payload: ReleaseRequest, db: Session = Depends(get_db),
    user: User = Depends(require_permission("materials.release")),
):
    """Release specific reservations, or every outstanding one on the order.

    Already-issued material is never released - it has physically gone and comes
    back through a return.
    """
    order = _order(db, order_id)
    if payload.reservation_ids:
        for rid in payload.reservation_ids:
            reservation = db.get(StockReservation, rid)
            if not reservation or reservation.production_order_id != order.id:
                raise HTTPException(404, f"Reservation {rid} not found on this production order")
            freed = _guard(lambda r=reservation: mf.release_reservation(
                db, r, user_id=user.id, reason=payload.reason
            ))
            _audit(db, user, "materials.release", order, reservation_id=rid, freed=freed,
                   reason=payload.reason)
    else:
        freed = mf.release_all_for_order(db, order, user_id=user.id, reason=payload.reason)
        _audit(db, user, "materials.release_all", order, freed=freed, reason=payload.reason)
    db.commit()
    return material_summary(order_id, db, user)


@router.post("/{order_id}/issue", response_model=OrderMaterialSummary)
def issue_materials(
    order_id: int, payload: IssueRequest, db: Session = Depends(get_db),
    user: User = Depends(require_permission("materials.issue")),
):
    """Physically issue material. Writes PRODUCTION_ISSUE ledger rows.

    Issuing beyond what is reserved needs materials.issue_unreserved, which is
    granted to no role by default, plus a reason.
    """
    order = _order(db, order_id)
    may_over_issue = has_permission(db, user, "materials.issue_unreserved")

    for line in payload.lines:
        if line.allow_unreserved and not may_over_issue:
            raise HTTPException(
                403,
                "Issuing material that was not reserved requires the "
                "'materials.issue_unreserved' permission.",
            )
        rec = _guard(lambda line=line: mf.issue(
            db, order, line.material_id, line.quantity, user_id=user.id,
            allow_unreserved=line.allow_unreserved and may_over_issue,
            unreserved_reason=line.unreserved_reason, note=line.note,
        ))
        _audit(db, user, "materials.issue", order, material_id=line.material_id,
               quantity=line.quantity, issue_id=rec.id, movement_id=rec.stock_movement_id)
    db.commit()
    return material_summary(order_id, db, user)


@router.post("/{order_id}/consume", response_model=OrderMaterialSummary)
def consume_materials(
    order_id: int, payload: ConsumeRequest, db: Session = Depends(get_db),
    user: User = Depends(require_permission("materials.consume")),
):
    """Record what was actually used. **Deducts no stock** - it left at issue."""
    order = _order(db, order_id)
    for line in payload.lines:
        rec = _guard(lambda line=line: mf.consume(
            db, order, line.material_id, line.quantity, user_id=user.id,
            allow_over_consumption=line.allow_over_consumption,
            over_consumption_reason=line.over_consumption_reason, note=line.note,
        ))
        _audit(db, user, "materials.consume", order, material_id=line.material_id,
               quantity=line.quantity, consumption_id=rec.id)
    db.commit()
    return material_summary(order_id, db, user)


@router.post("/{order_id}/return", response_model=OrderMaterialSummary)
def return_materials(
    order_id: int, payload: ReturnRequest, db: Session = Depends(get_db),
    user: User = Depends(require_permission("materials.return")),
):
    """Unused material back to stock - a compensating PRODUCTION_RETURN movement.

    The original issue is never edited.
    """
    order = _order(db, order_id)
    for line in payload.lines:
        rec = _guard(lambda line=line: mf.return_material(
            db, order, line.material_id, line.quantity, user_id=user.id,
            reason=line.reason, restock=line.restock,
        ))
        _audit(db, user, "materials.return", order, material_id=line.material_id,
               quantity=line.quantity, return_id=rec.id, restock=line.restock,
               movement_id=rec.stock_movement_id)
    db.commit()
    return material_summary(order_id, db, user)
