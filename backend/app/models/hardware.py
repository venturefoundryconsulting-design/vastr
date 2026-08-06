from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class HardwareAiSettings(Base, TimestampMixin):
    """Singleton row (id=1) holding config for hardware peripherals and AI features.

    This is config storage only - most of these fields aren't consumed by a feature
    yet (biometric attendance and the OpenAI-backed AI features don't exist in the
    app, see features.md). Barcode scanning already works today without any config
    here (scanners act as keyboard input into the existing scan fields); thermal
    printing already works via each outlet's paper-size setting plus the browser's
    own print dialog (browsers don't allow a webpage to pick a specific printer, for
    security reasons - that choice always belongs to the OS/browser print dialog).
    """

    __tablename__ = "hardware_ai_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)

    # Barcode scanner - scanners already work as keyboard input; these just tune it.
    barcode_min_length: Mapped[int | None] = mapped_column(Integer, default=None)
    barcode_beep_on_scan: Mapped[bool] = mapped_column(Boolean, default=True)

    # Thermal printer - connection metadata only; actual printing still goes through
    # the browser's print dialog (see PrintingSettings' paper-size config for the part
    # that actually affects output).
    thermal_printer_name: Mapped[str | None] = mapped_column(String(150), default=None)
    thermal_printer_ip: Mapped[str | None] = mapped_column(String(50), default=None)

    # Biometric attendance device - stored for when the Attendance module (see
    # features.md, not yet built) exists to consume it.
    biometric_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    biometric_device_api_url: Mapped[str | None] = mapped_column(String(300), default=None)
    biometric_api_key: Mapped[str | None] = mapped_column(String(500), default=None)

    # OpenAI - stored for when the AI features (see features.md, not yet built) exist
    # to consume it.
    openai_api_key: Mapped[str | None] = mapped_column(String(500), default=None)
    openai_model: Mapped[str | None] = mapped_column(String(60), default="gpt-4o-mini")
