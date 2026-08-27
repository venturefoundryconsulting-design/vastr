import enum
from decimal import Decimal

from sqlalchemy import Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.money import money, to_decimal
from app.models.inventory import QuantityType
from app.models.mixins import TenantMixin, TimestampMixin


class PaymentMode(str, enum.Enum):
    CASH = "cash"
    CARD = "card"
    UPI = "upi"
    OTHER = "other"


class Sale(Base, TimestampMixin, TenantMixin):
    __tablename__ = "sales"
    __table_args__ = (UniqueConstraint("tenant_id", "invoice_number", name="uq_sale_tenant_invoice"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(30), index=True)
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"))
    cashier_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), default=None)
    customer_name: Mapped[str | None] = mapped_column(String(120), default=None)
    customer_phone: Mapped[str | None] = mapped_column(String(20), default=None)
    customer_email: Mapped[str | None] = mapped_column(String(255), default=None)
    discount_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    coupon_code: Mapped[str | None] = mapped_column(String(40), default=None)
    discount_rule_id: Mapped[int | None] = mapped_column(ForeignKey("discount_rules.id"), default=None)
    rule_discount_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    credit_applied: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    points_redeemed: Mapped[int] = mapped_column(Integer, default=0)
    loyalty_points_earned: Mapped[int] = mapped_column(Integer, default=0)
    payment_mode: Mapped[PaymentMode] = mapped_column(Enum(PaymentMode), default=PaymentMode.CASH)

    outlet: Mapped["Outlet"] = relationship()  # noqa: F821
    customer: Mapped["Customer | None"] = relationship()  # noqa: F821
    discount_rule: Mapped["DiscountRule | None"] = relationship()  # noqa: F821
    items: Mapped[list["SaleItem"]] = relationship(back_populates="sale", cascade="all, delete-orphan")

    @property
    def subtotal(self) -> Decimal:
        return money(sum((item.unit_price * item.quantity for item in self.items), Decimal("0")))

    @property
    def tax_amount(self) -> Decimal:
        return money(
            sum(
                (item.unit_price * item.quantity * item.tax_rate / 100 for item in self.items),
                Decimal("0"),
            )
        )

    @property
    def total(self) -> Decimal:
        # 1 loyalty point = ₹1 when redeemed.
        return money(
            self.subtotal
            + self.tax_amount
            - to_decimal(self.discount_amount)
            - to_decimal(self.rule_discount_amount)
            - to_decimal(self.credit_applied)
            - to_decimal(self.points_redeemed)
        )


class SaleItem(Base, TimestampMixin, TenantMixin):
    __tablename__ = "sale_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"))
    variant_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    quantity: Mapped[Decimal] = mapped_column(QuantityType, default=Decimal("1"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)

    sale: Mapped["Sale"] = relationship(back_populates="items")
    variant: Mapped["Item"] = relationship()  # noqa: F821
