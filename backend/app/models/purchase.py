import enum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin


class PurchaseOrderStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    CONFIRMED = "confirmed"
    PARTIALLY_RECEIVED = "partially_received"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class PurchaseOrder(Base, TimestampMixin):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    po_number: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"))
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"))
    status: Mapped[PurchaseOrderStatus] = mapped_column(
        Enum(PurchaseOrderStatus), default=PurchaseOrderStatus.DRAFT
    )
    order_date: Mapped[DateTime] = mapped_column(DateTime(timezone=True))
    expected_date: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), default=None)
    notes: Mapped[str | None] = mapped_column(String(500), default=None)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)

    vendor: Mapped["Vendor"] = relationship()  # noqa: F821
    outlet: Mapped["Outlet"] = relationship()  # noqa: F821
    items: Mapped[list["PurchaseOrderItem"]] = relationship(
        back_populates="purchase_order", cascade="all, delete-orphan"
    )

    @property
    def total_amount(self) -> float:
        return sum(item.amount for item in self.items)


class PurchaseOrderItem(Base, TimestampMixin):
    __tablename__ = "purchase_order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"))
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id"))
    quantity_ordered: Mapped[int] = mapped_column(Integer, default=0)
    quantity_received: Mapped[int] = mapped_column(Integer, default=0)
    unit_cost: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=0)

    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="items")
    variant: Mapped["ProductVariant"] = relationship()  # noqa: F821

    @property
    def amount(self) -> float:
        base = float(self.unit_cost) * self.quantity_ordered
        return round(base * (1 + float(self.tax_rate) / 100), 2)
