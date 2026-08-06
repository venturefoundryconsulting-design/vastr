from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.models.hardware import HardwareAiSettings
from app.schemas.hardware import HardwareAiSettingsOut, HardwareAiSettingsUpdate
from app.services.hardware_settings import get_hardware_ai_settings

router = APIRouter(prefix="/api/settings/hardware-ai", tags=["settings"], dependencies=[Depends(require_admin)])


def _to_out(s: HardwareAiSettings) -> HardwareAiSettingsOut:
    return HardwareAiSettingsOut(
        barcode_min_length=s.barcode_min_length,
        barcode_beep_on_scan=s.barcode_beep_on_scan,
        thermal_printer_name=s.thermal_printer_name,
        thermal_printer_ip=s.thermal_printer_ip,
        biometric_enabled=s.biometric_enabled,
        biometric_device_api_url=s.biometric_device_api_url,
        biometric_api_key_set=bool(s.biometric_api_key),
        openai_api_key_set=bool(s.openai_api_key),
        openai_model=s.openai_model,
    )


@router.get("", response_model=HardwareAiSettingsOut)
def get_settings(db: Session = Depends(get_db)):
    return _to_out(get_hardware_ai_settings(db))


@router.patch("", response_model=HardwareAiSettingsOut)
def update_settings(payload: HardwareAiSettingsUpdate, db: Session = Depends(get_db)):
    s = get_hardware_ai_settings(db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None or value == "":
            continue
        setattr(s, field, value)
    db.commit()
    db.refresh(s)
    return _to_out(s)
