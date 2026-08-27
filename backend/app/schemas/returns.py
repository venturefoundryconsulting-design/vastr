from datetime import datetime

from pydantic import BaseModel

from app.models.returns import RefundMode
from app.models.sale import PaymentMode
from app.schemas.fields import Money, Quantity


class ReturnItemCreate(BaseModel):
    sale_item_id: int
    quantity: Quantity
    restock: bool = True


class ExchangeItemCreate(BaseModel):
    variant_id: int
    quantity: Quantity


class ReturnCreate(BaseModel):
    sale_id: int
    outlet_id: int
    reason: str | None = None
    return_items: list[ReturnItemCreate]
    exchange_items: list[ExchangeItemCreate] = []
    refund_mode: RefundMode | None = None
    payment_mode: PaymentMode | None = None


class ReturnItemOut(BaseModel):
    id: int
    sale_item_id: int
    variant_id: int
    quantity: Quantity
    unit_price: Money
    tax_rate: Money
    restock: bool
    sku: str | None = None
    product_name: str | None = None


class ExchangeItemOut(BaseModel):
    id: int
    variant_id: int
    quantity: Quantity
    unit_price: Money
    tax_rate: Money
    sku: str | None = None
    product_name: str | None = None


class ReturnOut(BaseModel):
    id: int
    return_number: str
    sale_id: int
    sale_invoice_number: str | None = None
    outlet_id: int
    outlet_name: str | None = None
    customer_id: int | None = None
    customer_name: str | None = None
    reason: str | None = None
    refund_mode: RefundMode | None = None
    payment_mode: PaymentMode | None = None
    returned_value: Money
    exchanged_value: Money
    difference: Money
    created_by_id: int | None = None
    created_at: datetime
    return_items: list[ReturnItemOut] = []
    exchange_items: list[ExchangeItemOut] = []

    model_config = {"from_attributes": True}
