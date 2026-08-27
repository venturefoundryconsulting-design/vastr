"""Quality control, rework, wastage and production costing.

All read-only with respect to inventory: a failed check does not un-make a
garment, and wastage does not deduct stock a second time (it left at issue).
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, get_db, require_permission
from app.models.production import ProductionOrder
from app.models.quality import (
    DefectCategory,
    ProductionWastage,
    QcResult,
    QualityCheck,
    ReworkOrder,
    WastageReason,
)
from app.models.user import User
from app.schemas.fields import Money, Quantity
from app.services import costing
from app.services import quality as qc
from app.services.audit import log_activity
from app.services.numbering import next_document_number

router = APIRouter(prefix="/api", tags=["quality"])


# --------------------------------------------------------------------- DTOs


class DefectIn(BaseModel):
    defect_category_id: int
    quantity: Quantity = Decimal("0")
    notes: str | None = None


class QcRequest(BaseModel):
    result: QcResult
    checked_quantity: Quantity
    failed_quantity: Quantity = Decimal("0")
    work_order_id: int | None = None
    notes: str | None = None
    photo_path: str | None = None
    defects: list[DefectIn] = []


class ReworkRequest(BaseModel):
    quantity: Quantity
    reason: str
    quality_check_id: int | None = None
    work_order_id: int | None = None
    assigned_tailor_id: int | None = None

    @field_validator("reason")
    @classmethod
    def reason_required(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("A reason is required to raise rework")
        return v.strip()


class WastageRequest(BaseModel):
    material_id: int
    quantity: Quantity
    reason_id: int | None = None
    work_order_id: int | None = None
    tailor_id: int | None = None
    notes: str | None = None


class LookupOut(BaseModel):
    id: int
    code: str
    name: str
    is_active: bool


def _order(db: Session, order_id: int) -> ProductionOrder:
    order = (
        db.query(ProductionOrder)
        .options(joinedload(ProductionOrder.materials))
        .filter(ProductionOrder.id == order_id)
        .first()
    )
    if not order:
        raise HTTPException(404, "Production order not found")
    return order


def _guard(fn):
    try:
        return fn()
    except qc.QualityError as e:
        raise HTTPException(409, str(e)) from e


# ---------------------------------------------------------------- lookups


@router.get("/defect-categories", response_model=list[LookupOut])
def list_defect_categories(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(DefectCategory).order_by(DefectCategory.name).all()


@router.get("/wastage-reasons", response_model=list[LookupOut])
def list_wastage_reasons(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(WastageReason).order_by(WastageReason.name).all()


# ----------------------------------------------------------- quality checks


@router.get("/production-orders/{order_id}/quality-checks")
def list_checks(
    order_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("qc.view")),
):
    _order(db, order_id)
    rows = (
        db.query(QualityCheck)
        .options(joinedload(QualityCheck.defects).joinedload(qc.QualityDefect.category))
        .filter(QualityCheck.production_order_id == order_id)
        .order_by(QualityCheck.id)
        .all()
    )
    return [
        {
            "id": c.id, "result": c.result, "checked_quantity": c.checked_quantity,
            "passed_quantity": c.passed_quantity, "failed_quantity": c.failed_quantity,
            "work_order_id": c.work_order_id, "notes": c.notes,
            "photo_path": c.photo_path, "inspector_id": c.inspector_id,
            "checked_at": c.checked_at,
            "defects": [
                {"category": d.category.name if d.category else None,
                 "quantity": d.quantity, "notes": d.notes}
                for d in c.defects
            ],
        }
        for c in rows
    ]


@router.post("/production-orders/{order_id}/quality-checks", status_code=201)
def create_check(
    order_id: int, payload: QcRequest, db: Session = Depends(get_db),
    user: User = Depends(require_permission("qc.create")),
):
    order = _order(db, order_id)
    check = _guard(lambda: qc.record_check(
        db, order, result=payload.result,
        checked_quantity=payload.checked_quantity, failed_quantity=payload.failed_quantity,
        work_order_id=payload.work_order_id, notes=payload.notes,
        photo_path=payload.photo_path,
        defects=[d.model_dump() for d in payload.defects],
        inspector_id=user.id,
    ))
    log_activity(db, action="qc.check", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="ProductionOrder", entity_id=order.id,
                 details={"result": payload.result.value, "checked": payload.checked_quantity,
                          "failed": payload.failed_quantity, "check_id": check.id})
    db.commit()
    return {"id": check.id, "result": check.result, "failed_quantity": check.failed_quantity}


# ------------------------------------------------------------------ rework


@router.get("/production-orders/{order_id}/rework")
def list_rework(
    order_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("qc.view")),
):
    _order(db, order_id)
    rows = (
        db.query(ReworkOrder)
        .filter(ReworkOrder.production_order_id == order_id)
        .order_by(ReworkOrder.id)
        .all()
    )
    return [
        {"id": r.id, "rework_number": r.rework_number, "quantity": r.quantity,
         "reason": r.reason, "status": r.status, "work_order_id": r.work_order_id,
         "assigned_tailor_id": r.assigned_tailor_id, "resolved_at": r.resolved_at,
         "created_at": r.created_at}
        for r in rows
    ]


@router.post("/production-orders/{order_id}/rework", status_code=201)
def create_rework(
    order_id: int, payload: ReworkRequest, db: Session = Depends(get_db),
    user: User = Depends(require_permission("qc.rework")),
):
    """Raise corrective work against this order - never a duplicate order."""
    order = _order(db, order_id)
    rework = _guard(lambda: qc.raise_rework(
        db, order, quantity=payload.quantity, reason=payload.reason,
        quality_check_id=payload.quality_check_id, work_order_id=payload.work_order_id,
        assigned_tailor_id=payload.assigned_tailor_id, user_id=user.id,
        number=next_document_number(db, ReworkOrder, ReworkOrder.rework_number, "RW"),
    ))
    log_activity(db, action="qc.rework", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="ProductionOrder", entity_id=order.id,
                 details={"rework_id": rework.id, "quantity": payload.quantity,
                          "reason": payload.reason})
    db.commit()
    return {"id": rework.id, "rework_number": rework.rework_number, "status": rework.status}


@router.post("/rework/{rework_id}/resolve")
def resolve_rework(
    rework_id: int, db: Session = Depends(get_db),
    user: User = Depends(require_permission("qc.rework")),
):
    rework = db.get(ReworkOrder, rework_id)
    if not rework:
        raise HTTPException(404, "Rework not found")
    _guard(lambda: qc.resolve_rework(db, rework))
    log_activity(db, action="qc.rework.resolve", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="ReworkOrder", entity_id=rework.id, details={})
    db.commit()
    return {"id": rework.id, "status": rework.status}


# ----------------------------------------------------------------- wastage


@router.get("/production-orders/{order_id}/wastage")
def list_wastage(
    order_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("wastage.view")),
):
    order = _order(db, order_id)
    rows = (
        db.query(ProductionWastage)
        .options(joinedload(ProductionWastage.item), joinedload(ProductionWastage.reason),
                 joinedload(ProductionWastage.tailor))
        .filter(ProductionWastage.production_order_id == order_id)
        .order_by(ProductionWastage.id)
        .all()
    )
    return {
        "entries": [
            {"id": w.id, "item_id": w.item_id,
             "sku": w.item.sku if w.item else None,
             "name": w.item.resolved_name if w.item else None,
             "quantity": w.quantity, "uom_id": w.uom_id,
             "reason": w.reason.name if w.reason else None,
             "tailor_name": w.tailor.name if w.tailor else None,
             "work_order_id": w.work_order_id, "notes": w.notes,
             "created_at": w.created_at}
            for w in rows
        ],
        "summary": qc.wastage_summary(db, order),
        "total_cost": qc.wastage_cost(db, order),
    }


@router.post("/production-orders/{order_id}/wastage", status_code=201)
def record_wastage(
    order_id: int, payload: WastageRequest, db: Session = Depends(get_db),
    user: User = Depends(require_permission("wastage.record")),
):
    """Record material that will never become product. Writes no ledger row."""
    order = _order(db, order_id)
    rec = _guard(lambda: qc.record_wastage(
        db, order, payload.material_id, payload.quantity,
        reason_id=payload.reason_id, work_order_id=payload.work_order_id,
        tailor_id=payload.tailor_id, notes=payload.notes, user_id=user.id,
    ))
    log_activity(db, action="wastage.record", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="ProductionOrder", entity_id=order.id,
                 details={"material_id": payload.material_id, "quantity": payload.quantity,
                          "wastage_id": rec.id})
    db.commit()
    return {"id": rec.id, "quantity": rec.quantity}


# ----------------------------------------------------------------- costing


@router.get("/production-orders/{order_id}/cost")
def order_cost(
    order_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("costing.view")),
):
    """Material + labour + wastage, estimated against actual."""
    return costing.order_cost(db, _order(db, order_id))


@router.get("/production-orders/{order_id}/variance")
def order_variance(
    order_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("costing.view")),
):
    """Planned vs actual per material. The BOM is never rewritten from this."""
    return costing.planned_vs_actual(db, _order(db, order_id))


# ----------------------------------------------------------------- reports


@router.get("/manufacturing/summary")
def manufacturing_summary(
    db: Session = Depends(get_db), _: User = Depends(require_permission("production.reports")),
):
    return costing.production_summary(db)


@router.get("/manufacturing/wastage-report")
def wastage_report(
    db: Session = Depends(get_db), _: User = Depends(require_permission("production.reports")),
    limit: int = Query(50, le=200),
):
    return costing.wastage_report(db, limit=limit)


@router.get("/manufacturing/tailor-productivity")
def tailor_productivity(
    db: Session = Depends(get_db), _: User = Depends(require_permission("production.reports")),
):
    return costing.tailor_productivity(db)
