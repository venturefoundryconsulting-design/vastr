import enum

from sqlalchemy import Boolean, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    OUTLET_STAFF = "outlet_staff"


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

    outlet: Mapped["Outlet | None"] = relationship(back_populates="users")  # noqa: F821
