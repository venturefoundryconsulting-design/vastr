from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, get_db, require_manager_up
from app.models.inventory import MovementType
from app.models.purchase import PurchaseOrder, PurchaseOrderItem, PurchaseOrderStatus
from app.models.user import User
from app.models.vendor import Vendor
from app.models.whatsapp import WhatsAppMessage, WhatsAppMessageStatus
from app.schemas.purchase import (
    GoodsReceiptRequest,
    PurchaseOrderCreate,
    PurchaseOrderOut,
    ReorderSuggestion,
)
from app.schemas.whatsapp import WhatsAppSendResult
from app.services.app_settings import get_app_settings
from app.services.export import ExportFormat, build_export_response
from app.services.inventory import apply_stock_delta
from app.services.numbering import next_document_number
from app.services.pdf import render_purchase_order_pdf
from app.services.purchasing import build_reorder_suggestions
from app.services.whatsapp import (
    build_po_message_text,
    build_wa_me_link,
    is_cloud_api_configured,
    send_via_cloud_api,
)

router = APIRouter(
    prefix="/api/purchase-orders", tags=["purchase-orders"], dependencies=[Depends(require_manager_up)]
)


def _to_out(po: PurchaseOrder) -> PurchaseOrderOut:
    return PurchaseOrderOut(
        id=po.id,
        po_number=po.po_number,
        vendor_id=po.vendor_id,
        vendor_name=po.vendor.name,
        outlet_id=po.outlet_id,
        outlet_name=po.outlet.name,
        status=po.status,
        order_date=po.order_date,
        expected_date=po.expected_date,
        notes=po.notes,
        total_amount=po.total_amount,
        items=[
            {
                "id": i.id,
                "variant_id": i.variant_id,
                "quantity_ordered": i.quantity_ordered,
                "quantity_received": i.quantity_received,
                "unit_cost": float(i.unit_cost),
                "tax_rate": float(i.tax_rate),
                "amount": i.amount,
                "sku": i.variant.sku,
                "product_name": i.variant.display_name,
            }
            for i in po.items
        ],
    )


def _get_po_or_404(db: Session, po_id: int) -> PurchaseOrder:
    po = (
        db.query(PurchaseOrder)
        .options(
            joinedload(PurchaseOrder.items).joinedload(PurchaseOrderItem.variant),
            joinedload(PurchaseOrder.vendor),
            joinedload(PurchaseOrder.outlet),
        )
        .filter(PurchaseOrder.id == po_id)
        .first()
    )
    if not po:
        raise HTTPException(404, "Purchase order not found")
    return po


