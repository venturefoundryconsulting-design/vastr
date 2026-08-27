from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.models.discount import DiscountScope, DiscountType
from app.schemas.fields import Money, Quantity


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
    # Decimal, not float/int: a cart line may now be 2.5 m of fabric, and mixing
    # float with the Decimal quantities elsewhere raises TypeError rather than
    # merely losing precision. See app.core.money.
    variant_id: int
    quantity: Quantity
    unit_price: Money


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
