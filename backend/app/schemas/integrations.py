from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.models.integrations import EmailProviderType, SmsProviderType


class EmailProviderOut(BaseModel):
    provider: EmailProviderType
    is_enabled: bool
    is_default: bool
    api_key_set: bool
    secret_key_set: bool
    sender_name: str | None = None
    sender_email: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_password_set: bool
    smtp_use_tls: bool
    extra_config: dict = {}
    is_configured: bool
    last_test_status: str | None = None
    last_test_at: datetime | None = None
    last_test_error: str | None = None


class EmailProviderUpdate(BaseModel):
    is_enabled: bool | None = None
    is_default: bool | None = None
    api_key: str | None = None
    secret_key: str | None = None
    sender_name: str | None = None
    sender_email: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool | None = None
    extra_config: dict | None = None


class TestEmailRequest(BaseModel):
    to_email: EmailStr


class SmsProviderOut(BaseModel):
    provider: SmsProviderType
    is_enabled: bool
    is_default: bool
    api_key_set: bool
    auth_token_set: bool
    sender_id: str | None = None
    extra_config: dict = {}
    is_configured: bool
    last_test_status: str | None = None
    last_test_at: datetime | None = None
    last_test_error: str | None = None


class SmsProviderUpdate(BaseModel):
    is_enabled: bool | None = None
    is_default: bool | None = None
    api_key: str | None = None
    auth_token: str | None = None
    sender_id: str | None = None
    extra_config: dict | None = None


class TestSmsRequest(BaseModel):
    to_number: str


class TestResult(BaseModel):
    ok: bool
    detail: str
