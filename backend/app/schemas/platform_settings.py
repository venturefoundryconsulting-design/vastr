from datetime import datetime

from pydantic import BaseModel, EmailStr


class PlatformEmailConfigOut(BaseModel):
    is_enabled: bool
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_password_set: bool
    smtp_use_tls: bool
    sender_name: str | None = None
    sender_email: str | None = None
    is_configured: bool
    last_test_status: str | None = None
    last_test_at: datetime | None = None
    last_test_error: str | None = None


class PlatformEmailConfigUpdate(BaseModel):
    is_enabled: bool | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool | None = None
    sender_name: str | None = None
    sender_email: str | None = None


class TestPlatformEmailRequest(BaseModel):
    to_email: EmailStr


class PlatformPaymentConfigOut(BaseModel):
    is_enabled: bool
    is_live: bool
    razorpay_key_id: str | None = None
    razorpay_key_secret_set: bool
    razorpay_webhook_secret_set: bool
    is_configured: bool
    last_test_status: str | None = None
    last_test_at: datetime | None = None
    last_test_error: str | None = None


class PlatformPaymentConfigUpdate(BaseModel):
    is_enabled: bool | None = None
    is_live: bool | None = None
    razorpay_key_id: str | None = None
    razorpay_key_secret: str | None = None
    razorpay_webhook_secret: str | None = None


class PlatformWebsiteConfigOut(BaseModel):
    site_name: str
    support_email: str | None = None
    support_phone: str | None = None
    footer_text: str | None = None
    social_links: dict = {}


class PlatformWebsiteConfigUpdate(BaseModel):
    site_name: str | None = None
    support_email: str | None = None
    support_phone: str | None = None
    footer_text: str | None = None
    social_links: dict | None = None


class PlatformDomainConfigOut(BaseModel):
    base_domain: str
    reserved_slugs: list[str] = []


class PlatformDomainConfigUpdate(BaseModel):
    base_domain: str | None = None
    reserved_slugs: list[str] | None = None


class TestResult(BaseModel):
    ok: bool
    detail: str
