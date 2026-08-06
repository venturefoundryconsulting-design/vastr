"""Sends purchase orders (to vendors) and sale receipts (to customers) over WhatsApp.

Two tiers, so the feature is useful on day one and can be automated later:

1. **wa.me deep link** (always available, zero setup): builds a
   `https://wa.me/<number>?text=...` link with the message pre-filled. Staff open
   it and tap Send in WhatsApp Web/Desktop/Mobile. No Meta approval needed.
2. **WhatsApp Cloud API** (optional): configured from the Settings page (or as a
   .env fallback) - if a token and phone number ID are set, the backend calls
   Meta's Graph API directly and the message is sent automatically, no manual
   tap required. Getting these credentials requires a Meta Business account with
   WhatsApp Business Platform access - see
   https://developers.facebook.com/docs/whatsapp/cloud-api/get-started
"""

import urllib.parse

import httpx

from app.core.config import settings as env_settings
from app.models.purchase import PurchaseOrder
from app.models.sale import Sale
from app.models.settings import AppSettings


def normalize_number(number: str) -> str:
    """Strips everything but digits, as required by both wa.me and the Cloud API."""
    return "".join(ch for ch in number if ch.isdigit())


def build_po_message_text(po: PurchaseOrder) -> str:
    lines = [
        f"*Purchase Order {po.po_number}*",
        f"From: {po.outlet.name}",
        f"Vendor: {po.vendor.name}",
        "",
        "Items:",
    ]
    for item in po.items:
        lines.append(f"- {item.variant.display_name} ({item.variant.sku}): {item.quantity_ordered} pcs @ {float(item.unit_cost):.2f}")
    lines.append("")
    lines.append(f"Total: {po.total_amount:.2f}")
    if po.expected_date:
        lines.append(f"Expected by: {po.expected_date.strftime('%d %b %Y')}")
    if po.notes:
        lines.append(f"Notes: {po.notes}")
    lines.append("")
    lines.append("Please confirm availability and dispatch date. Thank you!")
    return "\n".join(lines)


def build_sale_receipt_text(sale: Sale) -> str:
    lines = [
        f"*Receipt {sale.invoice_number}*",
        f"{sale.outlet.name}",
        "",
    ]
    for item in sale.items:
        lines.append(f"- {item.variant.display_name} x{item.quantity} @ {float(item.unit_price):.2f}")
    lines.append("")
    lines.append(f"Total: {sale.total:.2f} ({sale.payment_mode.value.upper()})")
    lines.append("")
    lines.append("Thank you for shopping with us!")
    return "\n".join(lines)


def build_wa_me_link(phone_number: str, text: str) -> str:
    number = normalize_number(phone_number)
    return f"https://wa.me/{number}?text={urllib.parse.quote(text)}"


def _resolve_cloud_api_credentials(app_settings: AppSettings | None) -> tuple[str, str, str] | None:
    """DB-configured settings take priority over .env fallback."""
    token = (app_settings.whatsapp_cloud_api_token if app_settings else None) or env_settings.WHATSAPP_CLOUD_API_TOKEN
    phone_id = (
        app_settings.whatsapp_phone_number_id if app_settings else None
    ) or env_settings.WHATSAPP_PHONE_NUMBER_ID
    api_version = (
        (app_settings.whatsapp_api_version if app_settings else None)
        or env_settings.WHATSAPP_API_VERSION
        or "v20.0"
    )
    if not token or not phone_id:
        return None
    return token, phone_id, api_version


def is_cloud_api_configured(app_settings: AppSettings | None) -> bool:
    return _resolve_cloud_api_credentials(app_settings) is not None


def send_via_cloud_api(app_settings: AppSettings | None, phone_number: str, text: str) -> dict:
    """Sends a plain text WhatsApp message via Meta's Cloud API.

    Raises httpx.HTTPStatusError on failure - caller decides how to record it.
    """
    credentials = _resolve_cloud_api_credentials(app_settings)
    if not credentials:
        raise RuntimeError("WhatsApp Cloud API is not configured")
    token, phone_id, api_version = credentials

    url = f"https://graph.facebook.com/{api_version}/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = {
        "messaging_product": "whatsapp",
        "to": normalize_number(phone_number),
        "type": "text",
        "text": {"body": text, "preview_url": False},
    }
    response = httpx.post(url, json=body, headers=headers, timeout=15)
    response.raise_for_status()
    return response.json()


