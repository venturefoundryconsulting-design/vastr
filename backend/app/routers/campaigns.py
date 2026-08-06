import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, require_manager_up
from app.core.config import settings
from app.models.campaign import Campaign, CampaignMediaType, CampaignRecipient, CampaignStatus, MessageTemplate
from app.models.user import User
from app.schemas.campaign import (
    CampaignCreate,
    CampaignDetailOut,
    CampaignOut,
    CampaignReport,
    CampaignRecipientOut,
    MediaUploadResult,
    MessageTemplateCreate,
    MessageTemplateOut,
    MessageTemplateUpdate,
    SegmentParams,
    SegmentPreviewResult,
)
from app.services.app_settings import get_app_settings
from app.services.campaigns import PLACEHOLDER_CATALOG, resolve_segment, send_campaign
from app.services.whatsapp import build_wa_me_link
from app.models.whatsapp import WhatsAppMessageStatus

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])
templates_router = APIRouter(
    prefix="/api/message-templates", tags=["campaigns"], dependencies=[Depends(require_manager_up)]
)

CAMPAIGN_MEDIA_TYPES: dict[str, tuple[str, CampaignMediaType]] = {
    "image/jpeg": (".jpg", CampaignMediaType.IMAGE),
    "image/png": (".png", CampaignMediaType.IMAGE),
    "image/webp": (".webp", CampaignMediaType.IMAGE),
    "video/mp4": (".mp4", CampaignMediaType.VIDEO),
    "application/pdf": (".pdf", CampaignMediaType.DOCUMENT),
}


def _recipient_out(r: CampaignRecipient) -> CampaignRecipientOut:
    return CampaignRecipientOut(
        id=r.id,
        customer_id=r.customer_id,
        customer_name=r.customer.name if r.customer else None,
        phone_number=r.phone_number,
        message_text=r.message_text,
        status=r.status,
        whatsapp_link=build_wa_me_link(r.phone_number, r.message_text)
        if r.status == WhatsAppMessageStatus.LINK_GENERATED
        else None,
        error=r.error,
        sent_at=r.sent_at,
        delivered_at=r.delivered_at,
        read_at=r.read_at,
    )


@router.get("/placeholders")
def list_placeholders(_=Depends(require_manager_up)):
    """Catalog of {token} placeholders the message composer can insert, with a description of
    what each expands to. Kept server-side so the frontend never hardcodes a stale list."""
    return PLACEHOLDER_CATALOG


@router.post("/upload-media", response_model=MediaUploadResult)
async def upload_campaign_media(
    file: UploadFile = File(...), current_user: User = Depends(require_manager_up)
):
    match = CAMPAIGN_MEDIA_TYPES.get(file.content_type)
    if not match:
        raise HTTPException(400, "Only JPEG/PNG/WebP images, MP4 video, or PDF documents are allowed")
    ext, media_type = match

    contents = await file.read()
    if len(contents) > 16 * 1024 * 1024:
        raise HTTPException(400, "File must be under 16MB")

    media_dir = settings.tenant_upload_dir(current_user.tenant_id, "campaigns")
    media_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    (media_dir / filename).write_bytes(contents)

    rel = settings.tenant_relative_path(current_user.tenant_id, "campaigns", filename)
    return MediaUploadResult(url=f"{settings.PUBLIC_BASE_URL}/uploads/{rel}", media_type=media_type)


@router.post("/preview", response_model=SegmentPreviewResult, dependencies=[Depends(require_manager_up)])
def preview_segment(payload: SegmentParams, db: Session = Depends(get_db)):
    customers = resolve_segment(db, payload)
    return SegmentPreviewResult(
        count=len(customers),
        customers=[{"id": c.id, "name": c.name, "phone": c.whatsapp_number or c.phone} for c in customers],
    )


@router.get("", response_model=list[CampaignOut], dependencies=[Depends(require_manager_up)])
def list_campaigns(db: Session = Depends(get_db)):
    return db.query(Campaign).order_by(Campaign.created_at.desc()).all()


