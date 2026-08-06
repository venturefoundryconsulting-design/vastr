from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class AppSettings(Base, TimestampMixin):
    """Singleton row (id=1) holding admin-configurable integration settings.

    Editable from the Settings page instead of .env, so the admin can turn on
    WhatsApp receipt delivery without a redeploy. SMS and Email are configured
    per-provider in their own tables (app.models.integrations) instead of here.
    Secret fields are never returned to the client - only an `_is_set` flag - and
    are left unchanged on update when the incoming value is None.
    """

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)

    # Business profile - printed on every PO / receipt / transfer document
    business_name: Mapped[str | None] = mapped_column(String(200), default=None)
    business_address: Mapped[str | None] = mapped_column(String(500), default=None)
    business_gstin: Mapped[str | None] = mapped_column(String(20), default=None)
    business_phone: Mapped[str | None] = mapped_column(String(20), default=None)
    business_email: Mapped[str | None] = mapped_column(String(255), default=None)
    invoice_footer_text: Mapped[str | None] = mapped_column(String(500), default=None)
    show_hsn_on_documents: Mapped[bool] = mapped_column(Boolean, default=False)
    logo_url: Mapped[str | None] = mapped_column(String(500), default=None)

    # WhatsApp Cloud API (falls back to .env values in core.config if unset here)
    whatsapp_cloud_api_token: Mapped[str | None] = mapped_column(String(500), default=None)
    whatsapp_phone_number_id: Mapped[str | None] = mapped_column(String(50), default=None)
    whatsapp_api_version: Mapped[str | None] = mapped_column(String(10), default=None)
