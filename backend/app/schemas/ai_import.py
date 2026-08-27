from decimal import Decimal

from pydantic import BaseModel

from app.models.ai_import import AiImportStatus
from app.schemas.fields import Money, Quantity


class AiImportRowOut(BaseModel):
    id: int
    line_no: int
    raw_description: str
    raw_unit_text: str | None = None
    matched_item_id: int | None = None
    matched_item_name: str | None = None
    matched_item_sku: str | None = None
    is_new_item: bool
    proposed_sku: str | None = None
    quantity: Quantity
    uom_id: int | None = None
    uom_code: str | None = None
    unit_cost: Money
    description_confidence: Decimal | None = None
    quantity_confidence: Decimal | None = None
    cost_confidence: Decimal | None = None
    match_confidence: Decimal | None = None
    excluded: bool

    model_config = {"from_attributes": True}


class AiImportRowUpdate(BaseModel):
    raw_description: str | None = None
    quantity: Decimal | None = None
    unit_cost: Decimal | None = None
    uom_id: int | None = None
    matched_item_id: int | None = None
    is_new_item: bool | None = None
    proposed_sku: str | None = None
    excluded: bool | None = None


class AiImportBatchOut(BaseModel):
    id: int
    outlet_id: int
    outlet_name: str | None = None
    vendor_id: int | None = None
    vendor_name: str | None = None
    source_filename: str
    status: AiImportStatus
    vendor_name_guess: str | None = None
    invoice_ref_guess: str | None = None
    goods_receipt_id: int | None = None
    goods_receipt_number: str | None = None
    notes: str | None = None
    created_at: str
    rows: list[AiImportRowOut] = []

    model_config = {"from_attributes": True}


class AiImportBatchSummary(BaseModel):
    id: int
    outlet_name: str | None = None
    vendor_name: str | None = None
    source_filename: str
    status: AiImportStatus
    line_count: int
    created_at: str

    model_config = {"from_attributes": True}
