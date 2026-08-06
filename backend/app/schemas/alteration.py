from datetime import date, datetime

from pydantic import BaseModel

from app.models.alteration import AlterationStatus


class AlterationCreate(BaseModel):
    outlet_id: int
    sale_id: int | None = None
    sale_item_id: int | None = None
    customer_id: int | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    description: str
    tailor_name: str | None = None
    expected_ready_date: date | None = None
    notes: str | None = None


class AlterationUpdate(BaseModel):
    status: AlterationStatus | None = None
    tailor_name: str | None = None
    expected_ready_date: date | None = None
    description: str | None = None
    notes: str | None = None


class AlterationOut(BaseModel):
    id: int
    alteration_number: str
    outlet_id: int
    outlet_name: str | None = None
    sale_id: int | None = None
    sale_invoice_number: str | None = None
    sale_item_id: int | None = None
    item_name: str | None = None
    customer_id: int | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    description: str
    tailor_name: str | None = None
    status: AlterationStatus
    expected_ready_date: date | None = None
    delivered_at: datetime | None = None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
