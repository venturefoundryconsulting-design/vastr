"""Per-plan module feature flags - architecture only, not enforcement.

Every module is seeded `true` on every plan (see the Phase 3 migration), and
has_feature() isn't called from any endpoint yet - toggling a module off for
a plan is future work, this just makes the toggle exist in the schema ahead
of billing, per the spec's explicit "prepare architecture, don't gate yet."
"""

from sqlalchemy.orm import Session

from app.models.subscription_plan import SubscriptionPlan
from app.models.tenant import Tenant

# Existing app modules plus a few named in the original spec that don't exist
# yet (wholesale, manufacturing, ecommerce, ai) - included now so a plan's
# feature set doesn't need a schema change when those modules eventually land.
FEATURE_CATALOG: list[str] = [
    "pos",
    "inventory",
    "crm",
    "reports",
    "analytics",
    "marketing",
    "alterations",
    "hrm",
    "payroll",
    "wholesale",
    "manufacturing",
    "ecommerce",
    "ai",
]


def has_feature(db: Session, tenant: Tenant, code: str) -> bool:
    """Fails open (True) if the plan or the specific code isn't configured -
    a missing row should never be able to silently disable a module."""
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.name == tenant.subscription_plan).first()
    if not plan:
        return True
    return bool(plan.features.get(code, True))
