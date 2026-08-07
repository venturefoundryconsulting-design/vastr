"""Sends system emails (signup verification, password reset) via the
platform's own SMTP config - separate from app.services.email, which sends
on a *tenant's* behalf to that tenant's own customers.

SMTP-only (not the multi-provider catalog tenant Email Integrations offers):
the Super Admin operator supplies one SMTP account for the whole platform.
"""

import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy.orm import Session

from app.models.platform_settings import PlatformEmailConfig


class PlatformEmailNotConfigured(Exception):
    pass


def get_config(db: Session) -> PlatformEmailConfig:
    """Get-or-create the singleton row, mirroring app.services.app_settings."""
    config = db.query(PlatformEmailConfig).first()
    if not config:
        config = PlatformEmailConfig()
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def is_configured(config: PlatformEmailConfig) -> bool:
    return bool(
        config.is_enabled
        and config.smtp_host
        and config.smtp_port
        and config.smtp_username
        and config.smtp_password
        and config.sender_email
    )


def send_email(db: Session, to_address: str, subject: str, body_text: str) -> None:
    config = get_config(db)
    if not is_configured(config):
        raise PlatformEmailNotConfigured(
            "Platform SMTP isn't configured yet - set it up under Global Settings > Email"
        )
    _send_via_smtp(config, to_address, subject, body_text)


def send_test_email(config: PlatformEmailConfig, to_address: str) -> None:
    _send_via_smtp(
        config,
        to_address,
        "Vastr - test email",
        "This is a test email from Vastr's platform SMTP configuration. "
        "If you received this, the connection is working.",
    )


def _send_via_smtp(config: PlatformEmailConfig, to_address: str, subject: str, body_text: str) -> None:
    message = MIMEMultipart()
    message["From"] = f"{config.sender_name} <{config.sender_email}>" if config.sender_name else config.sender_email
    message["To"] = to_address
    message["Subject"] = subject
    message.attach(MIMEText(body_text, "plain"))

    # Port 465 is implicit TLS (SMTPS) - the connection must be encrypted
    # from the very first byte. Port 587/25 use STARTTLS - plaintext first,
    # then upgraded mid-handshake. Connecting to 465 with plain SMTP.starttls()
    # (as this used to do unconditionally) hangs until timeout, since the
    # server is waiting for a TLS ClientHello it never receives over what it
    # thinks is a plaintext channel.
    if config.smtp_port == 465:
        with smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=15) as server:
            server.login(config.smtp_username, config.smtp_password)
            server.sendmail(config.sender_email, [to_address], message.as_string())
    else:
        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=15) as server:
            if config.smtp_use_tls:
                server.starttls()
            server.login(config.smtp_username, config.smtp_password)
            server.sendmail(config.sender_email, [to_address], message.as_string())


def record_test_result(db: Session, config: PlatformEmailConfig, *, ok: bool, error: str | None = None) -> None:
    config.last_test_status = "success" if ok else "failed"
    config.last_test_at = datetime.now(timezone.utc)
    config.last_test_error = None if ok else (error or "Unknown error")[:500]
    db.commit()
