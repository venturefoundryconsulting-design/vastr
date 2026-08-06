import enum

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TenantMixin, TimestampMixin


class DiscountType(str, enum.Enum):
    PERCENTAGE = "percentage"
    FLAT = "flat"
    BOGO = "bogo"


class DiscountScope(str, enum.Enum):
    ALL = "all"
    CATEGORY = "category"
    BRAND = "brand"
    PRODUCT = "product"


class DiscountRule(Base, TimestampMixin, TenantMixin):
    """A promotional rule, applied either automatically or via a coupon code.

    A null `code` means the rule is evaluated automatically against every cart;
    a set `code` means it only applies when a customer/staff enters that code.
    """

    __tablename__ = "discount_rules"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_discount_tenant_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str | None] = mapped_column(String(40), index=True, default=None)
    discount_type: Mapped[DiscountType] = mapped_column(Enum(DiscountType))
    scope: Mapped[DiscountScope] = mapped_column(Enum(DiscountScope), default=DiscountScope.ALL)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), default=None)
    brand: Mapped[str | None] = mapped_column(String(120), default=None)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), default=None)
    vip_only: Mapped[bool] = mapped_column(Boolean, default=False)

    # Percentage (e.g. 10 = 10%) or flat rupee amount, depending on discount_type.
    value: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    max_discount_amount: Mapped[float | None] = mapped_column(Numeric(10, 2), default=None)
    min_purchase_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)

    # Only used when discount_type == BOGO, e.g. buy 2 get 1 free.
    buy_quantity: Mapped[int | None] = mapped_column(Integer, default=None)
    get_quantity: Mapped[int | None] = mapped_column(Integer, default=None)

    start_date: Mapped[Date | None] = mapped_column(Date, default=None)
    end_date: Mapped[Date | None] = mapped_column(Date, default=None)

    usage_limit: Mapped[int | None] = mapped_column(Integer, default=None)
    times_used: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    category: Mapped["Category | None"] = relationship()  # noqa: F821
    product: Mapped["Product | None"] = relationship()  # noqa: F821
