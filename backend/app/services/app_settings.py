from sqlalchemy.orm import Session

from app.core.tenant_context import get_current_tenant_id
from app.models.settings import AppSettings
from app.models.tenant import Tenant


def _resolve_tenant_id(db: Session) -> int:
    tenant_id = get_current_tenant_id()
    if tenant_id is not None:
        return tenant_id
    # Unauthenticated call site (the public branding endpoint, hit by the login
    # page before a token exists) - there's no per-tenant domain/slug routing
    # yet, so fall back to the single active tenant. Revisit once tenants are
    # distinguished by subdomain/path before login.
    tenant = db.query(Tenant).filter(Tenant.is_active.is_(True)).order_by(Tenant.id).first()
    if not tenant:
        raise RuntimeError("No active tenant found")
    return tenant.id


def get_app_settings(db: Session) -> AppSettings:
    tenant_id = _resolve_tenant_id(db)
    settings = db.query(AppSettings).filter(AppSettings.tenant_id == tenant_id).first()
    if not settings:
        settings = AppSettings(tenant_id=tenant_id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings
