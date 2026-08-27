"""Phase 9 - AI-assisted invoice import.

Upload an invoice photo, review what the model extracted, approve into a
DRAFT goods receipt. See app.services.ai_import for the staging-vs-approval
split; this router is thin over it.
"""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, require_permission
from app.core.config import settings as env_settings
from app.models.ai_import import AiImportBatch, AiImportRow, AiImportStatus
from app.models.goods_receipt import GoodsReceipt
from app.models.outlet import Outlet
from app.models.product import Item
from app.models.uom import UnitOfMeasure
from app.models.user import User
from app.models.vendor import Vendor
from app.schemas.ai_import import (
    AiImportBatchOut,
    AiImportBatchSummary,
    AiImportRowOut,
    AiImportRowUpdate,
)
from app.services import ai_import as ai
from app.services.audit import log_activity
from app.services.hardware_settings import get_hardware_ai_settings
from app.services.numbering import next_document_number

router = APIRouter(prefix="/api/ai-import", tags=["ai-import"])

IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def _guard(fn):
    try:
        return fn()
    except ai.AiImportError as e:
        raise HTTPException(400, str(e)) from e


def _load(db: Session, batch_id: int) -> AiImportBatch:
    batch = (
        db.query(AiImportBatch)
        .options(
            joinedload(AiImportBatch.outlet), joinedload(AiImportBatch.vendor),
            joinedload(AiImportBatch.rows).joinedload(AiImportRow.matched_item),
            joinedload(AiImportBatch.rows).joinedload(AiImportRow.uom),
        )
        .filter(AiImportBatch.id == batch_id)
        .first()
    )
    if not batch:
        raise HTTPException(404, "Import batch not found")
    return batch


def _row_out(row: AiImportRow) -> AiImportRowOut:
    return AiImportRowOut(
        id=row.id, line_no=row.line_no, raw_description=row.raw_description,
        raw_unit_text=row.raw_unit_text,
        matched_item_id=row.matched_item_id,
        matched_item_name=row.matched_item.resolved_name if row.matched_item else None,
        matched_item_sku=row.matched_item.sku if row.matched_item else None,
        is_new_item=row.is_new_item, proposed_sku=row.proposed_sku,
        quantity=row.quantity, uom_id=row.uom_id, uom_code=row.uom.code if row.uom else None,
        unit_cost=row.unit_cost,
        description_confidence=row.description_confidence,
        quantity_confidence=row.quantity_confidence,
        cost_confidence=row.cost_confidence, match_confidence=row.match_confidence,
        excluded=row.excluded,
    )


def _batch_out(batch: AiImportBatch, receipt_number: str | None = None) -> AiImportBatchOut:
    return AiImportBatchOut(
        id=batch.id, outlet_id=batch.outlet_id, outlet_name=batch.outlet.name if batch.outlet else None,
        vendor_id=batch.vendor_id, vendor_name=batch.vendor.name if batch.vendor else None,
        source_filename=batch.source_filename, status=batch.status,
        vendor_name_guess=batch.vendor_name_guess, invoice_ref_guess=batch.invoice_ref_guess,
        goods_receipt_id=batch.goods_receipt_id, goods_receipt_number=receipt_number,
        notes=batch.notes, created_at=batch.created_at.isoformat(),
        rows=[_row_out(r) for r in batch.rows],
    )


@router.get("", response_model=list[AiImportBatchSummary])
def list_batches(
    status: AiImportStatus | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("ai_import.create")),
):
    q = db.query(AiImportBatch).options(
        joinedload(AiImportBatch.outlet), joinedload(AiImportBatch.vendor)
    )
    if status:
        q = q.filter(AiImportBatch.status == status)
    batches = q.order_by(AiImportBatch.id.desc()).limit(100).all()
    return [
        AiImportBatchSummary(
            id=b.id, outlet_name=b.outlet.name if b.outlet else None,
            vendor_name=b.vendor.name if b.vendor else None,
            source_filename=b.source_filename, status=b.status,
            line_count=len(b.rows), created_at=b.created_at.isoformat(),
        )
        for b in batches
    ]


@router.get("/{batch_id}", response_model=AiImportBatchOut)
def get_batch(
    batch_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("ai_import.create")),
):
    batch = _load(db, batch_id)
    receipt = db.get(GoodsReceipt, batch.goods_receipt_id) if batch.goods_receipt_id else None
    return _batch_out(batch, receipt.receipt_number if receipt else None)


