from datetime import datetime

from pydantic import BaseModel

from app.models.inventory import MovementType
from app.schemas.fields import Quantity


class StockLevelOut(BaseModel):
    id: int
    variant_id: int
    outlet_id: int
    quantity: Quantity

    model_config = {"from_attributes": True}


class StockLevelDetail(StockLevelOut):
    sku: str
    product_name: str
    size: str | None = None
    color: str | None = None
    outlet_name: str
    reorder_level: int


class StockAdjustment(BaseModel):
    variant_id: int
    outlet_id: int
    quantity_delta: Quantity
    note: str | None = None


class StockMovementOut(BaseModel):
    id: int
    variant_id: int
    outlet_id: int
    movement_type: MovementType
    quantity_delta: Quantity
    reference_type: str | None = None
    reference_id: int | None = None
    note: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LowStockItem(BaseModel):
    variant_id: int
    sku: str
    product_name: str
    size: str | None = None
    color: str | None = None
    outlet_id: int
    outlet_name: str
    quantity: Quantity
    reorder_level: int
    preferred_vendor_id: int | None = None
    preferred_vendor_name: str | None = None
