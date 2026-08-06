"""Sends email via whichever provider is enabled + set as default in Settings.

Provider-based architecture: `app/models/integrations.py` holds one row per
provider type; only the enabled+default row is ever used to send. Adding a new
provider means adding an enum value, a config-completeness check, and a `_send_via_*`
function here - nothing else in the app needs to change.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx
from sqlalchemy.orm import Session

from app.models.integrations import EmailProvider, EmailProviderType

SMTP_PROVIDERS = {EmailProviderType.SMTP_GENERIC, EmailProviderType.GMAIL_SMTP, EmailProviderType.OUTLOOK_SMTP}


class EmailNotConfigured(Exception):
    pass


def is_provider_configured(p: EmailProvider) -> bool:
    if not (p.sender_email and p.sender_name):
        return False
    if p.provider == EmailProviderType.BREVO:
        return bool(p.api_key)
    if p.provider == EmailProviderType.RESEND:
        return bool(p.api_key)
    if p.provider == EmailProviderType.EMAILJS:
        service_id = (p.extra_config or {}).get("service_id")
        template_id = (p.extra_config or {}).get("template_id")
        return bool(p.api_key and p.secret_key and service_id and template_id)
    if p.provider in SMTP_PROVIDERS:
        return bool(p.smtp_host and p.smtp_port and p.smtp_username and p.smtp_password)
    return False


def get_default_provider(db: Session) -> EmailProvider | None:
    provider = (
        db.query(EmailProvider)
        .filter(EmailProvider.is_enabled.is_(True), EmailProvider.is_default.is_(True))
        .first()
    )
    if provider and is_provider_configured(provider):
        return provider
    return None


def is_configured(db: Session) -> bool:
    return get_default_provider(db) is not None


def send_email(db: Session, to_address: str, subject: str, body_text: str) -> None:
    provider = get_default_provider(db)
    if not provider:
        raise EmailNotConfigured("Email is not configured - set up a provider in Settings first")
    _dispatch(provider, to_address, subject, body_text)


def send_test_email(provider: EmailProvider, to_address: str) -> None:
    """Used by the Test Email button - sends through a specific (possibly
    not-yet-saved-as-default) provider row rather than the configured default."""
    _dispatch(
        provider,
        to_address,
        "Tanisi ERP - test email",
        f"This is a test email from Tanisi ERP, sent via {provider.provider.value}. "
        "If you received this, the connection is working.",
    )


def _dispatch(provider: EmailProvider, to_address: str, subject: str, body_text: str) -> None:
    if provider.provider == EmailProviderType.BREVO:
        _send_via_brevo(provider, to_address, subject, body_text)
    elif provider.provider == EmailProviderType.RESEND:
        _send_via_resend(provider, to_address, subject, body_text)
    elif provider.provider == EmailProviderType.EMAILJS:
        _send_via_emailjs(provider, to_address, subject, body_text)
    elif provider.provider in SMTP_PROVIDERS:
        _send_via_smtp(provider, to_address, subject, body_text)
    else:
        raise EmailNotConfigured(f"Unsupported email provider: {provider.provider}")


def _send_via_brevo(p: EmailProvider, to_address: str, subject: str, body_text: str) -> None:
    response = httpx.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"api-key": p.api_key or "", "Content-Type": "application/json"},
        json={
            "sender": {"name": p.sender_name, "email": p.sender_email},
            "to": [{"email": to_address}],
            "subject": subject,
            "textContent": body_text,
        },
        timeout=15,
    )
    response.raise_for_status()


def _send_via_resend(p: EmailProvider, to_address: str, subject: str, body_text: str) -> None:
    response = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {p.api_key}", "Content-Type": "application/json"},
        json={
            "from": f"{p.sender_name} <{p.sender_email}>",
            "to": [to_address],
            "subject": subject,
            "text": body_text,
        },
        timeout=15,
    )
    response.raise_for_status()


def _send_via_emailjs(p: EmailProvider, to_address: str, subject: str, body_text: str) -> None:
    extra = p.extra_config or {}
    response = httpx.post(
        "https://api.emailjs.com/api/v1.0/email/send",
        json={
            "service_id": extra.get("service_id"),
            "template_id": extra.get("template_id"),
            "user_id": p.api_key,
            "accessToken": p.secret_key,
            "template_params": {
                "to_email": to_address,
                "from_name": p.sender_name,
                "reply_to": p.sender_email,
                "subject": subject,
                "message": body_text,
            },
        },
        timeout=15,
    )
    response.raise_for_status()


def _send_via_smtp(p: EmailProvider, to_address: str, subject: str, body_text: str) -> None:
    message = MIMEMultipart()
    message["From"] = f"{p.sender_name} <{p.sender_email}>" if p.sender_name else p.sender_email
    message["To"] = to_address
    message["Subject"] = subject
    message.attach(MIMEText(body_text, "plain"))

    with smtplib.SMTP(p.smtp_host, p.smtp_port, timeout=15) as server:
        if p.smtp_use_tls:
            server.starttls()
        server.login(p.smtp_username, p.smtp_password)
        server.sendmail(p.sender_email, [to_address], message.as_string())
