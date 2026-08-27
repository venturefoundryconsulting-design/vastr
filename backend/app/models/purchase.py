import enum
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.money import money
from app.models.inventory import QuantityType
from app.models.mixins import TenantMixin, TimestampMixin


class PurchaseOrderStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    CONFIRMED = "confirmed"
    PARTIALLY_RECEIVED = "partially_received"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class PurchaseOrder(Base, TimestampMixin, TenantMixin):
    __tablename__ = "purchase_orders"
    __table_args__ = (UniqueConstraint("tenant_id", "po_number", name="uq_po_tenant_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    po_number: Mapped[str] = mapped_column(String(30), index=True)
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
    def total_amount(self) -> Decimal:
        return money(sum((item.amount for item in self.items), Decimal("0")))


class PurchaseOrderItem(Base, TimestampMixin, TenantMixin):
    __tablename__ = "purchase_order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"))
    variant_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    quantity_ordered: Mapped[Decimal] = mapped_column(QuantityType, default=Decimal("0"))
    quantity_received: Mapped[Decimal] = mapped_column(QuantityType, default=Decimal("0"))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)

    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="items")
    variant: Mapped["Item"] = relationship()  # noqa: F821

    @property
    def amount(self) -> Decimal:
        base = self.unit_cost * self.quantity_ordered
        return money(base * (1 + self.tax_rate / 100))
