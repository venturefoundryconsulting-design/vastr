from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.core.tenant_context import tenant_scope
from app.models.outlet import Outlet
from app.models.settings import AppSettings
from app.models.tenant import SubscriptionStatus, Tenant
from app.models.user import User, UserRole
from app.schemas.auth import CurrentUser, LoginRequest, RegisterRequest, SlugAvailability, TokenResponse
from app.services.audit import log_activity

router = APIRouter(prefix="/api/auth", tags=["auth"])

_BLOCKED_SUBSCRIPTION_STATUSES = {SubscriptionStatus.SUSPENDED, SubscriptionStatus.CANCELLED}

_TRIAL_DAYS = 30


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User is inactive")
    # Super Admins have no tenant (see User.tenant_id) and skip this check entirely.
    if user.tenant_id is not None:
        tenant = db.get(Tenant, user.tenant_id)
        if not tenant or not tenant.is_active:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is no longer available")
        if tenant.subscription_status in _BLOCKED_SUBSCRIPTION_STATUSES:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Your organization's subscription is {tenant.subscription_status.value} - "
                "contact your administrator",
            )
    token = create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.role.value, "tenant_id": user.tenant_id},
    )
    log_activity(
        db, action="auth.login", tenant_id=user.tenant_id, user_id=user.id,
        entity_type="User", entity_id=user.id,
    )
    db.commit()
    return TokenResponse(access_token=token)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    """Self-service store registration. Creates a tenant, a Tenant Owner user,
    a default outlet, and default AppSettings, then returns a JWT so the
    user lands directly in their new workspace."""
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email is already registered")
    if db.query(Tenant).filter(Tenant.slug == payload.slug).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That store URL is already taken")

    trial_end = date.today() + timedelta(days=_TRIAL_DAYS)
    tenant = Tenant(
        company_name=payload.company_name,
        slug=payload.slug,
        subscription_plan=payload.plan,
        subscription_status=SubscriptionStatus.TRIAL,
        trial_end=trial_end,
        is_active=True,
    )
    db.add(tenant)
    db.flush()

    owner = User(
        name=payload.owner_name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=UserRole.TENANT_OWNER,
        tenant_id=tenant.id,
        is_active=True,
    )
    db.add(owner)

    with tenant_scope(tenant.id):
        db.add(Outlet(name=payload.company_name))
        db.add(AppSettings(tenant_id=tenant.id, business_name=payload.company_name))

    log_activity(
        db, action="tenant.registered", tenant_id=tenant.id, user_id=None,
        entity_type="Tenant", entity_id=tenant.id,
        details={"company_name": payload.company_name, "slug": payload.slug, "plan": payload.plan.value},
    )
    db.commit()
    db.refresh(owner)

    token = create_access_token(
        subject=str(owner.id),
        extra_claims={"role": owner.role.value, "tenant_id": owner.tenant_id},
    )
    return TokenResponse(access_token=token)


@router.get("/check-slug", response_model=SlugAvailability)
def check_slug(slug: str = Query(..., min_length=3, max_length=40), db: Session = Depends(get_db)):
    slug = slug.lower().strip()
    taken = db.query(Tenant).filter(Tenant.slug == slug).first() is not None
    return SlugAvailability(slug=slug, available=not taken)


@router.get("/me", response_model=CurrentUser)
def me(current_user: User = Depends(get_current_user)):
    return current_user
