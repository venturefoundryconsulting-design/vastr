import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin


class UserRole(str, enum.Enum):
    # Platform-level - not a member of any tenant (see User.tenant_id below).
    SUPER_ADMIN = "super_admin"
    # Tenant-scoped roles. ADMIN/MANAGER/OUTLET_STAFF are the original three and
    # their relative rank (see frontend src/utils/roles.ts) is unchanged - the
    # four new ones are resolved through the permission catalog instead
    # (app.permissions), not folded into that rank ladder.
    TENANT_OWNER = "tenant_owner"
    ADMIN = "admin"
    MANAGER = "manager"
    SALES = "sales"
    INVENTORY = "inventory"
    OUTLET_STAFF = "outlet_staff"
    # Phase 3F. Deliberately outside the admin>manager>staff rank ladder: a
    # tailor outranks nobody yet needs write access to their own work orders,
    # which rank-based checks cannot express. Resolved via has_permission only.
    TAILOR = "tailor"
    VIEWER = "viewer"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nullable: platform Super Admins aren't members of any tenant. Every other
    # role must have one - enforced in app code, not the DB, so the same User
    # model can represent both without two tables.
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), index=True, default=None)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.OUTLET_STAFF)
    outlet_id: Mapped[int | None] = mapped_column(ForeignKey("outlets.id"), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Self-service signups (POST /api/auth/register) must verify their email
    # before they can log in - accounts created by a Super Admin or the seed
    # script are stamped verified immediately (see their respective call sites),
    # since those are already trusted/administrative creations, not open signup.
    email_verified_at: Mapped["datetime | None"] = mapped_column(DateTime(timezone=True), default=None)
    verification_token: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, default=None)
    verification_sent_at: Mapped["datetime | None"] = mapped_column(DateTime(timezone=True), default=None)

    outlet: Mapped["Outlet | None"] = relationship(back_populates="users")  # noqa: F821
