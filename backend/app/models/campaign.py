import enum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TenantMixin, TimestampMixin
from app.models.whatsapp import WhatsAppMessageStatus


class SegmentType(str, enum.Enum):
    ALL = "all"
    VIP = "vip"
    TAG = "tag"
    CATEGORY_PURCHASE = "category_purchase"
    BRAND_PURCHASE = "brand_purchase"
    INACTIVE = "inactive"
    BIRTHDAY_MONTH = "birthday_month"


class CampaignMediaType(str, enum.Enum):
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"


class CampaignStatus(str, enum.Enum):
    SCHEDULED = "scheduled"  # scheduled_at is in the future, not sent yet
    SENT = "sent"  # sent immediately (or the scheduler already ran it)
    FAILED = "failed"  # every recipient failed


class MessageTemplate(Base, TimestampMixin, TenantMixin):
    """A reusable, saved campaign message body with placeholder tokens."""

    __tablename__ = "message_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    body: Mapped[str] = mapped_column(Text)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)


class Campaign(Base, TimestampMixin, TenantMixin):
    """A one-off WhatsApp broadcast sent to a customer segment."""

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    message_template: Mapped[str] = mapped_column(Text)

    segment_type: Mapped[SegmentType] = mapped_column(Enum(SegmentType))
    segment_tag: Mapped[str | None] = mapped_column(String(60), default=None)
    segment_category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), default=None)
    segment_brand: Mapped[str | None] = mapped_column(String(120), default=None)
    # Lookback window (category/brand purchase) or inactivity window (inactive), in days.
    segment_days: Mapped[int | None] = mapped_column(Integer, default=None)

    media_url: Mapped[str | None] = mapped_column(String(500), default=None)
    media_type: Mapped[CampaignMediaType | None] = mapped_column(Enum(CampaignMediaType), default=None)
    # Campaign-wide placeholder values (same for every recipient), used by {offer_code}/{product_name}.
    offer_code: Mapped[str | None] = mapped_column(String(40), default=None)
    product_name: Mapped[str | None] = mapped_column(String(200), default=None)
    # List of {"type": "url"|"phone"|"quick_reply", "label": str, "value": str}, admin-configured, max 3.
    buttons: Mapped[list | None] = mapped_column(JSONB, default=None)

    scheduled_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), default=None)
    status: Mapped[CampaignStatus] = mapped_column(Enum(CampaignStatus), default=CampaignStatus.SENT)

    recipient_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)

    category: Mapped["Category | None"] = relationship()  # noqa: F821
    recipients: Mapped[list["CampaignRecipient"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )


class CampaignRecipient(Base, TimestampMixin, TenantMixin):
    __tablename__ = "campaign_recipients"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    phone_number: Mapped[str] = mapped_column(String(20))
    message_text: Mapped[str] = mapped_column(Text)
    status: Mapped[WhatsAppMessageStatus] = mapped_column(
        Enum(WhatsAppMessageStatus), default=WhatsAppMessageStatus.LINK_GENERATED
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(100), default=None)
    error: Mapped[str | None] = mapped_column(String(500), default=None)
    sent_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), default=None)
    delivered_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), default=None)
    read_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), default=None)

    campaign: Mapped["Campaign"] = relationship(back_populates="recipients")
    customer: Mapped["Customer"] = relationship()  # noqa: F821
