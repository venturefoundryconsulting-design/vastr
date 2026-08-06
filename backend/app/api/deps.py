from collections.abc import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    """Tenant context (see app.core.tenant_context) is NOT set here - it's set
    by app.middleware.tenant.TenantContextMiddleware, before FastAPI's
    dependency injection even begins. That's a deliberate placement, not
    redundancy: sync dependencies each run in their own threadpool call with
    their own ContextVar snapshot, so a mutation made in this function would
    never be visible to the endpoint body that actually runs the query. This
    function only authenticates - it doesn't and can't reliably scope.
    """
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
    return user


def require_roles(*roles: UserRole):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not enough permissions")
        return user

    return checker


# Tenant Owner is, by definition, at least as privileged as Admin within its
# own tenant (see app.permissions.catalog's ROLE_GRANTS, which already grants
# it every permission Admin has) - every existing require_admin/
# require_manager_up gate needs to include it too, or a brand-new tenant's
# very first user (always created as Owner - see routers/admin.py's
# create_tenant) would be locked out of Outlets/Users/Settings/Payroll/etc.
# on day one.
require_admin = require_roles(UserRole.ADMIN, UserRole.TENANT_OWNER)
require_manager_up = require_roles(UserRole.ADMIN, UserRole.TENANT_OWNER, UserRole.MANAGER)


def require_super_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Super Admin access required")
    return user


def require_permission(code: str):
    """Capability-based alternative to require_roles(), for the new roles
    (tenant_owner/sales/inventory/viewer) that don't fit the original rank
    ladder - see app.permissions.catalog for what each role is granted.
    """

    def checker(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        from app.permissions.service import has_permission

        if not has_permission(db, user, code):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not enough permissions")
        return user

    return checker
