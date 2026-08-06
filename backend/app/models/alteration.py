import enum

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TenantMixin, TimestampMixin


class AlterationStatus(str, enum.Enum):
    REQUESTED = "requested"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    READY = "ready"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class Alteration(Base, TimestampMixin, TenantMixin):
    """Tracks a garment through tailoring: requested -> assigned -> in_progress -> ready -> delivered."""

    __tablename__ = "alterations"
    __table_args__ = (UniqueConstraint("tenant_id", "alteration_number", name="uq_alteration_tenant_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    alteration_number: Mapped[str] = mapped_column(String(30), index=True)
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"))
    sale_id: Mapped[int | None] = mapped_column(ForeignKey("sales.id"), default=None)
    sale_item_id: Mapped[int | None] = mapped_column(ForeignKey("sale_items.id"), default=None)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), default=None)
    customer_name: Mapped[str | None] = mapped_column(String(120), default=None)
    customer_phone: Mapped[str | None] = mapped_column(String(20), default=None)

    description: Mapped[str] = mapped_column(Text)
    # Free text - tailors are often external/contracted, not system user accounts.
    tailor_name: Mapped[str | None] = mapped_column(String(120), default=None)
    status: Mapped[AlterationStatus] = mapped_column(Enum(AlterationStatus), default=AlterationStatus.REQUESTED)
    expected_ready_date: Mapped[Date | None] = mapped_column(Date, default=None)
    delivered_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), default=None)
    notes: Mapped[str | None] = mapped_column(String(500), default=None)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)

    outlet: Mapped["Outlet"] = relationship()  # noqa: F821
    sale: Mapped["Sale | None"] = relationship()  # noqa: F821
    sale_item: Mapped["SaleItem | None"] = relationship()  # noqa: F821
    customer: Mapped["Customer | None"] = relationship()  # noqa: F821
