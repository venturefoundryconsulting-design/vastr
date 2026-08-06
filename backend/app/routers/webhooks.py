"""Receives Meta's WhatsApp Cloud API webhook callbacks.

Register this URL (PUBLIC_BASE_URL + /api/webhooks/whatsapp) in the Meta App
Dashboard's WhatsApp > Configuration > Webhook settings, subscribed to the
"messages" field, so delivery/read status updates flow back into campaign
reports. Only reachable in production once the backend has a public URL -
Meta can't call localhost.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.campaign import CampaignRecipient
from app.models.whatsapp import WhatsAppMessageStatus

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

_STATUS_MAP = {
    "sent": WhatsAppMessageStatus.SENT,
    "delivered": WhatsAppMessageStatus.DELIVERED,
    "read": WhatsAppMessageStatus.READ,
    "failed": WhatsAppMessageStatus.FAILED,
}


@router.get("/whatsapp")
def verify_whatsapp_webhook(
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_verify_token: str = Query(alias="hub.verify_token", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN:
        return PlainTextResponse(hub_challenge)
    raise HTTPException(403, "Verification token mismatch")


@router.post("/whatsapp")
async def receive_whatsapp_webhook(request: Request):
    payload = await request.json()
    db: Session = SessionLocal()
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                for status_update in change.get("value", {}).get("statuses", []):
                    _apply_status_update(db, status_update)
        db.commit()
    finally:
        db.close()
    return {"ok": True}


def _apply_status_update(db: Session, status_update: dict) -> None:
    new_status = _STATUS_MAP.get(status_update.get("status"))
    provider_message_id = status_update.get("id")
    if not new_status or not provider_message_id:
        return

    recipient = (
        db.query(CampaignRecipient)
        .filter(CampaignRecipient.provider_message_id == provider_message_id)
        .first()
    )
    if not recipient:
        return

    # Statuses arrive in order but webhooks can retry/replay - never regress a later status.
    order = [WhatsAppMessageStatus.SENT, WhatsAppMessageStatus.DELIVERED, WhatsAppMessageStatus.READ]
    if new_status in order and recipient.status in order and order.index(new_status) <= order.index(recipient.status):
        return

    recipient.status = new_status
    timestamp = status_update.get("timestamp")
    when = datetime.fromtimestamp(int(timestamp), tz=timezone.utc) if timestamp else datetime.now(timezone.utc)
    if new_status == WhatsAppMessageStatus.DELIVERED:
        recipient.delivered_at = when
    elif new_status == WhatsAppMessageStatus.READ:
        recipient.read_at = when
    elif new_status == WhatsAppMessageStatus.FAILED:
        errors = status_update.get("errors") or []
        recipient.error = errors[0].get("title") if errors else "Delivery failed"
