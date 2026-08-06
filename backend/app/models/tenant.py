import enum

from sqlalchemy import Boolean, Date, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class SubscriptionStatus(str, enum.Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class SubscriptionPlanName(str, enum.Enum):
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class Tenant(Base, TimestampMixin):
    """A single company/customer on the Velora platform. Every tenant-owned row
    across the schema carries a tenant_id pointing here (see TenantMixin)."""

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    logo: Mapped[str | None] = mapped_column(String(500), default=None)
    primary_color: Mapped[str | None] = mapped_column(String(20), default=None)
    timezone: Mapped[str] = mapped_column(String(60), default="Asia/Kolkata")
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    country: Mapped[str | None] = mapped_column(String(80), default=None)

    subscription_plan: Mapped[SubscriptionPlanName] = mapped_column(
        Enum(SubscriptionPlanName), default=SubscriptionPlanName.FREE
    )
    subscription_status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus), default=SubscriptionStatus.TRIAL
    )
    trial_end: Mapped[Date | None] = mapped_column(Date, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
