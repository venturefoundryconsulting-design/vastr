import enum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin


class WhatsAppMessageStatus(str, enum.Enum):
    LINK_GENERATED = "link_generated"  # manual wa.me link was created, staff must tap Send
    SENT = "sent"  # sent automatically via Cloud API
    DELIVERED = "delivered"  # Cloud API delivery webhook received
    READ = "read"  # Cloud API read-receipt webhook received
    FAILED = "failed"


class WhatsAppMessage(Base, TimestampMixin):
    """Log of PO/invoice documents shared with vendors over WhatsApp."""

    __tablename__ = "whatsapp_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"))
    purchase_order_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_orders.id"), default=None)
    phone_number: Mapped[str] = mapped_column(String(20))
    status: Mapped[WhatsAppMessageStatus] = mapped_column(
        Enum(WhatsAppMessageStatus), default=WhatsAppMessageStatus.LINK_GENERATED
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(100), default=None)
    error: Mapped[str | None] = mapped_column(String(500), default=None)
    sent_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), default=None)

    vendor: Mapped["Vendor"] = relationship()  # noqa: F821
    purchase_order: Mapped["PurchaseOrder | None"] = relationship()  # noqa: F821
