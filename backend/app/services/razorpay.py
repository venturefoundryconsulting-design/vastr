"""Real Razorpay integration via direct REST calls (Basic Auth with
key_id:key_secret) - no razorpay SDK dependency needed for the two calls this
app makes: create an Order, and verify a completed payment's signature.

https://razorpay.com/docs/api/orders/ and
https://razorpay.com/docs/payments/server-integration/python/build-integration/#3-verify-payment-signature
"""

import hashlib
import hmac

import httpx
from sqlalchemy.orm import Session

from app.models.platform_settings import PlatformPaymentConfig

_API_BASE = "https://api.razorpay.com/v1"


class RazorpayNotConfigured(Exception):
    pass


class RazorpayError(Exception):
    pass


def get_config(db: Session) -> PlatformPaymentConfig:
    config = db.query(PlatformPaymentConfig).first()
    if not config:
        config = PlatformPaymentConfig()
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def is_configured(config: PlatformPaymentConfig) -> bool:
    return bool(config.is_enabled and config.razorpay_key_id and config.razorpay_key_secret)


def create_order(config: PlatformPaymentConfig, *, amount_rupees: float, receipt: str, notes: dict) -> dict:
    """Amount is in rupees on our side; Razorpay's Orders API wants paise."""
    if not is_configured(config):
        raise RazorpayNotConfigured("Razorpay isn't configured yet")
    response = httpx.post(
        f"{_API_BASE}/orders",
        auth=(config.razorpay_key_id, config.razorpay_key_secret),
        json={
            "amount": int(round(amount_rupees * 100)),
            "currency": "INR",
            "receipt": receipt,
            "notes": notes,
        },
        timeout=15,
    )
    if response.status_code >= 400:
        raise RazorpayError(f"Razorpay order creation failed: {response.text}")
    return response.json()


def verify_payment_signature(
    config: PlatformPaymentConfig, *, order_id: str, payment_id: str, signature: str
) -> bool:
    """HMAC-SHA256 of 'order_id|payment_id', keyed with key_secret, must
    equal the signature Razorpay Checkout returns to the browser on success."""
    if not config.razorpay_key_secret:
        return False
    payload = f"{order_id}|{payment_id}".encode()
    expected = hmac.new(config.razorpay_key_secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
