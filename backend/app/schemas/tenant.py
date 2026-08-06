from datetime import date

from pydantic import BaseModel

from app.models.tenant import SubscriptionPlanName, SubscriptionStatus


class TenantSelfOut(BaseModel):
    """What a tenant's own users see about their tenant - includes the
    read-only subscription fields (for the Subscription page) but those
    aren't in TenantSelfUpdate below: changing plan/status is Super Admin
    only (see app.routers.admin), not tenant self-service.
    """

    id: int
    company_name: str
    slug: str
    logo: str | None
    primary_color: str | None
    timezone: str
    currency: str
    country: str | None
    subscription_plan: SubscriptionPlanName
    subscription_status: SubscriptionStatus
    trial_end: date | None

    model_config = {"from_attributes": True}


class TenantSelfUpdate(BaseModel):
    company_name: str | None = None
    primary_color: str | None = None
    timezone: str | None = None
    currency: str | None = None
    country: str | None = None
