from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.campaign import Campaign, CampaignRecipient, SegmentType
from app.models.customer import Customer
from app.models.product import Product, ProductVariant
from app.models.sale import Sale, SaleItem
from app.models.settings import AppSettings
from app.models.whatsapp import WhatsAppMessageStatus
from app.schemas.campaign import SegmentParams
from app.services.whatsapp import (
    build_wa_me_link,
    is_cloud_api_configured,
    send_interactive_buttons_via_cloud_api,
    send_media_via_cloud_api,
    send_via_cloud_api,
)

DEFAULT_LOOKBACK_DAYS = 30

# Buttons Meta allows to send as real interactive quick-reply buttons outside an approved
# Message Template. url/phone/catalog CTAs need template approval (a real Meta constraint),
# so those degrade to a plain-text line appended to the message instead.
QUICK_REPLY_BUTTON_TYPE = "quick_reply"


def resolve_segment(db: Session, params: SegmentParams) -> list[Customer]:
    base = db.query(Customer).filter(
        Customer.is_active.is_(True),
        or_(Customer.whatsapp_number.isnot(None), Customer.phone.isnot(None)),
    )

    if params.segment_type == SegmentType.ALL:
        return base.order_by(Customer.name).all()

    if params.segment_type == SegmentType.VIP:
        return base.filter(Customer.is_vip.is_(True)).order_by(Customer.name).all()

    if params.segment_type == SegmentType.TAG:
        if not params.segment_tag:
            return []
        return base.filter(Customer.tags.any(params.segment_tag)).order_by(Customer.name).all()

    if params.segment_type == SegmentType.BIRTHDAY_MONTH:
        current_month = datetime.now(timezone.utc).month
        return (
            base.filter(Customer.birthday.isnot(None))
            .filter(func.extract("month", Customer.birthday) == current_month)
            .order_by(Customer.name)
            .all()
        )

    cutoff = datetime.now(timezone.utc) - timedelta(days=params.segment_days or DEFAULT_LOOKBACK_DAYS)

    if params.segment_type in (SegmentType.CATEGORY_PURCHASE, SegmentType.BRAND_PURCHASE):
        purchasers = (
            db.query(Sale.customer_id)
            .join(SaleItem, SaleItem.sale_id == Sale.id)
            .join(ProductVariant, ProductVariant.id == SaleItem.variant_id)
            .join(Product, Product.id == ProductVariant.product_id)
            .filter(Sale.customer_id.isnot(None), Sale.created_at >= cutoff)
        )
        if params.segment_type == SegmentType.CATEGORY_PURCHASE:
            purchasers = purchasers.filter(Product.category_id == params.segment_category_id)
        else:
            purchasers = purchasers.filter(Product.brand.ilike(params.segment_brand or ""))
        return base.filter(Customer.id.in_(purchasers.distinct())).order_by(Customer.name).all()

    if params.segment_type == SegmentType.INACTIVE:
        recent = (
            db.query(Sale.customer_id)
            .filter(Sale.customer_id.isnot(None), Sale.created_at >= cutoff)
            .distinct()
        )
        return base.filter(~Customer.id.in_(recent)).order_by(Customer.name).all()

    return []


PLACEHOLDER_CATALOG = {
    "customer_name": "Customer's name",
    "invoice_number": "Their most recent invoice number (blank if they have no purchases)",
    "loyalty_points": "Their current loyalty point balance",
    "offer_code": "This campaign's offer code (set when composing the campaign)",
    "product_name": "This campaign's featured product name (set when composing the campaign)",
    "store_name": "Your business name, from Settings > Business Profile",
}


def personalize(template: str, customer: Customer, campaign: Campaign, db: Session, store_name: str | None) -> str:
    last_sale = (
        db.query(Sale)
        .filter(Sale.customer_id == customer.id)
        .order_by(Sale.created_at.desc())
        .first()
    )
    values = {
        "customer_name": customer.name,
        "name": customer.name,  # backward-compatible alias for campaigns created before this change
        "invoice_number": last_sale.invoice_number if last_sale else "",
        "loyalty_points": str(customer.loyalty_points),
        "offer_code": campaign.offer_code or "",
        "product_name": campaign.product_name or "",
        "store_name": store_name or "our store",
    }
    text = template
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text


def _reply_buttons(campaign: Campaign) -> list[tuple[str, str]]:
    if not campaign.buttons:
        return []
    return [
        (f"btn_{i}", b["label"])
        for i, b in enumerate(campaign.buttons)
        if b.get("type") == QUICK_REPLY_BUTTON_TYPE
    ][:3]


def _append_cta_lines(text: str, campaign: Campaign) -> str:
    """Buttons Meta won't let us render as real buttons (url/phone/catalog, outside a Message
    Template) are appended as plain text lines instead, so the CTA is never silently dropped."""
    if not campaign.buttons:
        return text
    lines = [f"{b['label']}: {b['value']}" for b in campaign.buttons if b.get("type") != QUICK_REPLY_BUTTON_TYPE]
    return text + ("\n\n" + "\n".join(lines) if lines else "")


def send_campaign(
    db: Session, campaign: Campaign, customers: list[Customer], app_settings: AppSettings | None
) -> list[CampaignRecipient]:
    cloud_configured = is_cloud_api_configured(app_settings)
    store_name = app_settings.business_name if app_settings else None
    reply_buttons = _reply_buttons(campaign)
    media_header = (
        (campaign.media_type.value, campaign.media_url) if campaign.media_url and campaign.media_type else None
    )

    recipients = []
    for customer in customers:
        number = customer.whatsapp_number or customer.phone
        if not number:
            continue
        text = personalize(campaign.message_template, customer, campaign, db, store_name)
        text = _append_cta_lines(text, campaign)
        recipient = CampaignRecipient(
            campaign_id=campaign.id,
            customer_id=customer.id,
            phone_number=number,
            message_text=text,
        )
        if cloud_configured:
            try:
                if reply_buttons:
                    result = send_interactive_buttons_via_cloud_api(
                        app_settings, number, text, reply_buttons, media_header
                    )
                elif media_header:
                    result = send_media_via_cloud_api(app_settings, number, media_header[1], media_header[0], text)
                else:
                    result = send_via_cloud_api(app_settings, number, text)
                recipient.status = WhatsAppMessageStatus.SENT
                recipient.sent_at = datetime.now(timezone.utc)
                recipient.provider_message_id = (
                    result.get("messages", [{}])[0].get("id") if isinstance(result, dict) else None
                )
            except httpx.HTTPError as exc:
                recipient.status = WhatsAppMessageStatus.FAILED
                recipient.error = str(exc)
        else:
            recipient.status = WhatsAppMessageStatus.LINK_GENERATED
        db.add(recipient)
        recipients.append(recipient)
    return recipients
