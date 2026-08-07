from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_super_admin
from app.core.preset_logos import random_preset_logo_url
from app.core.security import hash_password
from app.core.tenant_context import tenant_scope
from app.models.audit import AuditLog
from app.models.outlet import Outlet
from app.models.platform_settings import Payment
from app.models.product import Product
from app.models.settings import AppSettings
from app.models.tenant import SubscriptionPlanName, SubscriptionStatus, Tenant
from app.models.user import User, UserRole
from app.schemas.admin import (
    AuditLogOut,
    GlobalAuditLogOut,
    PaymentOut,
    PlanCountOut,
    PlatformOverviewOut,
    RecentSignupOut,
    ResetPasswordRequest,
    TenantCreate,
    TenantOut,
    TenantUpdate,
    TenantUsageOut,
)
from app.schemas.user import UserOut
from app.services.audit import log_activity

# Rough ARR estimate only - Enterprise is custom-quoted (no self-serve price),
# so it's excluded from the sum rather than guessed at.
_ANNUAL_PLAN_PRICE = {
    SubscriptionPlanName.FREE: 0,
    SubscriptionPlanName.STARTER: 1999,
    SubscriptionPlanName.PROFESSIONAL: 4999,
}

# Cross-tenant access for this router is granted by app.middleware.tenant -
# it reads the JWT's role/tenant_id claims directly (a role check here, in a
# dependency, can't retroactively widen the request's tenant scope; see that
# middleware's docstring for why). require_super_admin below still does the
# actual auth/role enforcement (401/403) - the middleware only decides query
# scope, it never skips authentication.
router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_super_admin)])


@router.get("/tenants", response_model=list[TenantOut])
def list_tenants(q: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Tenant)
    if q:
        like = f"%{q}%"
        query = query.filter((Tenant.company_name.ilike(like)) | (Tenant.slug.ilike(like)))
    return query.order_by(Tenant.company_name).all()


@router.post("/tenants", response_model=TenantOut)
def create_tenant(payload: TenantCreate, db: Session = Depends(get_db), admin: User = Depends(require_super_admin)):
    if db.query(Tenant).filter(Tenant.slug == payload.slug).first():
        raise HTTPException(400, "Slug already in use")
    if db.query(User).filter(User.email == payload.owner_email).first():
        raise HTTPException(400, "Email already registered")

    tenant = Tenant(
        company_name=payload.company_name,
        slug=payload.slug,
        primary_color=payload.primary_color,
        timezone=payload.timezone,
        currency=payload.currency,
        country=payload.country,
        subscription_plan=payload.subscription_plan,
        subscription_status=SubscriptionStatus.TRIAL,
        trial_end=payload.trial_end,
    )
    db.add(tenant)
    db.flush()

    owner = User(
        tenant_id=tenant.id,
        name=payload.owner_name,
        email=payload.owner_email,
        hashed_password=hash_password(payload.owner_password),
        role=UserRole.TENANT_OWNER,
        # Administrative creation, not open self-serve signup - trusted
        # immediately rather than requiring the owner to click an email link.
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(owner)

    # tenant_scope must stay active through the actual flush (db.commit()),
    # since the auto-stamp listener reads the ContextVar at flush time.
    with tenant_scope(tenant.id):
        db.add(Outlet(name=payload.company_name, code="MAIN"))
        db.add(AppSettings(
            tenant_id=tenant.id, business_name=payload.company_name, logo_url=random_preset_logo_url(),
        ))
        log_activity(
            db, action="tenant.create", tenant_id=tenant.id, user_id=admin.id,
            entity_type="Tenant", entity_id=tenant.id, details={"company_name": tenant.company_name},
        )
        db.commit()
    db.refresh(tenant)
    return tenant


@router.get("/tenants/{tenant_id}", response_model=TenantOut)
def get_tenant(tenant_id: int, db: Session = Depends(get_db)):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    return tenant


@router.patch("/tenants/{tenant_id}", response_model=TenantOut)
def update_tenant(
    tenant_id: int,
    payload: TenantUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_super_admin),
):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    changed = payload.model_dump(exclude_unset=True)
    for field, value in changed.items():
        setattr(tenant, field, value)
    log_activity(
        db, action="tenant.update", tenant_id=tenant.id, user_id=admin.id,
        entity_type="Tenant", entity_id=tenant.id, details={"fields": list(changed.keys())},
    )
    db.commit()
    db.refresh(tenant)
    return tenant


