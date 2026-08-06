from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin
from app.models.user import UserRole


class Permission(Base, TimestampMixin):
    """Global capability catalog (not tenant-scoped - the set of things the app
    *can* gate is a platform concern; which roles get which is RolePermission).

    code is a "module.action" string, e.g. "products.edit", "reports.view".
    """

    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(String(200))


class RolePermission(Base, TimestampMixin):
    """Which roles get which permissions - platform-defined defaults, not yet
    customizable per tenant (see Phase 2 plan notes: a full per-tenant role
    builder is future scope, this is the architecture it would plug into).
    """

    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role", "permission_id", name="uq_role_permission"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), index=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id"))

    permission: Mapped["Permission"] = relationship()
