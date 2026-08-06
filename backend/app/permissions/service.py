from sqlalchemy.orm import Session

from app.models.permission import Permission, RolePermission
from app.models.user import User, UserRole


def has_permission(db: Session, user: User, code: str) -> bool:
    """Super Admins and legacy Admin/Tenant Owner roles always pass (kept in
    sync with ROLE_GRANTS granting them everything, but checked explicitly
    here too so a missing catalog seed never silently locks out an owner).
    """
    if user.role in (UserRole.SUPER_ADMIN, UserRole.TENANT_OWNER, UserRole.ADMIN):
        return True
    grant = (
        db.query(RolePermission)
        .join(Permission, RolePermission.permission_id == Permission.id)
        .filter(RolePermission.role == user.role, Permission.code == code)
        .first()
    )
    return grant is not None
