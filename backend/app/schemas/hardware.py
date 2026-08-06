from pydantic import BaseModel


class HardwareAiSettingsOut(BaseModel):
    barcode_min_length: int | None = None
    barcode_beep_on_scan: bool = True

    thermal_printer_name: str | None = None
    thermal_printer_ip: str | None = None

    biometric_enabled: bool = False
    biometric_device_api_url: str | None = None
    biometric_api_key_set: bool = False

    openai_api_key_set: bool = False
    openai_model: str | None = None


class HardwareAiSettingsUpdate(BaseModel):
    """All fields optional. Secret fields are left unchanged when omitted or blank."""

    barcode_min_length: int | None = None
    barcode_beep_on_scan: bool | None = None

    thermal_printer_name: str | None = None
    thermal_printer_ip: str | None = None

    biometric_enabled: bool | None = None
    biometric_device_api_url: str | None = None
    biometric_api_key: str | None = None

    openai_api_key: str | None = None
    openai_model: str | None = None
