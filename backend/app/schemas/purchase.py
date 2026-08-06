from datetime import datetime

from pydantic import BaseModel

from app.models.purchase import PurchaseOrderStatus


class PurchaseOrderItemCreate(BaseModel):
    variant_id: int
    quantity_ordered: int
    unit_cost: float
    tax_rate: float = 0


class PurchaseOrderItemOut(PurchaseOrderItemCreate):
    id: int
    quantity_received: int
    amount: float
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
    total_amount: float
    items: list[PurchaseOrderItemOut] = []

    model_config = {"from_attributes": True}


class GoodsReceiptItem(BaseModel):
    item_id: int
    quantity_received: int


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
    current_quantity: int
    reorder_level: int
    suggested_quantity: int
    cost_price: float


class ReorderSuggestion(BaseModel):
    vendor_id: int
    vendor_name: str
    items: list[ReorderSuggestionItem]
