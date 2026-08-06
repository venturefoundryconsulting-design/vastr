from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.security import create_access_token, verify_password
from app.models.tenant import SubscriptionStatus, Tenant
from app.models.user import User
from app.schemas.auth import CurrentUser, LoginRequest, TokenResponse
from app.services.audit import log_activity

router = APIRouter(prefix="/api/auth", tags=["auth"])

_BLOCKED_SUBSCRIPTION_STATUSES = {SubscriptionStatus.SUSPENDED, SubscriptionStatus.CANCELLED}


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


@router.get("/me", response_model=CurrentUser)
def me(current_user: User = Depends(get_current_user)):
    return current_user
