from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.models.integrations import EmailProvider, EmailProviderType, SmsProviderConfig, SmsProviderType
from app.schemas.integrations import (
    EmailProviderOut,
    EmailProviderUpdate,
    SmsProviderOut,
    SmsProviderUpdate,
    TestEmailRequest,
    TestResult,
    TestSmsRequest,
)
from app.services import email as email_service
from app.services import sms as sms_service

router = APIRouter(prefix="/api/integrations", tags=["integrations"], dependencies=[Depends(require_admin)])


def _get_or_create_email_provider(db: Session, provider: EmailProviderType) -> EmailProvider:
    row = db.query(EmailProvider).filter(EmailProvider.provider == provider).first()
    if not row:
        row = EmailProvider(provider=provider)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _get_or_create_sms_provider(db: Session, provider: SmsProviderType) -> SmsProviderConfig:
    row = db.query(SmsProviderConfig).filter(SmsProviderConfig.provider == provider).first()
    if not row:
        row = SmsProviderConfig(provider=provider)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _email_out(p: EmailProvider) -> EmailProviderOut:
    return EmailProviderOut(
        provider=p.provider,
        is_enabled=p.is_enabled,
        is_default=p.is_default,
        api_key_set=bool(p.api_key),
        secret_key_set=bool(p.secret_key),
        sender_name=p.sender_name,
        sender_email=p.sender_email,
        smtp_host=p.smtp_host,
        smtp_port=p.smtp_port,
        smtp_username=p.smtp_username,
        smtp_password_set=bool(p.smtp_password),
        smtp_use_tls=p.smtp_use_tls,
        extra_config=p.extra_config or {},
        is_configured=email_service.is_provider_configured(p),
        last_test_status=p.last_test_status,
        last_test_at=p.last_test_at,
        last_test_error=p.last_test_error,
    )


def _sms_out(p: SmsProviderConfig) -> SmsProviderOut:
    return SmsProviderOut(
        provider=p.provider,
        is_enabled=p.is_enabled,
        is_default=p.is_default,
        api_key_set=bool(p.api_key),
        auth_token_set=bool(p.auth_token),
        sender_id=p.sender_id,
        extra_config=p.extra_config or {},
        is_configured=sms_service.is_provider_configured(p),
        last_test_status=p.last_test_status,
        last_test_at=p.last_test_at,
        last_test_error=p.last_test_error,
    )


# ---- Email ----


@router.get("/email", response_model=list[EmailProviderOut])
def list_email_providers(db: Session = Depends(get_db)):
    return [_email_out(_get_or_create_email_provider(db, p)) for p in EmailProviderType]


@router.patch("/email/{provider}", response_model=EmailProviderOut)
def update_email_provider(provider: EmailProviderType, payload: EmailProviderUpdate, db: Session = Depends(get_db)):
    row = _get_or_create_email_provider(db, provider)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if value is None or value == "":
            continue
        setattr(row, field, value)
    if data.get("is_default"):
        db.query(EmailProvider).filter(EmailProvider.provider != provider).update({"is_default": False})
    db.commit()
    db.refresh(row)
    return _email_out(row)


@router.post("/email/{provider}/test", response_model=TestResult)
def test_email_provider(provider: EmailProviderType, payload: TestEmailRequest, db: Session = Depends(get_db)):
    row = _get_or_create_email_provider(db, provider)
    if not email_service.is_provider_configured(row):
        raise HTTPException(400, "Fill in this provider's required fields before testing")
    try:
        email_service.send_test_email(row, payload.to_email)
    except httpx.HTTPError as exc:
        row.last_test_status = "failed"
        row.last_test_error = str(exc)
        row.last_test_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(502, f"Test email failed: {exc}") from exc
    except Exception as exc:
        row.last_test_status = "failed"
        row.last_test_error = str(exc)
        row.last_test_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(502, f"Test email failed: {exc}") from exc

    row.last_test_status = "success"
    row.last_test_error = None
    row.last_test_at = datetime.now(timezone.utc)
    db.commit()
    return TestResult(ok=True, detail=f"Test email sent to {payload.to_email}")


# ---- SMS ----


@router.get("/sms", response_model=list[SmsProviderOut])
def list_sms_providers(db: Session = Depends(get_db)):
    return [_sms_out(_get_or_create_sms_provider(db, p)) for p in SmsProviderType]


@router.patch("/sms/{provider}", response_model=SmsProviderOut)
def update_sms_provider(provider: SmsProviderType, payload: SmsProviderUpdate, db: Session = Depends(get_db)):
    row = _get_or_create_sms_provider(db, provider)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if value is None or value == "":
            continue
        setattr(row, field, value)
    if data.get("is_default"):
        db.query(SmsProviderConfig).filter(SmsProviderConfig.provider != provider).update({"is_default": False})
    db.commit()
    db.refresh(row)
    return _sms_out(row)


@router.post("/sms/{provider}/test", response_model=TestResult)
def test_sms_provider(provider: SmsProviderType, payload: TestSmsRequest, db: Session = Depends(get_db)):
    row = _get_or_create_sms_provider(db, provider)
    if not sms_service.is_provider_configured(row):
        raise HTTPException(400, "Fill in this provider's required fields before testing")
    try:
        sms_service.send_test_sms(row, payload.to_number)
    except httpx.HTTPError as exc:
        row.last_test_status = "failed"
        row.last_test_error = str(exc)
        row.last_test_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(502, f"Test SMS failed: {exc}") from exc

    row.last_test_status = "success"
    row.last_test_error = None
    row.last_test_at = datetime.now(timezone.utc)
    db.commit()
    return TestResult(ok=True, detail=f"Test SMS sent to {payload.to_number}")
