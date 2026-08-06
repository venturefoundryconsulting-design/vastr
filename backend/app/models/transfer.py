import enum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TenantMixin, TimestampMixin


class TransferStatus(str, enum.Enum):
    REQUESTED = "requested"
    DISPATCHED = "dispatched"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class StockTransfer(Base, TimestampMixin, TenantMixin):
    __tablename__ = "stock_transfers"
    __table_args__ = (UniqueConstraint("tenant_id", "transfer_number", name="uq_transfer_tenant_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_number: Mapped[str] = mapped_column(String(30), index=True)
    source_outlet_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"))
    dest_outlet_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"))
    status: Mapped[TransferStatus] = mapped_column(Enum(TransferStatus), default=TransferStatus.REQUESTED)
    notes: Mapped[str | None] = mapped_column(String(500), default=None)
    requested_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    dispatched_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), default=None)
    received_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), default=None)

    source_outlet: Mapped["Outlet"] = relationship(foreign_keys=[source_outlet_id])  # noqa: F821
    dest_outlet: Mapped["Outlet"] = relationship(foreign_keys=[dest_outlet_id])  # noqa: F821
    items: Mapped[list["StockTransferItem"]] = relationship(
        back_populates="transfer", cascade="all, delete-orphan"
    )


class StockTransferItem(Base, TimestampMixin, TenantMixin):
    __tablename__ = "stock_transfer_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_id: Mapped[int] = mapped_column(ForeignKey("stock_transfers.id"))
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id"))
    quantity_requested: Mapped[int] = mapped_column(Integer, default=0)
    quantity_sent: Mapped[int] = mapped_column(Integer, default=0)
    quantity_received: Mapped[int] = mapped_column(Integer, default=0)

    transfer: Mapped["StockTransfer"] = relationship(back_populates="items")
    variant: Mapped["ProductVariant"] = relationship()  # noqa: F821
