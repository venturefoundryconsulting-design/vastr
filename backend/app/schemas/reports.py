from datetime import datetime

from pydantic import BaseModel


class SalesTrendPoint(BaseModel):
    date: str
    total: float
    count: int


class PaymentModeBreakdownItem(BaseModel):
    payment_mode: str
    total: float
    count: int


class StockAgingItem(BaseModel):
    variant_id: int
    product_id: int
    sku: str
    product_name: str
    color: str | None = None
    size: str | None = None
    outlet_id: int
    outlet_name: str
    quantity: int
    cost_price: float
    stock_value: float
    last_sold_at: datetime | None = None
    days_since_last_sale: int
