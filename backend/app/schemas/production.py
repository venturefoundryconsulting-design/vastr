from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator

from app.models.production import (
    MaterialAvailability,
    OrderAvailability,
    ProductionPriority,
    ProductionStatus,
)
from app.schemas.fields import Money, Quantity


class ProductionOrderCreate(BaseModel):
    item_id: int
    planned_quantity: Quantity
    location_id: int
    bom_version_id: int | None = None  # defaults to the item's ACTIVE version
    uom_id: int | None = None
    planned_start: date | None = None
    planned_completion: date | None = None
    priority: ProductionPriority = ProductionPriority.NORMAL
    notes: str | None = None

    @field_validator("planned_quantity")
    @classmethod
    def positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Production quantity must be greater than zero")
        return v


class ProductionOrderUpdate(BaseModel):
    """DRAFT/PLANNED only. Changing quantity or BOM version re-derives the
    material snapshot; the server refuses this once released."""

    planned_quantity: Quantity | None = None
    bom_version_id: int | None = None
    location_id: int | None = None
    uom_id: int | None = None
    planned_start: date | None = None
    planned_completion: date | None = None
    priority: ProductionPriority | None = None
    notes: str | None = None


class CloseShortRequest(BaseModel):
    """All fields mandatory by design - a short close must always record what was
    actually made, what was abandoned, and why."""

    produced_quantity: Quantity
    reason: str

    @field_validator("reason")
    @classmethod
    def reason_required(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("A reason is required when closing a production order short")
        return v.strip()

    @field_validator("produced_quantity")
    @classmethod
    def non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("Produced quantity cannot be negative")
        return v


class TransitionRequest(BaseModel):
    reason: str | None = None


class MaterialLine(BaseModel):
    item_id: int
    sku: str
    name: str
    base_quantity: Quantity
    expected_wastage: Quantity
    planned_quantity: Quantity
    required: Quantity
    uom_id: int | None = None
    uom_code: str | None = None
    on_hand: Quantity
    reserved: Quantity
    available: Quantity
    shortage: Quantity
    suggested_purchase_qty: Quantity
    status: MaterialAvailability
    note: str | None = None
    is_optional: bool


class AvailabilityOut(BaseModel):
    overall: OrderAvailability
    lines: list[MaterialLine]


class SnapshotLine(BaseModel):
    """A raw snapshot row, including sub-assemblies, for the hierarchy view."""

    id: int
    item_id: int
    sku: str | None = None
    name: str | None = None
    quantity_per_unit: Quantity
    base_quantity: Quantity
    scrap_pct: Decimal
    expected_wastage: Quantity
    planned_quantity: Quantity
    uom_id: int
    uom_code: str | None = None
    level: int
    parent_item_id: int | None = None
    parent_sku: str | None = None
    is_optional: bool
    is_subassembly: bool
    sequence: int

    model_config = {"from_attributes": True}


class TraceStep(BaseModel):
    level: int
    parent_sku: str | None = None
    parent_name: str | None = None
    quantity_per_unit: Quantity
    base_quantity: Quantity
    scrap_pct: Decimal
    planned_quantity: Quantity


class ProductionOrderOut(BaseModel):
    id: int
    po_number: str
    item_id: int
    item_sku: str | None = None
    item_name: str | None = None
    bom_id: int | None = None
    bom_version_id: int | None = None
    bom_version_no: int | None = None
    planned_quantity: Quantity
    produced_quantity: Quantity
    cancelled_quantity: Quantity
    remaining_quantity: Quantity
    uom_id: int | None = None
    uom_code: str | None = None
    location_id: int
    location_name: str | None = None
    planned_start: date | None = None
    planned_completion: date | None = None
    actual_start: datetime | None = None
    actual_completion: datetime | None = None
    status: ProductionStatus
    priority: ProductionPriority
    notes: str | None = None
    is_editable: bool
    allowed_transitions: list[ProductionStatus] = []
    material_count: int = 0
    created_by_id: int | None = None
    released_by_id: int | None = None
    released_at: datetime | None = None
    close_short_reason: str | None = None
    closed_short_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ProductionOrderDetail(ProductionOrderOut):
    materials: list[SnapshotLine] = []
    availability: AvailabilityOut | None = None


class HistoryEntry(BaseModel):
    action: str
    user_id: int | None = None
    created_at: datetime
    details: dict | None = None


class OutputRequest(BaseModel):
    """Record finished goods from a production run."""

    quantity: Quantity
    location_id: int | None = None
    note: str | None = None

    @field_validator("quantity")
    @classmethod
    def positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Output quantity must be greater than zero")
        return v


class OutputOut(BaseModel):
    id: int
    production_order_id: int
    item_id: int
    sku: str | None = None
    name: str | None = None
    location_id: int
    quantity: Quantity
    uom_id: int | None = None
    uom_code: str | None = None
    stock_movement_id: int | None = None
    note: str | None = None
    produced_by_id: int | None = None
    created_at: datetime | None = None
