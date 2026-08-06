from datetime import date, datetime

from pydantic import BaseModel, EmailStr

from app.models.customer import BalanceType
from app.models.sale import PaymentMode


class CustomerBase(BaseModel):
    name: str
    phone: str | None = None
    email: EmailStr | None = None
    whatsapp_number: str | None = None
    is_gst_customer: bool = False
    gstin: str | None = None
    birthday: date | None = None
    anniversary: date | None = None
    preferred_sizes: list[str] = []
    preferred_colors: list[str] = []
    favorite_brands: list[str] = []
    tags: list[str] = []
    notes: str | None = None
    is_vip: bool = False


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    whatsapp_number: str | None = None
    is_gst_customer: bool | None = None
    gstin: str | None = None
    birthday: date | None = None
    anniversary: date | None = None
    preferred_sizes: list[str] | None = None
    preferred_colors: list[str] | None = None
    favorite_brands: list[str] | None = None
    tags: list[str] | None = None
    notes: str | None = None
    is_vip: bool | None = None
    is_active: bool | None = None


class CustomerOut(CustomerBase):
    id: int
    credit_balance: float
    loyalty_points: int
    is_active: bool

    model_config = {"from_attributes": True}


class CustomerAddressBase(BaseModel):
    label: str | None = None
    line1: str
    line2: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    is_default: bool = False


class CustomerAddressCreate(CustomerAddressBase):
    customer_id: int


class CustomerAddressUpdate(BaseModel):
    label: str | None = None
    line1: str | None = None
    line2: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    is_default: bool | None = None


class CustomerAddressOut(CustomerAddressBase):
    id: int
    customer_id: int

    model_config = {"from_attributes": True}


class CustomerBalanceAdjustmentCreate(BaseModel):
    balance_type: BalanceType = BalanceType.CREDIT
    amount_delta: float
    reason: str | None = None


class CustomerBalanceAdjustmentOut(BaseModel):
    id: int
    customer_id: int
    balance_type: BalanceType
    amount_delta: float
    reference_type: str | None = None
    reference_id: int | None = None
    reason: str | None = None
    created_by_id: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CustomerLoyaltyAdjustmentCreate(BaseModel):
    points_delta: int
    reason: str | None = None


class CustomerLoyaltyAdjustmentOut(BaseModel):
    id: int
    customer_id: int
    points_delta: int
    reference_type: str | None = None
    reference_id: int | None = None
    reason: str | None = None
    created_by_id: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CustomerPurchaseOut(BaseModel):
    sale_id: int
    invoice_number: str
    outlet_id: int
    outlet_name: str | None = None
    total: float
    payment_mode: PaymentMode
    created_at: datetime
