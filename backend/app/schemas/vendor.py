from pydantic import BaseModel


class VendorBase(BaseModel):
    name: str
    contact_person: str | None = None
    whatsapp_number: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    gstin: str | None = None
    payment_terms: str | None = None


class VendorCreate(VendorBase):
    pass


class VendorUpdate(BaseModel):
    name: str | None = None
    contact_person: str | None = None
    whatsapp_number: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    gstin: str | None = None
    payment_terms: str | None = None
    is_active: bool | None = None


class VendorOut(VendorBase):
    id: int
    is_active: bool

    model_config = {"from_attributes": True}


class VendorProductCreate(BaseModel):
    vendor_id: int
    variant_id: int
    vendor_sku: str | None = None
    cost_price: float = 0
    is_preferred: bool = True


class VendorProductOut(VendorProductCreate):
    id: int
    sku: str | None = None
    product_name: str | None = None

    model_config = {"from_attributes": True}
