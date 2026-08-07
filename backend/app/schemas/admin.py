from datetime import date, datetime

from pydantic import BaseModel

from app.models.tenant import SubscriptionPlanName, SubscriptionStatus


class TenantCreate(BaseModel):
    company_name: str
    slug: str
    primary_color: str | None = None
    timezone: str = "Asia/Kolkata"
    currency: str = "INR"
    country: str | None = None
    subscription_plan: SubscriptionPlanName = SubscriptionPlanName.FREE
    trial_end: date | None = None
    # The tenant's first user (becomes its tenant_owner).
    owner_name: str
    owner_email: str
    owner_password: str


class TenantUpdate(BaseModel):
    company_name: str | None = None
    primary_color: str | None = None
    timezone: str | None = None
    currency: str | None = None
    country: str | None = None
    subscription_plan: SubscriptionPlanName | None = None
    subscription_status: SubscriptionStatus | None = None
    trial_end: date | None = None
    is_active: bool | None = None


class TenantOut(BaseModel):
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
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TenantUsageOut(BaseModel):
    tenant_id: int
    user_count: int
    active_user_count: int
    outlet_count: int
    product_count: int
    # Row-count proxy, not actual bytes - a real disk-usage figure needs a
    # filesystem walk of uploads/tenant-{id}/, deferred to when that's cheap
    # to compute (e.g. behind a cache) rather than done on every admin request.
    estimated_record_count: int


class ResetPasswordRequest(BaseModel):
    new_password: str


class AuditLogOut(BaseModel):
    id: int
    tenant_id: int | None
    user_id: int | None
    action: str
    entity_type: str | None
    entity_id: int | None
    details: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


class GlobalAuditLogOut(AuditLogOut):
    tenant_name: str | None = None
    user_name: str | None = None


class PlanCountOut(BaseModel):
    plan: SubscriptionPlanName
    count: int


class RecentSignupOut(BaseModel):
    id: int
    company_name: str
    slug: str
    subscription_plan: SubscriptionPlanName
    created_at: datetime

    model_config = {"from_attributes": True}


class PlatformOverviewOut(BaseModel):
    total_tenants: int
    active_tenants: int
    trialing_tenants: int
    paying_tenants: int
    suspended_tenants: int
    new_signups_7d: int
    new_signups_30d: int
    estimated_arr: float
    plan_breakdown: list[PlanCountOut]
    recent_signups: list[RecentSignupOut]


class PaymentOut(BaseModel):
    id: int
    tenant_id: int | None
    tenant_name: str | None = None
    plan: str
    amount: float
    currency: str
    status: str
    razorpay_order_id: str
    razorpay_payment_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
