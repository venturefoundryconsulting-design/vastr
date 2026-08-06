from pydantic import BaseModel

from app.models.outlet import PaperSize


class OutletBase(BaseModel):
    name: str
    code: str
    address: str | None = None
    phone: str | None = None
    is_warehouse: bool = False


class OutletCreate(OutletBase):
    pass


class OutletUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    phone: str | None = None
    is_warehouse: bool | None = None
    is_active: bool | None = None
    receipt_paper_size: PaperSize | None = None
    transfer_paper_size: PaperSize | None = None


class OutletOut(OutletBase):
    id: int
    is_active: bool
    receipt_paper_size: PaperSize
    transfer_paper_size: PaperSize

    model_config = {"from_attributes": True}
