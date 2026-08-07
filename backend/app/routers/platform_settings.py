"""Super Admin-only platform configuration: Payment Gateway (Razorpay),
Email/SMTP, Website configuration, and Sub-domain policy - the "Global
Settings" surface of the Super Admin portal. Mirrors the tenant-facing
app.routers.integrations pattern (get-or-create singleton, masked secrets,
test-send endpoints) but scoped to the platform instead of a tenant.
"""

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_super_admin
from app.models.platform_settings import (
    PlatformDomainConfig,
    PlatformEmailConfig,
    PlatformPaymentConfig,
    PlatformWebsiteConfig,
)
from app.schemas.platform_settings import (
    PlatformDomainConfigOut,
    PlatformDomainConfigUpdate,
    PlatformEmailConfigOut,
    PlatformEmailConfigUpdate,
    PlatformPaymentConfigOut,
    PlatformPaymentConfigUpdate,
    PlatformWebsiteConfigOut,
    PlatformWebsiteConfigUpdate,
    TestPlatformEmailRequest,
    TestResult,
)
from app.services import platform_email
from app.services import razorpay as razorpay_service

router = APIRouter(prefix="/api/admin/settings", tags=["platform-settings"], dependencies=[Depends(require_super_admin)])


# ---- Email / SMTP ----


def _email_out(c: PlatformEmailConfig) -> PlatformEmailConfigOut:
    return PlatformEmailConfigOut(
        is_enabled=c.is_enabled,
        smtp_host=c.smtp_host,
        smtp_port=c.smtp_port,
        smtp_username=c.smtp_username,
        smtp_password_set=bool(c.smtp_password),
        smtp_use_tls=c.smtp_use_tls,
        sender_name=c.sender_name,
        sender_email=c.sender_email,
        is_configured=platform_email.is_configured(c),
        last_test_status=c.last_test_status,
        last_test_at=c.last_test_at,
        last_test_error=c.last_test_error,
    )


@router.get("/email", response_model=PlatformEmailConfigOut)
def get_email_config(db: Session = Depends(get_db)):
    return _email_out(platform_email.get_config(db))


@router.patch("/email", response_model=PlatformEmailConfigOut)
def update_email_config(payload: PlatformEmailConfigUpdate, db: Session = Depends(get_db)):
    row = platform_email.get_config(db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None or value == "":
            continue
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return _email_out(row)


@router.post("/email/test", response_model=TestResult)
def test_email_config(payload: TestPlatformEmailRequest, db: Session = Depends(get_db)):
    row = platform_email.get_config(db)
    if not platform_email.is_configured(row):
        raise HTTPException(400, "Fill in the required SMTP fields before testing")
    try:
        platform_email.send_test_email(row, payload.to_email)
    except Exception as exc:
        platform_email.record_test_result(db, row, ok=False, error=str(exc))
        raise HTTPException(502, f"Test email failed: {exc}") from exc
    platform_email.record_test_result(db, row, ok=True)
    return TestResult(ok=True, detail=f"Test email sent to {payload.to_email}")


# ---- Payment gateway (Razorpay) ----


def _payment_out(c: PlatformPaymentConfig) -> PlatformPaymentConfigOut:
    return PlatformPaymentConfigOut(
        is_enabled=c.is_enabled,
        is_live=c.is_live,
        razorpay_key_id=c.razorpay_key_id,
        razorpay_key_secret_set=bool(c.razorpay_key_secret),
        razorpay_webhook_secret_set=bool(c.razorpay_webhook_secret),
        is_configured=razorpay_service.is_configured(c),
        last_test_status=c.last_test_status,
        last_test_at=c.last_test_at,
        last_test_error=c.last_test_error,
    )


@router.get("/payment", response_model=PlatformPaymentConfigOut)
def get_payment_config(db: Session = Depends(get_db)):
    return _payment_out(razorpay_service.get_config(db))


@router.patch("/payment", response_model=PlatformPaymentConfigOut)
def update_payment_config(payload: PlatformPaymentConfigUpdate, db: Session = Depends(get_db)):
    row = razorpay_service.get_config(db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None or value == "":
            continue
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return _payment_out(row)


@router.post("/payment/test", response_model=TestResult)
def test_payment_config(db: Session = Depends(get_db)):
    """Creates a throwaway ₹1 order to confirm the Razorpay credentials work -
    nothing is ever charged unless someone completes that specific checkout,
    which this test never opens."""
    row = razorpay_service.get_config(db)
    if not razorpay_service.is_configured(row):
        raise HTTPException(400, "Fill in the Razorpay key ID and secret before testing")
    try:
        razorpay_service.create_order(row, amount_rupees=1, receipt="connection-test", notes={"test": "true"})
    except (razorpay_service.RazorpayError, httpx.HTTPError) as exc:
        row.last_test_status = "failed"
        row.last_test_at = datetime.now(timezone.utc)
        row.last_test_error = str(exc)[:500]
        db.commit()
        raise HTTPException(502, f"Razorpay connection test failed: {exc}") from exc
    row.last_test_status = "success"
    row.last_test_at = datetime.now(timezone.utc)
    row.last_test_error = None
    db.commit()
    return TestResult(ok=True, detail="Razorpay credentials are valid")


# ---- Website configuration ----


@router.get("/website", response_model=PlatformWebsiteConfigOut)
def get_website_config(db: Session = Depends(get_db)):
    row = db.query(PlatformWebsiteConfig).first()
    if not row:
        row = PlatformWebsiteConfig()
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@router.patch("/website", response_model=PlatformWebsiteConfigOut)
def update_website_config(payload: PlatformWebsiteConfigUpdate, db: Session = Depends(get_db)):
    row = db.query(PlatformWebsiteConfig).first()
    if not row:
        row = PlatformWebsiteConfig()
        db.add(row)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


# ---- Sub-domain configuration ----


@router.get("/domain", response_model=PlatformDomainConfigOut)
def get_domain_config(db: Session = Depends(get_db)):
    row = db.query(PlatformDomainConfig).first()
    if not row:
        row = PlatformDomainConfig()
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@router.patch("/domain", response_model=PlatformDomainConfigOut)
def update_domain_config(payload: PlatformDomainConfigUpdate, db: Session = Depends(get_db)):
    row = db.query(PlatformDomainConfig).first()
    if not row:
        row = PlatformDomainConfig()
        db.add(row)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row
