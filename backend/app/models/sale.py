import enum

from sqlalchemy import Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin


class PaymentMode(str, enum.Enum):
    CASH = "cash"
    CARD = "card"
    UPI = "upi"
    OTHER = "other"


class Sale(Base, TimestampMixin):
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(30), unique=True, index=True)
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
    def subtotal(self) -> float:
        return sum(float(item.unit_price) * item.quantity for item in self.items)

    @property
    def tax_amount(self) -> float:
        return sum(
            float(item.unit_price) * item.quantity * float(item.tax_rate) / 100 for item in self.items
        )

    @property
    def total(self) -> float:
        # 1 loyalty point = ₹1 when redeemed.
        return round(
            self.subtotal
            + self.tax_amount
            - float(self.discount_amount)
            - float(self.rule_discount_amount)
            - float(self.credit_applied)
            - self.points_redeemed,
            2,
        )


class SaleItem(Base, TimestampMixin):
    __tablename__ = "sale_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"))
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=0)

    sale: Mapped["Sale"] = relationship(back_populates="items")
    variant: Mapped["ProductVariant"] = relationship()  # noqa: F821