@router.get("/{campaign_id}/report", response_model=CampaignReport, dependencies=[Depends(require_manager_up)])
def get_campaign_report(campaign_id: int, db: Session = Depends(get_db)):
    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    counts = {status: 0 for status in WhatsAppMessageStatus}
    for (status, count) in (
        db.query(CampaignRecipient.status, func.count())
        .filter(CampaignRecipient.campaign_id == campaign_id)
        .group_by(CampaignRecipient.status)
        .all()
    ):
        counts[status] = count
    return CampaignReport(
        recipient_count=campaign.recipient_count,
        link_generated_count=counts[WhatsAppMessageStatus.LINK_GENERATED],
        sent_count=counts[WhatsAppMessageStatus.SENT],
        delivered_count=counts[WhatsAppMessageStatus.DELIVERED],
        read_count=counts[WhatsAppMessageStatus.READ],
        failed_count=counts[WhatsAppMessageStatus.FAILED],
    )


@router.get("/{campaign_id}", response_model=CampaignDetailOut, dependencies=[Depends(require_manager_up)])
def get_campaign(campaign_id: int, db: Session = Depends(get_db)):
    campaign = (
        db.query(Campaign)
        .options(joinedload(Campaign.recipients).joinedload(CampaignRecipient.customer))
        .filter(Campaign.id == campaign_id)
        .first()
    )
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    return CampaignDetailOut(
        **CampaignOut.model_validate(campaign).model_dump(),
        recipients=[_recipient_out(r) for r in campaign.recipients],
    )


@router.post("", response_model=CampaignDetailOut)
def create_campaign(payload: CampaignCreate, db: Session = Depends(get_db), user: User = Depends(require_manager_up)):
    customers = resolve_segment(db, payload)
    if not customers:
        raise HTTPException(400, "No customers match this segment")

    is_scheduled = bool(payload.scheduled_at and payload.scheduled_at > datetime.now(timezone.utc))
    campaign = Campaign(
        name=payload.name,
        message_template=payload.message_template,
        segment_type=payload.segment_type,
        segment_tag=payload.segment_tag,
        segment_category_id=payload.segment_category_id,
        segment_brand=payload.segment_brand,
        segment_days=payload.segment_days,
        media_url=payload.media_url,
        media_type=payload.media_type,
        buttons=[b.model_dump() for b in payload.buttons] if payload.buttons else None,
        offer_code=payload.offer_code,
        product_name=payload.product_name,
        scheduled_at=payload.scheduled_at,
        status=CampaignStatus.SCHEDULED if is_scheduled else CampaignStatus.SENT,
        created_by_id=user.id,
    )
    db.add(campaign)
    db.flush()

    if is_scheduled:
        # The scheduler (app.services.campaign_scheduler) picks this up once scheduled_at is
        # due and calls send_campaign() then, re-resolving the segment at that time.
        campaign.recipient_count = len(customers)
    else:
        app_settings = get_app_settings(db)
        recipients = send_campaign(db, campaign, customers, app_settings)
        campaign.recipient_count = len(recipients)
        campaign.sent_count = sum(1 for r in recipients if r.status == WhatsAppMessageStatus.SENT)
    db.commit()
    db.refresh(campaign)

    campaign = (
        db.query(Campaign)
        .options(joinedload(Campaign.recipients).joinedload(CampaignRecipient.customer))
        .filter(Campaign.id == campaign.id)
        .first()
    )
    return CampaignDetailOut(
        **CampaignOut.model_validate(campaign).model_dump(),
        recipients=[_recipient_out(r) for r in campaign.recipients],
    )


# ---- Message templates ----


@templates_router.get("", response_model=list[MessageTemplateOut])
def list_message_templates(db: Session = Depends(get_db)):
    return db.query(MessageTemplate).order_by(MessageTemplate.name).all()


@templates_router.post("", response_model=MessageTemplateOut)
def create_message_template(payload: MessageTemplateCreate, db: Session = Depends(get_db), user: User = Depends(require_manager_up)):
    template = MessageTemplate(name=payload.name, body=payload.body, created_by_id=user.id)
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@templates_router.patch("/{template_id}", response_model=MessageTemplateOut)
def update_message_template(template_id: int, payload: MessageTemplateUpdate, db: Session = Depends(get_db)):
    template = db.get(MessageTemplate, template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    db.commit()
    db.refresh(template)
    return template


@templates_router.delete("/{template_id}", status_code=204)
def delete_message_template(template_id: int, db: Session = Depends(get_db)):
    template = db.get(MessageTemplate, template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    db.delete(template)
    db.commit()
