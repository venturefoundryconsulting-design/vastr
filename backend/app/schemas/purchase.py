from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.purchase import PurchaseOrderStatus
from app.schemas.fields import Money, Quantity


class PurchaseOrderItemCreate(BaseModel):
    variant_id: int
    quantity_ordered: Quantity
    unit_cost: Money
    tax_rate: Money = Decimal("0")


class PurchaseOrderItemOut(PurchaseOrderItemCreate):
    id: int
    quantity_received: Quantity
    amount: Money
    sku: str | None = None
    product_name: str | None = None

    model_config = {"from_attributes": True}


class PurchaseOrderCreate(BaseModel):
    vendor_id: int
    outlet_id: int
    expected_date: datetime | None = None
    notes: str | None = None
    items: list[PurchaseOrderItemCreate]


class PurchaseOrderOut(BaseModel):
    id: int
    po_number: str
    vendor_id: int
    vendor_name: str | None = None
    outlet_id: int
    outlet_name: str | None = None
    status: PurchaseOrderStatus
    order_date: datetime
    expected_date: datetime | None = None
    notes: str | None = None
    total_amount: Money
    items: list[PurchaseOrderItemOut] = []

    model_config = {"from_attributes": True}


class GoodsReceiptItem(BaseModel):
    item_id: int
    quantity_received: Quantity


class GoodsReceiptRequest(BaseModel):
    items: list[GoodsReceiptItem]


class ReorderSuggestionItem(BaseModel):
    variant_id: int
    sku: str
    product_name: str
    size: str | None = None
    color: str | None = None
    outlet_id: int
    outlet_name: str
    current_quantity: Quantity
    reorder_level: int
    suggested_quantity: Quantity
    cost_price: float


class ReorderSuggestion(BaseModel):
    vendor_id: int
    vendor_name: str
    items: list[ReorderSuggestionItem]
