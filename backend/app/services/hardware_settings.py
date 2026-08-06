from sqlalchemy.orm import Session

from app.models.hardware import HardwareAiSettings


def get_hardware_ai_settings(db: Session) -> HardwareAiSettings:
    settings = db.get(HardwareAiSettings, 1)
    if not settings:
        settings = HardwareAiSettings(id=1)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings
