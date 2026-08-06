from collections.abc import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.core.tenant_context import set_current_tenant_id
from app.models.user import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None or "sub" not in payload:
        raise credentials_exception
    # User isn't tenant-filtered here (it's excluded from TenantMixin, see
    # app.models.user) - a user looking themselves up by their own id from a
    # validly-signed token is always safe regardless of tenant scoping.
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise credentials_exception
    # Every other query this request makes now auto-filters/auto-stamps by this
    # tenant (see app.core.tenant_context) - callers never pass tenant_id.
    set_current_tenant_id(user.tenant_id)
    return user


def require_roles(*roles: UserRole):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not enough permissions")
        return user

    return checker


require_admin = require_roles(UserRole.ADMIN)
require_manager_up = require_roles(UserRole.ADMIN, UserRole.MANAGER)
