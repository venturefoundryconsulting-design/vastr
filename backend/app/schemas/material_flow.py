from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator

from app.models.material_flow import ReservationStatus
from app.models.production import ProductionStatus
from app.schemas.fields import Quantity


class _PositiveLine(BaseModel):
    material_id: int
    quantity: Quantity

    @field_validator("quantity")
    @classmethod
    def positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Quantity must be greater than zero")
        return v


class ReserveLine(_PositiveLine):
    note: str | None = None


class ReserveRequest(BaseModel):
    lines: list[ReserveLine]


class ReleaseRequest(BaseModel):
    """Empty reservation_ids means "release everything outstanding on this order"
    - the cancel/close-short case."""

    reservation_ids: list[int] = []
    reason: str | None = None


class IssueLine(_PositiveLine):
    note: str | None = None
    # Requires materials.issue_unreserved, which no role holds by default.
    allow_unreserved: bool = False
    unreserved_reason: str | None = None


class IssueRequest(BaseModel):
    lines: list[IssueLine]


class ConsumeLine(_PositiveLine):
    note: str | None = None
    allow_over_consumption: bool = False
    over_consumption_reason: str | None = None


class ConsumeRequest(BaseModel):
    lines: list[ConsumeLine]


class ReturnLine(_PositiveLine):
    reason: str | None = None
    # False when the material comes back damaged: no ledger row, so it does not
    # re-enter usable stock.
    restock: bool = True


class ReturnRequest(BaseModel):
    lines: list[ReturnLine]


class MaterialPosition(BaseModel):
    material_id: int
    item_id: int
    sku: str | None = None
    name: str | None = None
    uom_id: int | None = None
    uom_code: str | None = None
    planned: Quantity
    reserved: Quantity
    issued: Quantity
    consumed: Quantity
    returned: Quantity
    wasted: Quantity
    remaining_to_reserve: Quantity
    remaining_to_issue: Quantity
    returnable: Quantity
    still_with_production: Quantity
    on_hand: Quantity
    available: Quantity


class OrderMaterialSummary(BaseModel):
    production_order_id: int
    po_number: str
    status: ProductionStatus
    lines: list[MaterialPosition]
    fully_reserved: bool
    fully_issued: bool


class ReservationOut(BaseModel):
    id: int
    production_order_material_id: int
    item_id: int
    sku: str | None = None
    name: str | None = None
    location_id: int
    quantity: Quantity
    issued_quantity: Quantity
    outstanding: Quantity
    uom_id: int
    uom_code: str | None = None
    status: ReservationStatus
    note: str | None = None
    released_at: datetime | None = None
    release_reason: str | None = None
    created_at: datetime | None = None


class IssueOut(BaseModel):
    id: int
    production_order_material_id: int
    item_id: int
    sku: str | None = None
    name: str | None = None
    quantity: Quantity
    uom_id: int
    uom_code: str | None = None
    stock_movement_id: int | None = None
    unreserved_reason: str | None = None
    note: str | None = None
    issued_by_id: int | None = None
    created_at: datetime | None = None


class ConsumptionOut(BaseModel):
    id: int
    production_order_material_id: int
    item_id: int
    sku: str | None = None
    name: str | None = None
    quantity: Quantity
    uom_id: int
    uom_code: str | None = None
    over_consumption_reason: str | None = None
    note: str | None = None
    recorded_by_id: int | None = None
    created_at: datetime | None = None


class ReturnOut(BaseModel):
    id: int
    production_order_material_id: int
    item_id: int
    sku: str | None = None
    name: str | None = None
    quantity: Quantity
    uom_id: int
    uom_code: str | None = None
    stock_movement_id: int | None = None
    reason: str | None = None
    restock: bool
    returned_by_id: int | None = None
    created_at: datetime | None = None
