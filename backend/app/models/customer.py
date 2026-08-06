import enum

from sqlalchemy import JSON, Boolean, Date, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(20), index=True, default=None)
    email: Mapped[str | None] = mapped_column(String(255), default=None)
    # Full international format e.g. 91XXXXXXXXXX, used for wa.me links / Cloud API
    whatsapp_number: Mapped[str | None] = mapped_column(String(20), default=None)

    is_gst_customer: Mapped[bool] = mapped_column(Boolean, default=False)
    gstin: Mapped[str | None] = mapped_column(String(20), default=None)

    birthday: Mapped["Date | None"] = mapped_column(Date, default=None)
    anniversary: Mapped["Date | None"] = mapped_column(Date, default=None)

    # JSON array of strings - portable across Postgres/MySQL, unlike Postgres's native
    # ARRAY type. Tag matching uses func.json_contains() (see routers/customers.py,
    # services/campaigns.py) instead of the Postgres-only .any() operator.
    preferred_sizes: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_colors: Mapped[list[str]] = mapped_column(JSON, default=list)
    favorite_brands: Mapped[list[str]] = mapped_column(JSON, default=list)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)

    notes: Mapped[str | None] = mapped_column(String(2000), default=None)

    # Signed balance: positive = store owes customer credit, negative = customer owes the store.
    credit_balance: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    loyalty_points: Mapped[int] = mapped_column(default=0)
    # VIP members earn loyalty points at 2x the normal rate.
    is_vip: Mapped[bool] = mapped_column(Boolean, default=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    addresses: Mapped[list["CustomerAddress"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )
    balance_adjustments: Mapped[list["CustomerBalanceAdjustment"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )
    loyalty_adjustments: Mapped[list["CustomerLoyaltyAdjustment"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )


class CustomerAddress(Base, TimestampMixin):
    __tablename__ = "customer_addresses"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    label: Mapped[str | None] = mapped_column(String(40), default=None)
    line1: Mapped[str] = mapped_column(String(255))
    line2: Mapped[str | None] = mapped_column(String(255), default=None)
    city: Mapped[str | None] = mapped_column(String(100), default=None)
    state: Mapped[str | None] = mapped_column(String(100), default=None)
    pincode: Mapped[str | None] = mapped_column(String(10), default=None)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    customer: Mapped["Customer"] = relationship(back_populates="addresses")


class BalanceType(str, enum.Enum):
    CREDIT = "credit"
    OUTSTANDING = "outstanding"


class CustomerBalanceAdjustment(Base, TimestampMixin):
    """Immutable audit trail of every credit_balance change, mirrors StockMovement."""

    __tablename__ = "customer_balance_adjustments"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    balance_type: Mapped[BalanceType] = mapped_column(Enum(BalanceType), default=BalanceType.CREDIT)
    amount_delta: Mapped[float] = mapped_column(Numeric(10, 2))
    reference_type: Mapped[str | None] = mapped_column(String(40), default=None)
    reference_id: Mapped[int | None] = mapped_column(default=None)
    reason: Mapped[str | None] = mapped_column(String(255), default=None)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)

    customer: Mapped["Customer"] = relationship(back_populates="balance_adjustments")


class CustomerLoyaltyAdjustment(Base, TimestampMixin):
    """Immutable audit trail of every loyalty_points change (earn, redeem, or manual bonus)."""

    __tablename__ = "customer_loyalty_adjustments"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    points_delta: Mapped[int] = mapped_column()
    reference_type: Mapped[str | None] = mapped_column(String(40), default=None)
    reference_id: Mapped[int | None] = mapped_column(default=None)
    reason: Mapped[str | None] = mapped_column(String(255), default=None)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)

    customer: Mapped["Customer"] = relationship(back_populates="loyalty_adjustments")
