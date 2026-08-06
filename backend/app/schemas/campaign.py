from datetime import datetime

from pydantic import BaseModel

from app.models.campaign import CampaignMediaType, CampaignStatus, SegmentType
from app.models.whatsapp import WhatsAppMessageStatus


class SegmentParams(BaseModel):
    segment_type: SegmentType
    segment_tag: str | None = None
    segment_category_id: int | None = None
    segment_brand: str | None = None
    segment_days: int | None = None


class SegmentPreviewCustomer(BaseModel):
    id: int
    name: str
    phone: str | None = None


class SegmentPreviewResult(BaseModel):
    count: int
    customers: list[SegmentPreviewCustomer]


class CampaignButton(BaseModel):
    type: str  # "quick_reply" (sent as a real WhatsApp button) | "url" | "phone" | "catalog" (appended as text)
    label: str
    value: str


class CampaignCreate(SegmentParams):
    name: str
    message_template: str
    media_url: str | None = None
    media_type: CampaignMediaType | None = None
    buttons: list[CampaignButton] | None = None
    offer_code: str | None = None
    product_name: str | None = None
    scheduled_at: datetime | None = None


class CampaignRecipientOut(BaseModel):
    id: int
    customer_id: int
    customer_name: str | None = None
    phone_number: str
    message_text: str
    status: WhatsAppMessageStatus
    whatsapp_link: str | None = None
    error: str | None = None
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    read_at: datetime | None = None

    model_config = {"from_attributes": True}


class CampaignOut(SegmentParams):
    id: int
    name: str
    message_template: str
    media_url: str | None = None
    media_type: CampaignMediaType | None = None
    buttons: list[CampaignButton] | None = None
    offer_code: str | None = None
    product_name: str | None = None
    scheduled_at: datetime | None = None
    status: CampaignStatus
    recipient_count: int
    sent_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class CampaignDetailOut(CampaignOut):
    recipients: list[CampaignRecipientOut] = []


class CampaignReport(BaseModel):
    recipient_count: int
    link_generated_count: int
    sent_count: int
    delivered_count: int
    read_count: int
    failed_count: int


class MessageTemplateOut(BaseModel):
    id: int
    name: str
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageTemplateCreate(BaseModel):
    name: str
    body: str


class MessageTemplateUpdate(BaseModel):
    name: str | None = None
    body: str | None = None


class MediaUploadResult(BaseModel):
    url: str
    media_type: CampaignMediaType