@router.post("/tenants/{tenant_id}/suspend", response_model=TenantOut)
def suspend_tenant(tenant_id: int, db: Session = Depends(get_db), admin: User = Depends(require_super_admin)):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    tenant.subscription_status = SubscriptionStatus.SUSPENDED
    log_activity(
        db, action="tenant.suspend", tenant_id=tenant.id, user_id=admin.id, entity_type="Tenant", entity_id=tenant.id,
    )
    db.commit()
    db.refresh(tenant)
    return tenant


@router.delete("/tenants/{tenant_id}", response_model=TenantOut)
def delete_tenant(tenant_id: int, db: Session = Depends(get_db), admin: User = Depends(require_super_admin)):
    """Soft-delete: deactivates the tenant and cancels its subscription rather
    than cascading a hard delete across ~30 related tables. A true irreversible
    hard-delete is a separate, deliberately harder-to-reach operation that this
    phase doesn't add - losing a paying customer's data by accident is a much
    worse failure mode than a suspended tenant staying in the database.
    """
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    tenant.is_active = False
    tenant.subscription_status = SubscriptionStatus.CANCELLED
    log_activity(
        db, action="tenant.delete", tenant_id=tenant.id, user_id=admin.id, entity_type="Tenant", entity_id=tenant.id,
    )
    db.commit()
    db.refresh(tenant)
    return tenant


@router.get("/tenants/{tenant_id}/usage", response_model=TenantUsageOut)
def tenant_usage(tenant_id: int, db: Session = Depends(get_db)):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    user_count = db.query(User).filter(User.tenant_id == tenant_id).count()
    active_user_count = db.query(User).filter(User.tenant_id == tenant_id, User.is_active.is_(True)).count()
    outlet_count = db.query(Outlet).filter(Outlet.tenant_id == tenant_id).count()
    product_count = db.query(Product).filter(Product.tenant_id == tenant_id).count()
    return TenantUsageOut(
        tenant_id=tenant_id,
        user_count=user_count,
        active_user_count=active_user_count,
        outlet_count=outlet_count,
        product_count=product_count,
        estimated_record_count=user_count + outlet_count + product_count,
    )


@router.get("/tenants/{tenant_id}/users", response_model=list[UserOut])
def list_tenant_users(tenant_id: int, db: Session = Depends(get_db)):
    return db.query(User).filter(User.tenant_id == tenant_id).order_by(User.name).all()


@router.post("/tenants/{tenant_id}/users/{user_id}/reset-password", response_model=dict)
def reset_user_password(
    tenant_id: int,
    user_id: int,
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_super_admin),
):
    user = db.query(User).filter(User.id == user_id, User.tenant_id == tenant_id).first()
    if not user:
        raise HTTPException(404, "User not found in this tenant")
    user.hashed_password = hash_password(payload.new_password)
    log_activity(
        db, action="user.password_reset", tenant_id=tenant_id, user_id=admin.id,
        entity_type="User", entity_id=user.id, details={"reset_by": "super_admin"},
    )
    db.commit()
    return {"ok": True}


@router.get("/tenants/{tenant_id}/activity", response_model=list[AuditLogOut])
def tenant_activity(tenant_id: int, limit: int = 100, db: Session = Depends(get_db)):
    return (
        db.query(AuditLog)
        .filter(AuditLog.tenant_id == tenant_id)
        .order_by(AuditLog.created_at.desc())
        .limit(min(limit, 500))
        .all()
    )


