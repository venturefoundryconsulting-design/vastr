from datetime import date, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, get_db
from app.models.customer import BalanceType, Customer
from app.models.discount import DiscountRule
from app.models.inventory import MovementType, StockLevel
from app.models.product import Product, ProductVariant
from app.models.sale import PaymentMode, Sale, SaleItem
from app.models.user import User
from app.schemas.discount import DiscountCartItem
from app.schemas.sale import BarcodeLookupResult, ReceiptSendResult, SaleCreate, SaleOut
from app.services import email as email_service
from app.services import sms as sms_service
from app.services.app_settings import get_app_settings
from app.services.customer import adjust_credit_balance, adjust_loyalty_points
from app.services.discounts import apply_coupon, find_best_automatic_discount
from app.services.export import ExportFormat, build_export_response
from app.services.inventory import apply_stock_delta, get_or_create_stock_level
from app.services.numbering import next_document_number
from app.services.pdf import render_sale_receipt_pdf
from app.services.whatsapp import (
    build_sale_receipt_text,
    build_wa_me_link,
    is_cloud_api_configured,
    send_document_via_cloud_api,
    send_via_cloud_api,
)

router = APIRouter(prefix="/api/sales", tags=["sales"])


def _to_out(sale: Sale) -> SaleOut:
    return SaleOut(
        id=sale.id,
        invoice_number=sale.invoice_number,
        outlet_id=sale.outlet_id,
        outlet_name=sale.outlet.name,
        customer_id=sale.customer_id,
        customer_name=sale.customer_name,
        customer_phone=sale.customer_phone,
        customer_email=sale.customer_email,
        discount_amount=float(sale.discount_amount),
        coupon_code=sale.coupon_code,
        rule_discount_amount=float(sale.rule_discount_amount),
        discount_rule_name=sale.discount_rule.name if sale.discount_rule else None,
        credit_applied=float(sale.credit_applied),
        points_redeemed=sale.points_redeemed,
        loyalty_points_earned=sale.loyalty_points_earned,
        payment_mode=sale.payment_mode,
        subtotal=sale.subtotal,
        tax_amount=sale.tax_amount,
        total=sale.total,
        created_at=sale.created_at,
        items=[
            {
                "id": i.id,
                "variant_id": i.variant_id,
                "quantity": i.quantity,
                "unit_price": float(i.unit_price),
                "tax_rate": float(i.tax_rate),
                "sku": i.variant.sku,
                "product_name": i.variant.display_name,
            }
            for i in sale.items
        ],
    )


def _get_or_404(db: Session, sale_id: int) -> Sale:
    sale = (
        db.query(Sale)
        .options(
            joinedload(Sale.items).joinedload(SaleItem.variant),
            joinedload(Sale.outlet),
            joinedload(Sale.discount_rule),
        )
        .filter(Sale.id == sale_id)
        .first()
    )
    if not sale:
        raise HTTPException(404, "Sale not found")
    return sale


@router.get("/barcode/{code}", response_model=BarcodeLookupResult)
def lookup_barcode(
    code: str, outlet_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)
):
    variant = (
        db.query(ProductVariant)
        .filter((ProductVariant.barcode == code) | (ProductVariant.sku == code))
        .first()
    )
    if not variant or not variant.is_active:
        raise HTTPException(404, "No product found for this code")
    stock = (
        db.query(StockLevel)
        .filter(StockLevel.variant_id == variant.id, StockLevel.outlet_id == outlet_id)
        .first()
    )
    return BarcodeLookupResult(
        variant_id=variant.id,
        sku=variant.sku,
        barcode=variant.barcode,
        product_name=variant.display_name,
        size=variant.size,
        color=variant.color,
        selling_price=float(variant.selling_price),
        tax_rate=float(variant.product.tax_rate),
        available_quantity=stock.quantity if stock else 0,
    )


