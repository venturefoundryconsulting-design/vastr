from datetime import date

from pydantic import BaseModel

from app.models.discount import DiscountScope, DiscountType


class DiscountRuleBase(BaseModel):
    name: str
    code: str | None = None
    discount_type: DiscountType
    scope: DiscountScope = DiscountScope.ALL
    category_id: int | None = None
    brand: str | None = None
    product_id: int | None = None
    vip_only: bool = False
    value: float = 0
    max_discount_amount: float | None = None
    min_purchase_amount: float = 0
    buy_quantity: int | None = None
    get_quantity: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    usage_limit: int | None = None


class DiscountRuleCreate(DiscountRuleBase):
    pass


class DiscountRuleUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    discount_type: DiscountType | None = None
    scope: DiscountScope | None = None
    category_id: int | None = None
    brand: str | None = None
    product_id: int | None = None
    vip_only: bool | None = None
    value: float | None = None
    max_discount_amount: float | None = None
    min_purchase_amount: float | None = None
    buy_quantity: int | None = None
    get_quantity: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    usage_limit: int | None = None
    is_active: bool | None = None


class DiscountRuleOut(DiscountRuleBase):
    id: int
    times_used: int
    is_active: bool

    model_config = {"from_attributes": True}


class DiscountCartItem(BaseModel):
    variant_id: int
    quantity: int
    unit_price: float


class DiscountApplyRequest(BaseModel):
    items: list[DiscountCartItem]
    customer_id: int | None = None
    coupon_code: str | None = None


class DiscountApplyResult(BaseModel):
    applied: bool
    rule_id: int | None = None
    rule_name: str | None = None
    code: str | None = None
    discount_amount: float = 0
    message: str
