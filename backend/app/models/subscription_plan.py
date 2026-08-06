from sqlalchemy import Enum, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin
from app.models.tenant import SubscriptionPlanName


class SubscriptionPlan(Base, TimestampMixin):
    """Global reference table (one row per SubscriptionPlanName, not per
    tenant) describing what each plan includes. Tenant.subscription_plan
    stays the plain enum column added in Phase 1 - this table is looked up
    by that same value rather than a literal FK, so no column-type migration
    was needed to add it.

    Architecture only, per the spec's explicit "don't implement billing or
    feature gating yet": every module is seeded `true` on every plan, and
    has_feature() isn't called from any endpoint. Flipping a module off for
    a plan later is a data change here, not a code change.
    """

    __tablename__ = "subscription_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[SubscriptionPlanName] = mapped_column(Enum(SubscriptionPlanName), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    # Billing isn't implemented - these are placeholders for when it is.
    monthly_price: Mapped[float | None] = mapped_column(Numeric(10, 2), default=None)
    max_users: Mapped[int | None] = mapped_column(Integer, default=None)
    max_outlets: Mapped[int | None] = mapped_column(Integer, default=None)
    # {"pos": true, "reports": true, ...} - see FEATURE_CATALOG in
    # app.services.feature_flags for the full code list and has_feature().
    features: Mapped[dict] = mapped_column(JSONB, default=dict)
