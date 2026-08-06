from datetime import datetime

from pydantic import BaseModel

from app.models.sale import PaymentMode


class SaleItemCreate(BaseModel):
    variant_id: int
    quantity: int
    unit_price: float
    tax_rate: float = 0


class SaleItemOut(SaleItemCreate):
    id: int
    sku: str | None = None
    product_name: str | None = None

    model_config = {"from_attributes": True}


class SaleCreate(BaseModel):
    outlet_id: int
    customer_id: int | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    customer_email: str | None = None
    discount_amount: float = 0
    coupon_code: str | None = None
    redeem_credit_amount: float = 0
    redeem_points: int = 0
    payment_mode: PaymentMode = PaymentMode.CASH
    items: list[SaleItemCreate]


class SaleOut(BaseModel):
    id: int
    invoice_number: str
    outlet_id: int
    outlet_name: str | None = None
    customer_id: int | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    customer_email: str | None = None
    discount_amount: float
    coupon_code: str | None = None
    rule_discount_amount: float = 0
    discount_rule_name: str | None = None
    credit_applied: float
    points_redeemed: int
    loyalty_points_earned: int
    payment_mode: PaymentMode
    subtotal: float
    tax_amount: float
    total: float
    created_at: datetime
    items: list[SaleItemOut] = []

    model_config = {"from_attributes": True}


class ReceiptSendResult(BaseModel):
    ok: bool
    detail: str
    whatsapp_link: str | None = None
    media_attached: bool = False
    needs_setup: bool = False


class BarcodeLookupResult(BaseModel):
    variant_id: int
    sku: str
    barcode: str | None = None
    product_name: str
    size: str | None = None
    color: str | None = None
    selling_price: float
    tax_rate: float
    available_quantity: int