@router.get("/search-products", response_model=list[BarcodeLookupResult])
def search_products_for_pos(
    q: str, outlet_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)
):
    """Name/SKU search for the POS "search by name" field - complements barcode/SKU
    scanning for staff who don't have the barcode handy. Returns variant-level rows
    (one per size/color) with this outlet's stock, same shape as the barcode lookup."""
    if not q.strip():
        return []
    variants = (
        db.query(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(
            ProductVariant.is_active.is_(True),
            (Product.name.ilike(f"%{q}%")) | (ProductVariant.sku.ilike(f"%{q}%")),
        )
        .order_by(Product.name)
        .limit(20)
        .all()
    )
    stock_by_variant = {
        s.variant_id: s.quantity
        for s in db.query(StockLevel).filter(
            StockLevel.outlet_id == outlet_id, StockLevel.variant_id.in_([v.id for v in variants])
        )
    }
    return [
        BarcodeLookupResult(
            variant_id=v.id,
            sku=v.sku,
            barcode=v.barcode,
            product_name=v.display_name,
            size=v.size,
            color=v.color,
            selling_price=float(v.selling_price),
            tax_rate=float(v.product.tax_rate),
            available_quantity=stock_by_variant.get(v.id, 0),
        )
        for v in variants
    ]


def _filtered_sales_query(
    db: Session,
    outlet_id: int | None,
    search: str | None,
    start_date: date | None,
    end_date: date | None,
    payment_mode: PaymentMode | None,
):
    query = db.query(Sale).options(
        joinedload(Sale.items).joinedload(SaleItem.variant),
        joinedload(Sale.outlet),
        joinedload(Sale.discount_rule),
    )
    if outlet_id:
        query = query.filter(Sale.outlet_id == outlet_id)
    if search:
        like = f"%{search}%"
        query = query.filter(
            (Sale.invoice_number.ilike(like))
            | (Sale.customer_phone.ilike(like))
            | (Sale.customer_name.ilike(like))
        )
    if start_date:
        query = query.filter(Sale.created_at >= start_date)
    if end_date:
        query = query.filter(Sale.created_at < end_date + timedelta(days=1))
    if payment_mode:
        query = query.filter(Sale.payment_mode == payment_mode)
    return query.order_by(Sale.created_at.desc())


@router.get("", response_model=list[SaleOut])
def list_sales(
    outlet_id: int | None = None,
    search: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    payment_mode: PaymentMode | None = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    sales = _filtered_sales_query(db, outlet_id, search, start_date, end_date, payment_mode).limit(500).all()
    return [_to_out(s) for s in sales]


@router.get("/export")
def export_sales(
    outlet_id: int | None = None,
    search: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    payment_mode: PaymentMode | None = None,
    format: ExportFormat = "xlsx",
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    sales = _filtered_sales_query(db, outlet_id, search, start_date, end_date, payment_mode).limit(2000).all()
    rows = [
        {
            "invoice_number": s.invoice_number,
            "date": s.created_at,
            "outlet": s.outlet.name if s.outlet else None,
            "customer": s.customer_name or "Walk-in",
            "items": sum(i.quantity for i in s.items),
            "payment_mode": s.payment_mode,
            "subtotal": s.subtotal,
            "tax": s.tax_amount,
            "discount": float(s.discount_amount) + float(s.rule_discount_amount),
            "total": s.total,
        }
        for s in sales
    ]
    columns = [
        ("invoice_number", "Invoice #"),
        ("date", "Date"),
        ("outlet", "Outlet"),
        ("customer", "Customer"),
        ("items", "Items"),
        ("payment_mode", "Payment Mode"),
        ("subtotal", "Subtotal"),
        ("tax", "Tax"),
        ("discount", "Discount"),
        ("total", "Total"),
    ]
    return build_export_response(rows, columns, "Sales", format)


@router.get("/{sale_id}", response_model=SaleOut)
def get_sale(sale_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return _to_out(_get_or_404(db, sale_id))


@router.post("", response_model=SaleOut)
def checkout(payload: SaleCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not payload.items:
        raise HTTPException(400, "Cannot checkout an empty cart")

    for item in payload.items:
        stock = get_or_create_stock_level(db, item.variant_id, payload.outlet_id)
        if stock.quantity < item.quantity:
            variant = db.get(ProductVariant, item.variant_id)
            raise HTTPException(
                400, f"Insufficient stock for {variant.sku if variant else item.variant_id}: "
                f"have {stock.quantity}, need {item.quantity}"
            )

    customer = None
    if payload.redeem_credit_amount > 0 or payload.redeem_points > 0:
        if not payload.customer_id:
            raise HTTPException(400, "A customer must be selected to redeem credit or points")
        customer = db.get(Customer, payload.customer_id)
        if not customer:
            raise HTTPException(404, "Customer not found")
        if payload.redeem_credit_amount > float(customer.credit_balance):
            raise HTTPException(
                400,
                f"Customer only has ₹{float(customer.credit_balance):.2f} of store credit available",
            )
        if payload.redeem_points > customer.loyalty_points:
            raise HTTPException(
                400,
                f"Customer only has {customer.loyalty_points} loyalty points available",
            )
    elif payload.customer_id:
        customer = db.get(Customer, payload.customer_id)

    cart_items = [
        DiscountCartItem(variant_id=i.variant_id, quantity=i.quantity, unit_price=i.unit_price)
        for i in payload.items
    ]
    discount_rule: DiscountRule | None = None
    rule_discount_amount = 0.0
    if payload.coupon_code:
        result = apply_coupon(db, payload.coupon_code, cart_items, customer)
        if not result.applied:
            raise HTTPException(400, result.message)
        discount_rule = db.get(DiscountRule, result.rule_id)
        rule_discount_amount = result.discount_amount
    else:
        result = find_best_automatic_discount(db, cart_items, customer)
        if result.applied:
            discount_rule = db.get(DiscountRule, result.rule_id)
            rule_discount_amount = result.discount_amount

    sale = Sale(
        invoice_number=next_document_number(db, Sale, Sale.invoice_number, "INV"),
        outlet_id=payload.outlet_id,
        cashier_id=user.id,
        customer_id=payload.customer_id,
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        customer_email=payload.customer_email,
        discount_amount=payload.discount_amount,
        coupon_code=discount_rule.code if payload.coupon_code and discount_rule else None,
        discount_rule_id=discount_rule.id if discount_rule else None,
        rule_discount_amount=rule_discount_amount,
        credit_applied=payload.redeem_credit_amount,
        points_redeemed=payload.redeem_points,
        payment_mode=payload.payment_mode,
    )
    for item in payload.items:
        sale.items.append(SaleItem(**item.model_dump()))
    db.add(sale)
    db.flush()

    if sale.total < 0:
        raise HTTPException(400, "Redeemed credit and points cannot exceed the sale total")

    for item in payload.items:
        apply_stock_delta(
            db,
            variant_id=item.variant_id,
            outlet_id=payload.outlet_id,
            quantity_delta=-item.quantity,
            movement_type=MovementType.SALE,
            reference_type="sale",
            reference_id=sale.id,
            created_by_id=user.id,
        )

    if payload.redeem_credit_amount > 0:
        adjust_credit_balance(
            db,
            customer_id=payload.customer_id,
            amount_delta=-payload.redeem_credit_amount,
            balance_type=BalanceType.CREDIT,
            reference_type="sale",
            reference_id=sale.id,
            reason="Redeemed at checkout",
            created_by_id=user.id,
        )

    if payload.redeem_points > 0:
        adjust_loyalty_points(
            db,
            customer_id=payload.customer_id,
            points_delta=-payload.redeem_points,
            reference_type="sale",
            reference_id=sale.id,
            reason="Redeemed at checkout",
            created_by_id=user.id,
        )

    if payload.customer_id:
        earn_multiplier = 2 if (customer and customer.is_vip) else 1
        sale.loyalty_points_earned = int(sale.total // 100) * earn_multiplier
        if sale.loyalty_points_earned > 0:
            adjust_loyalty_points(
                db,
                customer_id=payload.customer_id,
                points_delta=sale.loyalty_points_earned,
                reference_type="sale",
                reference_id=sale.id,
                reason="Earned at checkout" + (" (VIP 2x)" if earn_multiplier == 2 else ""),
                created_by_id=user.id,
            )

    if discount_rule:
        discount_rule.times_used += 1

    db.commit()
    return _to_out(_get_or_404(db, sale.id))


@router.get("/{sale_id}/receipt/pdf")
def download_receipt_pdf(sale_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    sale = _get_or_404(db, sale_id)
    pdf_bytes = render_sale_receipt_pdf(sale, sale.outlet.receipt_paper_size, get_app_settings(db))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{sale.invoice_number}.pdf"'},
    )


@router.post("/{sale_id}/send-whatsapp", response_model=ReceiptSendResult)
def send_receipt_whatsapp(sale_id: int, db: Session = Depends(get_db)):
    sale = _get_or_404(db, sale_id)
    if not sale.customer_phone:
        raise HTTPException(400, "No customer phone number on this sale")

    app_settings = get_app_settings(db)
    text = build_sale_receipt_text(sale)
    link = build_wa_me_link(sale.customer_phone, text)

    if is_cloud_api_configured(app_settings):
        pdf_bytes = render_sale_receipt_pdf(sale, sale.outlet.receipt_paper_size, app_settings)
        try:
            send_document_via_cloud_api(
                app_settings, sale.customer_phone, pdf_bytes, f"{sale.invoice_number}.pdf", text
            )
            return ReceiptSendResult(
                ok=True, detail="Sent automatically via WhatsApp, with the invoice PDF attached.", media_attached=True
            )
        except httpx.HTTPError:
            pass  # fall through to a text-only send, then to the manual link

        try:
            send_via_cloud_api(app_settings, sale.customer_phone, text)
            return ReceiptSendResult(
                ok=True,
                detail="The PDF attachment failed, so a text-only receipt was sent automatically instead.",
            )
        except httpx.HTTPError as exc:
            return ReceiptSendResult(
                ok=False, detail=f"Automated send failed ({exc}) - use the link to send manually.", whatsapp_link=link
            )

    return ReceiptSendResult(
        ok=True,
        detail=(
            "WhatsApp Cloud API isn't set up, so the invoice PDF can't be attached automatically - "
            "WhatsApp's tap-to-chat links can only carry text. Download the PDF and attach it manually, "
            "or set up WhatsApp Cloud API in Settings to send it automatically with the invoice attached."
        ),
        whatsapp_link=link,
        needs_setup=True,
    )


@router.post("/{sale_id}/send-sms", response_model=ReceiptSendResult)
def send_receipt_sms(sale_id: int, db: Session = Depends(get_db)):
    sale = _get_or_404(db, sale_id)
    if not sale.customer_phone:
        raise HTTPException(400, "No customer phone number on this sale")

    if not sms_service.is_configured(db):
        raise HTTPException(400, "SMS is not configured - set it up in Settings first")

    text = build_sale_receipt_text(sale)
    try:
        sms_service.send_sms(db, sale.customer_phone, text)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Failed to send SMS: {exc}") from exc
    return ReceiptSendResult(ok=True, detail="SMS sent.")


@router.post("/{sale_id}/send-email", response_model=ReceiptSendResult)
def send_receipt_email(sale_id: int, db: Session = Depends(get_db)):
    sale = _get_or_404(db, sale_id)
    if not sale.customer_email:
        raise HTTPException(400, "No customer email on this sale")

    if not email_service.is_configured(db):
        raise HTTPException(400, "Email is not configured - set it up in Settings first")

    text = build_sale_receipt_text(sale).replace("*", "")
    try:
        email_service.send_email(db, sale.customer_email, f"Receipt {sale.invoice_number}", text)
    except Exception as exc:
        raise HTTPException(502, f"Failed to send email: {exc}") from exc
    return ReceiptSendResult(ok=True, detail="Email sent.")
