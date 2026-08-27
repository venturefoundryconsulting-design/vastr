from datetime import date
from decimal import Decimal

from pydantic import BaseModel, field_validator

from app.models.bom import BomStatus
from app.schemas.fields import Money, Quantity


class SubstituteIn(BaseModel):
    item_id: int
    priority: int = 0
    notes: str | None = None


class SubstituteOut(SubstituteIn):
    id: int
    sku: str | None = None
    name: str | None = None

    model_config = {"from_attributes": True}


class ComponentIn(BaseModel):
    item_id: int
    quantity: Quantity
    uom_id: int
    scrap_pct: Decimal = Decimal("0")
    is_optional: bool = False
    sequence: int = 0
    notes: str | None = None
    substitutes: list[SubstituteIn] = []

    @field_validator("quantity")
    @classmethod
    def positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Component quantity must be greater than zero")
        return v

    @field_validator("scrap_pct")
    @classmethod
    def scrap_in_range(cls, v: Decimal) -> Decimal:
        if v < 0 or v >= 100:
            raise ValueError("Wastage must be between 0 and 100 percent")
        return v


class ComponentOut(BaseModel):
    id: int
    item_id: int
    sku: str | None = None
    name: str | None = None
    quantity: Quantity
    uom_id: int
    uom_code: str | None = None
    scrap_pct: Decimal
    gross_quantity: Quantity
    is_optional: bool
    sequence: int
    notes: str | None = None
    substitutes: list[SubstituteOut] = []

    model_config = {"from_attributes": True}


class VersionOut(BaseModel):
    id: int
    bom_id: int
    version_no: int
    status: BomStatus
    output_quantity: Quantity
    output_uom_id: int | None = None
    output_uom_code: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    notes: str | None = None
    is_locked: bool
    is_editable: bool
    component_count: int = 0
    components: list[ComponentOut] = []

    model_config = {"from_attributes": True}


class VersionCreate(BaseModel):
    """Creates the next version. If copy_from_version_id is given, that version's
    lines are carried forward - which is how an ACTIVE BOM is 'edited'."""

    output_quantity: Quantity = Decimal("1")
    output_uom_id: int | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    notes: str | None = None
    copy_from_version_id: int | None = None


class BomOut(BaseModel):
    id: int
    item_id: int
    item_sku: str | None = None
    item_name: str | None = None
    name: str
    description: str | None = None
    notes: str | None = None
    is_active: bool
    active_version_no: int | None = None
    version_count: int = 0

    model_config = {"from_attributes": True}


class BomDetail(BomOut):
    versions: list[VersionOut] = []


class BomCreate(BaseModel):
    item_id: int
    name: str
    description: str | None = None
    notes: str | None = None
    # Optional first draft, so a BOM can be created complete in one call - which
    # is what the grid-style builder needs when saving 100+ rows.
    output_quantity: Quantity = Decimal("1")
    output_uom_id: int | None = None
    components: list[ComponentIn] = []


class ComponentsReplace(BaseModel):
    """Whole-list replace for the builder grid.

    The BOM editor is a spreadsheet, not a set of forms: the user adds, edits,
    reorders and deletes many rows and saves once. Diffing that client-side into
    per-row calls would be slower and racier than sending the intended final
    state, and a draft version is cheap to rewrite wholesale.
    """

    components: list[ComponentIn]


class DuplicateWarning(BaseModel):
    item_id: int
    uom_id: int
    count: int
    total_quantity: Quantity
    component_ids: list[int]


class CostLine(BaseModel):
    item_id: int
    sku: str
    name: str
    quantity: Quantity
    uom_id: int
    unit_cost: Money
    line_cost: Money
    is_optional: bool


class CostOut(BaseModel):
    quantity: Quantity
    lines: list[CostLine]
    total_cost: Money


class AvailabilityLine(BaseModel):
    item_id: int
    sku: str
    name: str
    required: Quantity
    uom_id: int | None = None
    on_hand: Quantity
    reserved: Quantity
    available: Quantity
    shortage: Quantity
    suggested_purchase_qty: Quantity
    is_available: bool
    is_optional: bool


class AvailabilityOut(BaseModel):
    quantity: Quantity
    outlet_id: int | None = None
    all_available: bool
    lines: list[AvailabilityLine]


class ExplosionLine(BaseModel):
    item_id: int
    sku: str
    name: str
    quantity: Quantity
    net_quantity: Quantity
    scrap_pct: Decimal
    uom_id: int
    is_optional: bool
    is_subassembly: bool
    level: int