@router.get("", response_model=list[PurchaseOrderOut])
def list_purchase_orders(
    status: PurchaseOrderStatus | None = None,
    vendor_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(PurchaseOrder).options(
        joinedload(PurchaseOrder.items).joinedload(PurchaseOrderItem.variant),
        joinedload(PurchaseOrder.vendor),
        joinedload(PurchaseOrder.outlet),
    )
    if status:
        query = query.filter(PurchaseOrder.status == status)
    if vendor_id:
        query = query.filter(PurchaseOrder.vendor_id == vendor_id)
    pos = query.order_by(PurchaseOrder.created_at.desc()).limit(100).all()
    return [_to_out(po) for po in pos]


@router.get("/reorder-suggestions", response_model=list[ReorderSuggestion])
def reorder_suggestions(
    outlet_id: int | None = None,
    vendor_id: int | None = None,
    db: Session = Depends(get_db),
):
    return build_reorder_suggestions(db, outlet_id=outlet_id, vendor_id=vendor_id)


@router.get("/export")
def export_purchase_orders(
    status: PurchaseOrderStatus | None = None,
    vendor_id: int | None = None,
    format: ExportFormat = "xlsx",
    db: Session = Depends(get_db),
):
    query = db.query(PurchaseOrder).options(
        joinedload(PurchaseOrder.vendor), joinedload(PurchaseOrder.outlet)
    )
    if status:
        query = query.filter(PurchaseOrder.status == status)
    if vendor_id:
        query = query.filter(PurchaseOrder.vendor_id == vendor_id)
    pos = query.order_by(PurchaseOrder.created_at.desc()).all()
    rows = [
        {
            "po_number": po.po_number,
            "vendor": po.vendor.name if po.vendor else None,
            "outlet": po.outlet.name if po.outlet else None,
            "status": po.status,
            "order_date": po.order_date,
            "expected_date": po.expected_date,
            "total_amount": po.total_amount,
        }
        for po in pos
    ]
    columns = [
        ("po_number", "PO #"),
        ("vendor", "Vendor"),
        ("outlet", "Outlet"),
        ("status", "Status"),
        ("order_date", "Order Date"),
        ("expected_date", "Expected Date"),
        ("total_amount", "Total"),
    ]
    return build_export_response(rows, columns, "Purchase Orders", format)


@router.get("/{po_id}", response_model=PurchaseOrderOut)
def get_purchase_order(po_id: int, db: Session = Depends(get_db)):
    return _to_out(_get_po_or_404(db, po_id))


@router.post("", response_model=PurchaseOrderOut)
def create_purchase_order(
    payload: PurchaseOrderCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    if not db.get(Vendor, payload.vendor_id):
        raise HTTPException(404, "Vendor not found")
    po = PurchaseOrder(
        po_number=next_document_number(db, PurchaseOrder, PurchaseOrder.po_number, "PO"),
        vendor_id=payload.vendor_id,
        outlet_id=payload.outlet_id,
        order_date=datetime.now(timezone.utc),
        expected_date=payload.expected_date,
        notes=payload.notes,
        created_by_id=user.id,
        status=PurchaseOrderStatus.DRAFT,
    )
    for item in payload.items:
        po.items.append(PurchaseOrderItem(**item.model_dump()))
    db.add(po)
    db.commit()
    return _to_out(_get_po_or_404(db, po.id))


@router.get("/{po_id}/pdf")
def download_purchase_order_pdf(po_id: int, db: Session = Depends(get_db)):
    po = _get_po_or_404(db, po_id)
    pdf_bytes = render_purchase_order_pdf(po, get_app_settings(db))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{po.po_number}.pdf"'},
    )


@router.post("/{po_id}/send-whatsapp", response_model=WhatsAppSendResult)
def send_purchase_order_whatsapp(po_id: int, db: Session = Depends(get_db)):
    po = _get_po_or_404(db, po_id)
    if not po.vendor.whatsapp_number:
        raise HTTPException(400, "Vendor has no WhatsApp number on file")

    app_settings = get_app_settings(db)
    text = build_po_message_text(po)
    link = build_wa_me_link(po.vendor.whatsapp_number, text)

    message = WhatsAppMessage(
        vendor_id=po.vendor_id,
        purchase_order_id=po.id,
        phone_number=po.vendor.whatsapp_number,
        status=WhatsAppMessageStatus.LINK_GENERATED,
    )

    note = "Open the link to send the pre-filled message from WhatsApp."
    if is_cloud_api_configured(app_settings):
        try:
            result = send_via_cloud_api(app_settings, po.vendor.whatsapp_number, text)
            message.status = WhatsAppMessageStatus.SENT
            message.provider_message_id = result.get("messages", [{}])[0].get("id")
            message.sent_at = datetime.now(timezone.utc)
            note = "Sent automatically via WhatsApp Cloud API."
        except httpx.HTTPError as exc:
            message.status = WhatsAppMessageStatus.FAILED
            message.error = str(exc)
            note = "Automated send failed - use the wa.me link to send manually."

    db.add(message)
    if po.status == PurchaseOrderStatus.DRAFT:
        po.status = PurchaseOrderStatus.SENT
    db.commit()
    db.refresh(message)

    return WhatsAppSendResult(
        whatsapp_link=link,
        status=message.status,
        message_id=message.id,
        provider_message_id=message.provider_message_id,
        note=note,
    )


@router.post("/{po_id}/receive", response_model=PurchaseOrderOut)
def receive_goods(
    po_id: int,
    payload: GoodsReceiptRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    po = _get_po_or_404(db, po_id)
    items_by_id = {item.id: item for item in po.items}

    for receipt_item in payload.items:
        po_item = items_by_id.get(receipt_item.item_id)
        if not po_item:
            raise HTTPException(400, f"Item {receipt_item.item_id} not on this purchase order")
        if receipt_item.quantity_received <= 0:
            continue
        remaining = po_item.quantity_ordered - po_item.quantity_received
        if receipt_item.quantity_received > remaining:
            raise HTTPException(
                400, f"Cannot receive more than remaining ({remaining}) for {po_item.variant.sku}"
            )
        po_item.quantity_received += receipt_item.quantity_received
        apply_stock_delta(
            db,
            variant_id=po_item.variant_id,
            outlet_id=po.outlet_id,
            quantity_delta=receipt_item.quantity_received,
            movement_type=MovementType.PURCHASE_RECEIPT,
            reference_type="purchase_order",
            reference_id=po.id,
            created_by_id=user.id,
        )

    if all(i.quantity_received >= i.quantity_ordered for i in po.items):
        po.status = PurchaseOrderStatus.RECEIVED
    elif any(i.quantity_received > 0 for i in po.items):
        po.status = PurchaseOrderStatus.PARTIALLY_RECEIVED

    db.commit()
    return _to_out(_get_po_or_404(db, po_id))
