"""Sends SMS via whichever provider is enabled + set as default in Settings.

Same provider-based architecture as email.py - see that file's docstring.
"""

import httpx
from sqlalchemy.orm import Session

from app.models.integrations import SmsProviderConfig, SmsProviderType


class SmsNotConfigured(Exception):
    pass


def is_provider_configured(p: SmsProviderConfig) -> bool:
    if p.provider == SmsProviderType.MSG91:
        return bool(p.api_key and p.sender_id)
    if p.provider == SmsProviderType.TEXTLOCAL_INDIA:
        return bool(p.api_key and p.sender_id)
    if p.provider == SmsProviderType.TWO_FACTOR:
        return bool(p.api_key and p.sender_id)
    if p.provider == SmsProviderType.TWILIO:
        return bool(p.api_key and p.auth_token and p.sender_id)
    if p.provider == SmsProviderType.GENERIC_HTTP:
        return bool((p.extra_config or {}).get("webhook_url"))
    return False


def get_default_provider(db: Session) -> SmsProviderConfig | None:
    provider = (
        db.query(SmsProviderConfig)
        .filter(SmsProviderConfig.is_enabled.is_(True), SmsProviderConfig.is_default.is_(True))
        .first()
    )
    if provider and is_provider_configured(provider):
        return provider
    return None


def is_configured(db: Session) -> bool:
    return get_default_provider(db) is not None


def send_sms(db: Session, to_number: str, text: str) -> dict:
    provider = get_default_provider(db)
    if not provider:
        raise SmsNotConfigured("SMS is not configured - set up a provider in Settings first")
    return _dispatch(provider, to_number, text)


def send_test_sms(provider: SmsProviderConfig, to_number: str) -> dict:
    return _dispatch(provider, to_number, "This is a test SMS from Tanisi ERP. Your SMS integration is working.")


def _dispatch(p: SmsProviderConfig, to_number: str, text: str) -> dict:
    if p.provider == SmsProviderType.MSG91:
        return _send_via_msg91(p, to_number, text)
    if p.provider == SmsProviderType.TEXTLOCAL_INDIA:
        return _send_via_textlocal(p, to_number, text)
    if p.provider == SmsProviderType.TWO_FACTOR:
        return _send_via_2factor(p, to_number, text)
    if p.provider == SmsProviderType.TWILIO:
        return _send_via_twilio(p, to_number, text)
    if p.provider == SmsProviderType.GENERIC_HTTP:
        return _send_via_generic_http(p, to_number, text)
    raise SmsNotConfigured(f"Unsupported SMS provider: {p.provider}")


def _send_via_msg91(p: SmsProviderConfig, to_number: str, text: str) -> dict:
    response = httpx.get(
        "https://api.msg91.com/api/sendhttp.php",
        params={
            "authkey": p.api_key,
            "mobiles": to_number,
            "message": text,
            "sender": p.sender_id,
            "route": "4",
            "country": "91",
        },
        timeout=15,
    )
    response.raise_for_status()
    return {"status_code": response.status_code, "body": response.text}


def _send_via_textlocal(p: SmsProviderConfig, to_number: str, text: str) -> dict:
    response = httpx.post(
        "https://api.textlocal.in/send/",
        data={"apikey": p.api_key, "numbers": to_number, "message": text, "sender": p.sender_id},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def _send_via_2factor(p: SmsProviderConfig, to_number: str, text: str) -> dict:
    response = httpx.get(
        f"https://2factor.in/API/V1/{p.api_key}/ADDON_SERVICES/SEND/TSMS",
        params={"From": p.sender_id, "To": to_number, "Msg": text},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def _send_via_twilio(p: SmsProviderConfig, to_number: str, text: str) -> dict:
    url = f"https://api.twilio.com/2010-04-01/Accounts/{p.api_key}/Messages.json"
    response = httpx.post(
        url,
        data={"To": to_number, "From": p.sender_id, "Body": text},
        auth=(p.api_key, p.auth_token),
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def _send_via_generic_http(p: SmsProviderConfig, to_number: str, text: str) -> dict:
    extra = p.extra_config or {}
    webhook_url = extra.get("webhook_url")
    headers = {"Content-Type": "application/json"}
    if p.auth_token:
        headers["Authorization"] = p.auth_token
    response = httpx.post(webhook_url, json={"to": to_number, "message": text}, headers=headers, timeout=15)
    response.raise_for_status()
    try:
        return response.json()
    except ValueError:
        return {"status_code": response.status_code}
