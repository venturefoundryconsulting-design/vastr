from datetime import datetime

from pydantic import BaseModel

from app.models.transfer import TransferStatus
from app.schemas.fields import Quantity


class TransferItemCreate(BaseModel):
    variant_id: int
    quantity_requested: Quantity


class TransferItemOut(TransferItemCreate):
    id: int
    quantity_sent: Quantity
    quantity_received: Quantity
    sku: str | None = None
    product_name: str | None = None

    model_config = {"from_attributes": True}


class TransferCreate(BaseModel):
    source_outlet_id: int
    dest_outlet_id: int
    notes: str | None = None
    items: list[TransferItemCreate]


class TransferUpdate(BaseModel):
    """Full edit of a transfer - only allowed while status is still 'requested'
    (i.e. before anything has actually moved). Items are replaced wholesale."""

    source_outlet_id: int
    dest_outlet_id: int
    notes: str | None = None
    items: list[TransferItemCreate]


class TransferOut(BaseModel):
    id: int
    transfer_number: str
    source_outlet_id: int
    source_outlet_name: str | None = None
    dest_outlet_id: int
    dest_outlet_name: str | None = None
    status: TransferStatus
    notes: str | None = None
    dispatched_at: datetime | None = None
    received_at: datetime | None = None
    items: list[TransferItemOut] = []

    model_config = {"from_attributes": True}


class DispatchItem(BaseModel):
    item_id: int
    quantity_sent: Quantity


class DispatchRequest(BaseModel):
    items: list[DispatchItem]


class ReceiveItem(BaseModel):
    item_id: int
    quantity_received: Quantity


class ReceiveRequest(BaseModel):
    items: list[ReceiveItem]