def send_document_via_cloud_api(
    app_settings: AppSettings | None,
    phone_number: str,
    pdf_bytes: bytes,
    filename: str,
    caption: str,
) -> dict:
    """Uploads a PDF to Meta's Media API and sends it as a WhatsApp document message.

    Only the Cloud API tier can attach real files - the wa.me link tier has no way
    to carry an attachment, so this is the only path that satisfies "auto-generate
    PDF, attach, and send." Raises httpx.HTTPStatusError on failure.
    """
    credentials = _resolve_cloud_api_credentials(app_settings)
    if not credentials:
        raise RuntimeError("WhatsApp Cloud API is not configured")
    token, phone_id, api_version = credentials
    headers = {"Authorization": f"Bearer {token}"}

    upload_response = httpx.post(
        f"https://graph.facebook.com/{api_version}/{phone_id}/media",
        headers=headers,
        data={"messaging_product": "whatsapp", "type": "application/pdf"},
        files={"file": (filename, pdf_bytes, "application/pdf")},
        timeout=30,
    )
    upload_response.raise_for_status()
    media_id = upload_response.json()["id"]

    message_response = httpx.post(
        f"https://graph.facebook.com/{api_version}/{phone_id}/messages",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "messaging_product": "whatsapp",
            "to": normalize_number(phone_number),
            "type": "document",
            "document": {"id": media_id, "filename": filename, "caption": caption},
        },
        timeout=15,
    )
    message_response.raise_for_status()
    return message_response.json()


def send_media_via_cloud_api(
    app_settings: AppSettings | None,
    phone_number: str,
    media_url: str,
    media_type: str,
    caption: str,
) -> dict:
    """Sends an image/video/document WhatsApp message by public URL (Meta fetches it directly -
    no upload round-trip needed, unlike send_document_via_cloud_api which is used for
    just-generated PDFs that only exist in memory). media_type is "image", "video", or "document".
    Raises httpx.HTTPStatusError on failure.
    """
    credentials = _resolve_cloud_api_credentials(app_settings)
    if not credentials:
        raise RuntimeError("WhatsApp Cloud API is not configured")
    token, phone_id, api_version = credentials

    media_field = {"link": media_url}
    if media_type in ("image", "document"):
        media_field["caption"] = caption
    if media_type == "document":
        media_field["filename"] = media_url.rsplit("/", 1)[-1]

    response = httpx.post(
        f"https://graph.facebook.com/{api_version}/{phone_id}/messages",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "messaging_product": "whatsapp",
            "to": normalize_number(phone_number),
            "type": media_type,
            media_type: media_field,
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def send_interactive_buttons_via_cloud_api(
    app_settings: AppSettings | None,
    phone_number: str,
    body_text: str,
    reply_buttons: list[tuple[str, str]],
    media_header: tuple[str, str] | None = None,
) -> dict:
    """Sends a free-form WhatsApp "interactive" message with up to 3 quick-reply buttons.

    This is the only button type Meta allows outside an approved Message Template -
    URL/call/catalog buttons require Meta template approval, a real external constraint
    (same one noted for the WhatsApp Marketing feature generally). Callers that want a
    URL/call/catalog CTA fall back to appending the link/number as plain text instead.
    reply_buttons is a list of (id, title) pairs, title capped at 20 chars by WhatsApp.
    media_header, if given, is (media_type, media_url) for "image"/"video"/"document" -
    interactive messages can carry a media header alongside the buttons.
    Raises httpx.HTTPStatusError on failure.
    """
    credentials = _resolve_cloud_api_credentials(app_settings)
    if not credentials:
        raise RuntimeError("WhatsApp Cloud API is not configured")
    token, phone_id, api_version = credentials

    interactive: dict = {
        "type": "button",
        "body": {"text": body_text},
        "action": {
            "buttons": [
                {"type": "reply", "reply": {"id": bid, "title": title[:20]}} for bid, title in reply_buttons[:3]
            ]
        },
    }
    if media_header:
        header_type, header_url = media_header
        interactive["header"] = {"type": header_type, header_type: {"link": header_url}}

    response = httpx.post(
        f"https://graph.facebook.com/{api_version}/{phone_id}/messages",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "messaging_product": "whatsapp",
            "to": normalize_number(phone_number),
            "type": "interactive",
            "interactive": interactive,
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()