@router.get("/overview", response_model=PlatformOverviewOut)
def platform_overview(db: Session = Depends(get_db)):
    """Aggregate platform stats for the Super Admin landing page - the only
    view of "how is Vastr doing across every tenant" that exists today."""
    tenants = db.query(Tenant).all()
    now = datetime.now(timezone.utc)
    since_7d = now - timedelta(days=7)
    since_30d = now - timedelta(days=30)

    def _naive_aware(dt: datetime) -> datetime:
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    plan_counts: dict[SubscriptionPlanName, int] = {}
    estimated_arr = 0.0
    paying = 0
    for t in tenants:
        plan_counts[t.subscription_plan] = plan_counts.get(t.subscription_plan, 0) + 1
        if t.subscription_status == SubscriptionStatus.ACTIVE:
            paying += 1
            estimated_arr += _ANNUAL_PLAN_PRICE.get(t.subscription_plan, 0)

    recent = sorted(tenants, key=lambda t: t.created_at, reverse=True)[:8]

    return PlatformOverviewOut(
        total_tenants=len(tenants),
        active_tenants=sum(1 for t in tenants if t.is_active),
        trialing_tenants=sum(1 for t in tenants if t.subscription_status == SubscriptionStatus.TRIAL),
        paying_tenants=paying,
        suspended_tenants=sum(1 for t in tenants if t.subscription_status == SubscriptionStatus.SUSPENDED),
        new_signups_7d=sum(1 for t in tenants if _naive_aware(t.created_at) >= since_7d),
        new_signups_30d=sum(1 for t in tenants if _naive_aware(t.created_at) >= since_30d),
        estimated_arr=estimated_arr,
        plan_breakdown=[PlanCountOut(plan=p, count=c) for p, c in plan_counts.items()],
        recent_signups=[RecentSignupOut.model_validate(t) for t in recent],
    )


@router.get("/activity", response_model=list[GlobalAuditLogOut])
def global_activity(limit: int = 100, db: Session = Depends(get_db)):
    """Platform-wide activity feed across every tenant - complements the
    per-tenant Activity tab on the Tenant Detail page."""
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500)).all()
    tenant_ids = {r.tenant_id for r in rows if r.tenant_id}
    user_ids = {r.user_id for r in rows if r.user_id}
    tenant_names = {t.id: t.company_name for t in db.query(Tenant).filter(Tenant.id.in_(tenant_ids)).all()}
    user_names = {u.id: u.name for u in db.query(User).filter(User.id.in_(user_ids)).all()}
    return [
        GlobalAuditLogOut(
            id=r.id, tenant_id=r.tenant_id, user_id=r.user_id, action=r.action,
            entity_type=r.entity_type, entity_id=r.entity_id, details=r.details, created_at=r.created_at,
            tenant_name=tenant_names.get(r.tenant_id), user_name=user_names.get(r.user_id),
        )
        for r in rows
    ]


@router.get("/payments", response_model=list[PaymentOut])
def list_payments(limit: int = 100, db: Session = Depends(get_db)):
    """Every Razorpay order created for a tenant's subscription - the
    "Subscriptions" screen's transaction history."""
    rows = db.query(Payment).order_by(Payment.created_at.desc()).limit(min(limit, 500)).all()
    tenant_ids = {r.tenant_id for r in rows if r.tenant_id}
    tenant_names = {t.id: t.company_name for t in db.query(Tenant).filter(Tenant.id.in_(tenant_ids)).all()}
    return [
        PaymentOut(
            id=r.id, tenant_id=r.tenant_id, tenant_name=tenant_names.get(r.tenant_id),
            plan=r.plan, amount=float(r.amount), currency=r.currency, status=r.status,
            razorpay_order_id=r.razorpay_order_id, razorpay_payment_id=r.razorpay_payment_id,
            created_at=r.created_at,
        )
        for r in rows
    ]
