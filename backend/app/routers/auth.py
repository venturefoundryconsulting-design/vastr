import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.core.preset_logos import random_preset_logo_url
from app.core.security import create_access_token, hash_password, verify_password
from app.core.tenant_context import tenant_scope
from app.models.outlet import Outlet
from app.models.platform_settings import PlatformDomainConfig
from app.models.settings import AppSettings
from app.models.tenant import SubscriptionStatus, Tenant
from app.models.user import User, UserRole
from app.schemas.auth import (
    CurrentUser,
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationRequest,
    SlugAvailability,
    TokenResponse,
)
from app.services import platform_email
from app.services.audit import log_activity

router = APIRouter(prefix="/api/auth", tags=["auth"])

_BLOCKED_SUBSCRIPTION_STATUSES = {SubscriptionStatus.SUSPENDED, SubscriptionStatus.CANCELLED}
_TRIAL_DAYS = 30
_VERIFICATION_TOKEN_BYTES = 32


def _issue_token(user: User) -> str:
    return create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.role.value, "tenant_id": user.tenant_id},
    )


def _send_verification_email(db: Session, user: User) -> None:
    verify_url = f"{settings.FRONTEND_BASE_URL}/verify-email?token={user.verification_token}"
    body = (
        f"Hi {user.name},\n\n"
        "Welcome to Vastr! Confirm your email address to activate your store:\n\n"
        f"{verify_url}\n\n"
        "If you didn't create this account, you can ignore this email."
    )
    try:
        platform_email.send_email(db, user.email, "Verify your Vastr account", body)
    except platform_email.PlatformEmailNotConfigured:
        # Dev/pre-launch fallback: platform SMTP isn't set up yet (Global
        # Settings > Email). Don't fail the signup over it - log the link so
        # it's still reachable for testing/manual handoff until it is.
        print(f"[auth] Platform SMTP not configured - verification link for {user.email}: {verify_url}")


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User is inactive")
    # Super Admins are trusted platform operators, not self-service signups -
    # they're exempt from the verification gate entirely.
    if user.role != UserRole.SUPER_ADMIN and user.email_verified_at is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Please verify your email address before logging in - check your inbox for the link, "
            "or request a new one.",
        )
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
    token = _issue_token(user)
    log_activity(
        db, action="auth.login", tenant_id=user.tenant_id, user_id=user.id,
        entity_type="User", entity_id=user.id,
    )
    db.commit()
    return TokenResponse(access_token=token)


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    """Self-service store registration. Creates a tenant, a Tenant Owner user
    (unverified), a default outlet, and default AppSettings, then emails a
    verification link - the owner is logged in once they click it (see
    GET /verify-email), not immediately on registration."""
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email is already registered")
    if db.query(Tenant).filter(Tenant.slug == payload.slug).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That store URL is already taken")
    domain_config = db.query(PlatformDomainConfig).first()
    if domain_config and payload.slug in set(domain_config.reserved_slugs or []):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That store URL is reserved")

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
        verification_token=secrets.token_urlsafe(_VERIFICATION_TOKEN_BYTES),
        verification_sent_at=datetime.now(timezone.utc),
    )
    db.add(owner)

    # tenant_scope must still be active when the flush actually happens (the
    # before_flush auto-stamp listener reads the ContextVar at flush time, not
    # at db.add() time) - so db.commit() has to stay inside this block.
    with tenant_scope(tenant.id):
        db.add(Outlet(name=payload.company_name, code="MAIN"))
        db.add(AppSettings(
            tenant_id=tenant.id, business_name=payload.company_name, logo_url=random_preset_logo_url(),
        ))
        log_activity(
            db, action="tenant.registered", tenant_id=tenant.id, user_id=None,
            entity_type="Tenant", entity_id=tenant.id,
            details={"company_name": payload.company_name, "slug": payload.slug, "plan": payload.plan.value},
        )
        db.commit()
    db.refresh(owner)

    _send_verification_email(db, owner)

    return RegisterResponse(email=owner.email)


@router.get("/verify-email", response_model=TokenResponse)
def verify_email(token: str = Query(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.verification_token == token).first()
    if not user:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "This verification link is invalid or has already been used"
        )
    user.email_verified_at = datetime.now(timezone.utc)
    user.verification_token = None
    log_activity(
        db, action="auth.email_verified", tenant_id=user.tenant_id, user_id=user.id,
        entity_type="User", entity_id=user.id,
    )
    db.commit()
    return TokenResponse(access_token=_issue_token(user))


@router.post("/resend-verification")
def resend_verification(payload: ResendVerificationRequest, db: Session = Depends(get_db)) -> dict:
    user = db.query(User).filter(User.email == payload.email).first()
    # Same generic response whether or not the account exists / is already
    # verified, so this endpoint can't be used to probe registered emails.
    if user and user.email_verified_at is None:
        user.verification_token = secrets.token_urlsafe(_VERIFICATION_TOKEN_BYTES)
        user.verification_sent_at = datetime.now(timezone.utc)
        db.commit()
        _send_verification_email(db, user)
    return {"message": "If that email exists and isn't verified yet, a new link has been sent."}


@router.get("/check-slug", response_model=SlugAvailability)
def check_slug(slug: str = Query(..., min_length=3, max_length=40), db: Session = Depends(get_db)):
    slug = slug.lower().strip()
    taken = db.query(Tenant).filter(Tenant.slug == slug).first() is not None
    return SlugAvailability(slug=slug, available=not taken)


@router.get("/me", response_model=CurrentUser)
def me(current_user: User = Depends(get_current_user)):
    return current_user
