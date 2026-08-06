import enum

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TenantMixin, TimestampMixin
from app.models.sale import PaymentMode


class RefundMode(str, enum.Enum):
    CASH = "cash"
    STORE_CREDIT = "store_credit"


class Return(Base, TimestampMixin, TenantMixin):
    """A return, or a return-and-exchange, against a prior Sale.

    exchanged_value - returned_value = difference: positive means the customer
    owes more (collected via payment_mode), negative means a refund is due
    (settled via refund_mode), zero means a straight swap with no money moved.
    """

    __tablename__ = "returns"
    __table_args__ = (UniqueConstraint("tenant_id", "return_number", name="uq_return_tenant_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    return_number: Mapped[str] = mapped_column(String(30), index=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"))
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), default=None)
    reason: Mapped[str | None] = mapped_column(String(255), default=None)
    refund_mode: Mapped[RefundMode | None] = mapped_column(Enum(RefundMode), default=None)
    payment_mode: Mapped[PaymentMode | None] = mapped_column(Enum(PaymentMode), default=None)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)

    sale: Mapped["Sale"] = relationship()  # noqa: F821
    outlet: Mapped["Outlet"] = relationship()  # noqa: F821
    customer: Mapped["Customer | None"] = relationship()  # noqa: F821
    return_items: Mapped[list["ReturnItem"]] = relationship(
        back_populates="return_", cascade="all, delete-orphan"
    )
    exchange_items: Mapped[list["ExchangeItem"]] = relationship(
        back_populates="return_", cascade="all, delete-orphan"
    )

    @property
    def returned_value(self) -> float:
        return sum(
            float(i.unit_price) * i.quantity * (1 + float(i.tax_rate) / 100) for i in self.return_items
        )

    @property
    def exchanged_value(self) -> float:
        return sum(
            float(i.unit_price) * i.quantity * (1 + float(i.tax_rate) / 100) for i in self.exchange_items
        )

    @property
    def difference(self) -> float:
        return round(self.exchanged_value - self.returned_value, 2)


class ReturnItem(Base, TimestampMixin, TenantMixin):
    """An item handed back by the customer from the original sale."""

    __tablename__ = "return_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    return_id: Mapped[int] = mapped_column(ForeignKey("returns.id"))
    sale_item_id: Mapped[int] = mapped_column(ForeignKey("sale_items.id"))
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    # False when the item is damaged/unsellable and should not go back into stock.
    restock: Mapped[bool] = mapped_column(Boolean, default=True)

    return_: Mapped["Return"] = relationship(back_populates="return_items")
    variant: Mapped["ProductVariant"] = relationship()  # noqa: F821


class ExchangeItem(Base, TimestampMixin, TenantMixin):
    """A new item given to the customer in place of a returned one."""

    __tablename__ = "exchange_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    return_id: Mapped[int] = mapped_column(ForeignKey("returns.id"))
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=0)

    return_: Mapped["Return"] = relationship(back_populates="exchange_items")
    variant: Mapped["ProductVariant"] = relationship()  # noqa: F821
