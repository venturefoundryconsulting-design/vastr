from sqlalchemy.orm import Session

from app.core.tenant_context import get_current_tenant_id
from app.models.hardware import HardwareAiSettings


def get_hardware_ai_settings(db: Session) -> HardwareAiSettings:
    tenant_id = get_current_tenant_id()
    settings = db.query(HardwareAiSettings).filter(HardwareAiSettings.tenant_id == tenant_id).first()
    if not settings:
        settings = HardwareAiSettings(tenant_id=tenant_id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings
