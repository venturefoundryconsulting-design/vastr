import enum

from sqlalchemy import Boolean, DateTime, Enum, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class EmailProviderType(str, enum.Enum):
    BREVO = "brevo"
    RESEND = "resend"
    EMAILJS = "emailjs"
    SMTP_GENERIC = "smtp_generic"
    GMAIL_SMTP = "gmail_smtp"
    OUTLOOK_SMTP = "outlook_smtp"


class SmsProviderType(str, enum.Enum):
    MSG91 = "msg91"
    TEXTLOCAL_INDIA = "textlocal_india"
    TWO_FACTOR = "two_factor"
    GENERIC_HTTP = "generic_http"
    TWILIO = "twilio"


class EmailProvider(Base, TimestampMixin):
    """One row per email provider type. Enabling + setting one as default makes it
    the active send path; the rest stay configured-but-idle so switching providers
    is instant and previous credentials aren't lost.
    """

    __tablename__ = "email_providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[EmailProviderType] = mapped_column(Enum(EmailProviderType), unique=True, index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    api_key: Mapped[str | None] = mapped_column(String(500), default=None)
    secret_key: Mapped[str | None] = mapped_column(String(500), default=None)
    sender_name: Mapped[str | None] = mapped_column(String(120), default=None)
    sender_email: Mapped[str | None] = mapped_column(String(255), default=None)

    # SMTP-family providers only (smtp_generic / gmail_smtp / outlook_smtp)
    smtp_host: Mapped[str | None] = mapped_column(String(255), default=None)
    smtp_port: Mapped[int | None] = mapped_column(Integer, default=None)
    smtp_username: Mapped[str | None] = mapped_column(String(255), default=None)
    smtp_password: Mapped[str | None] = mapped_column(String(500), default=None)
    smtp_use_tls: Mapped[bool] = mapped_column(Boolean, default=True)

    # Provider-specific extras that don't fit the common shape (e.g. EmailJS's
    # service_id/template_id) - keeps this table stable as new providers are added.
    extra_config: Mapped[dict] = mapped_column(JSONB, default=dict)

    last_test_status: Mapped[str | None] = mapped_column(String(20), default=None)
    last_test_at: Mapped["DateTime | None"] = mapped_column(DateTime(timezone=True), default=None)
    last_test_error: Mapped[str | None] = mapped_column(String(500), default=None)


class SmsProviderConfig(Base, TimestampMixin):
    """Same one-row-per-provider pattern as EmailProvider."""

    __tablename__ = "sms_provider_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[SmsProviderType] = mapped_column(Enum(SmsProviderType), unique=True, index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    api_key: Mapped[str | None] = mapped_column(String(500), default=None)
    auth_token: Mapped[str | None] = mapped_column(String(500), default=None)
    sender_id: Mapped[str | None] = mapped_column(String(40), default=None)

    extra_config: Mapped[dict] = mapped_column(JSONB, default=dict)

    last_test_status: Mapped[str | None] = mapped_column(String(20), default=None)
    last_test_at: Mapped["DateTime | None"] = mapped_column(DateTime(timezone=True), default=None)
    last_test_error: Mapped[str | None] = mapped_column(String(500), default=None)
