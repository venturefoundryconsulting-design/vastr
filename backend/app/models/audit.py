from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class AuditLog(Base, TimestampMixin):
    """Append-only activity trail. tenant_id is declared directly (not via
    TenantMixin) and nullable: Super Admin actions on the platform itself
    (creating a tenant, suspending one) aren't scoped to "the current
    tenant" the way an ordinary request is - log_activity() always passes
    tenant_id explicitly rather than relying on auto-stamp.

    Coverage is best-effort, wired into the highest-value mutation endpoints
    first (auth, settings, users, tenant admin actions) - not a claim that
    every field-level change everywhere is captured.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), index=True, default=None)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, default=None)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(60), default=None)
    entity_id: Mapped[int | None] = mapped_column(Integer, default=None)
    details: Mapped[dict | None] = mapped_column(JSONB, default=None)