@router.post("/extract", response_model=AiImportBatchOut, status_code=201)
async def extract(
    outlet_id: int, vendor_id: int | None = None, file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("ai_import.create")),
):
    ext = IMAGE_TYPES.get(file.content_type)
    if not ext:
        raise HTTPException(400, "Only JPEG, PNG or WebP images are allowed")
    if not db.get(Outlet, outlet_id):
        raise HTTPException(404, "Outlet not found")
    if vendor_id and not db.get(Vendor, vendor_id):
        raise HTTPException(404, "Vendor not found")

    ai_settings = get_hardware_ai_settings(db)
    if not ai_settings.openai_api_key:
        raise HTTPException(
            400,
            "No OpenAI API key configured for this store. Set one under "
            "Settings → Hardware & AI before uploading an invoice.",
        )

    contents = await file.read()
    if len(contents) > 8 * 1024 * 1024:
        raise HTTPException(400, "Invoice image must be under 8MB")

    upload_dir = env_settings.tenant_upload_dir(user.tenant_id, "ai-import")
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"invoice-{uuid.uuid4().hex}{ext}"
    (upload_dir / filename).write_bytes(contents)
    rel_path = f"{env_settings.tenant_relative_path(user.tenant_id, 'ai-import')}/{filename}"

    try:
        extraction = ai.call_extraction(
            api_key=ai_settings.openai_api_key, model=ai_settings.openai_model,
            image_bytes=contents, mime_type=file.content_type,
        )
    except ai.AiImportError as e:
        raise HTTPException(502, str(e)) from e
    except Exception as e:  # noqa: BLE001 - surface any provider-side failure as a 502, not a 500
        raise HTTPException(502, f"Extraction failed: {e}") from e

    batch = ai.create_batch(
        db, outlet_id=outlet_id, vendor_id=vendor_id,
        source_filename=file.filename or filename, source_path=rel_path,
        extraction=extraction, user_id=user.id,
    )
    log_activity(db, action="ai_import.extract", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="AiImportBatch", entity_id=batch.id,
                 details={"filename": batch.source_filename, "lines": len(batch.rows)})
    db.commit()
    return _batch_out(_load(db, batch.id))


@router.patch("/rows/{row_id}", response_model=AiImportRowOut)
def patch_row(
    row_id: int, payload: AiImportRowUpdate, db: Session = Depends(get_db),
    user: User = Depends(require_permission("ai_import.create")),
):
    row = db.get(AiImportRow, row_id)
    if not row:
        raise HTTPException(404, "Import row not found")
    batch = db.get(AiImportBatch, row.batch_id)
    if batch.status != AiImportStatus.PENDING:
        raise HTTPException(409, f"This batch is already {batch.status.value} and can no longer be edited")
    if payload.matched_item_id and not db.get(Item, payload.matched_item_id):
        raise HTTPException(404, "Item not found")
    if payload.uom_id and not db.get(UnitOfMeasure, payload.uom_id):
        raise HTTPException(404, "Unit of measure not found")

    ai.update_row(db, row, **payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(row)
    return _row_out(row)


@router.post("/batches/{batch_id}/approve", response_model=AiImportBatchOut)
def approve(
    batch_id: int, db: Session = Depends(get_db),
    user: User = Depends(require_permission("ai_import.approve")),
):
    batch = _load(db, batch_id)
    number = next_document_number(db, GoodsReceipt, GoodsReceipt.receipt_number, "GRN")
    receipt = _guard(lambda: ai.approve_batch(db, batch, user_id=user.id, receipt_number=number))
    log_activity(db, action="ai_import.approve", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="AiImportBatch", entity_id=batch.id,
                 details={"goods_receipt": receipt.receipt_number})
    db.commit()
    return _batch_out(_load(db, batch_id), receipt.receipt_number)


@router.post("/batches/{batch_id}/reject", response_model=AiImportBatchOut)
def reject(
    batch_id: int, db: Session = Depends(get_db),
    user: User = Depends(require_permission("ai_import.approve")),
):
    batch = _load(db, batch_id)
    _guard(lambda: ai.reject_batch(db, batch, user_id=user.id))
    log_activity(db, action="ai_import.reject", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="AiImportBatch", entity_id=batch.id, details={})
    db.commit()
    return _batch_out(_load(db, batch_id))
