from decimal import Decimal

from pydantic import BaseModel, field_validator

from app.models.product import ItemType
from app.schemas.fields import Money, Quantity


class UomCategoryOut(BaseModel):
    id: int
    code: str
    name: str
    is_active: bool

    model_config = {"from_attributes": True}


class UomCategoryCreate(BaseModel):
    code: str
    name: str


class UomOut(BaseModel):
    id: int
    code: str
    name: str
    symbol: str | None = None
    category_id: int
    category_code: str | None = None
    factor_to_base: Decimal
    is_base: bool
    decimal_precision: int
    is_active: bool

    model_config = {"from_attributes": True}


class UomCreate(BaseModel):
    code: str
    name: str
    symbol: str | None = None
    category_id: int
    factor_to_base: Decimal = Decimal("1")
    is_base: bool = False
    decimal_precision: int = 2

    @field_validator("factor_to_base")
    @classmethod
    def factor_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Conversion factor must be greater than zero")
        return v


class UomUpdate(BaseModel):
    name: str | None = None
    symbol: str | None = None
    decimal_precision: int | None = None
    is_active: bool | None = None


class ItemUomConversionOut(BaseModel):
    id: int
    item_id: int
    from_uom_id: int
    to_uom_id: int
    from_uom_code: str | None = None
    to_uom_code: str | None = None
    factor: Decimal
    vendor_id: int | None = None
    vendor_name: str | None = None
    is_active: bool

    model_config = {"from_attributes": True}


class ItemUomConversionCreate(BaseModel):
    from_uom_id: int
    to_uom_id: int
    factor: Decimal
    vendor_id: int | None = None

    @field_validator("factor")
    @classmethod
    def factor_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Conversion factor must be greater than zero")
        return v


class ConvertRequest(BaseModel):
    quantity: Quantity
    from_uom_id: int
    to_uom_id: int
    item_id: int | None = None
    vendor_id: int | None = None


class ConvertResult(BaseModel):
    quantity: Quantity
    from_uom: str
    to_uom: str


class VendorItemOut(BaseModel):
    id: int
    vendor_id: int
    vendor_name: str | None = None
    variant_id: int
    vendor_sku: str | None = None
    cost_price: Money
    purchase_uom_id: int | None = None
    purchase_uom_code: str | None = None
    min_order_qty: Quantity
    lead_time_days: int | None = None
    is_preferred: bool
    is_active: bool

    model_config = {"from_attributes": True}


class VendorItemCreate(BaseModel):
    vendor_id: int
    vendor_sku: str | None = None
    cost_price: Money = Decimal("0")
    purchase_uom_id: int | None = None
    min_order_qty: Quantity = Decimal("0")
    lead_time_days: int | None = None
    is_preferred: bool = False


class ItemBase(BaseModel):
    sku: str
    name: str | None = None
    description: str | None = None
    item_type: ItemType = ItemType.FINISHED_PRODUCT
    category_id: int | None = None
    brand: str | None = None
    barcode: str | None = None
    hsn_code: str | None = None
    tax_rate: Money = Decimal("0")
    size: str | None = None
    color: str | None = None
    stock_uom_id: int | None = None
    purchase_uom_id: int | None = None
    sales_uom_id: int | None = None
    cost_price: Money = Decimal("0")
    selling_price: Money = Decimal("0")
    mrp: Money = Decimal("0")
    reorder_level: Quantity = Decimal("0")
    min_stock: Quantity = Decimal("0")
    is_sellable: bool = True
    is_purchasable: bool = True
    is_stocked: bool = True
    notes: str | None = None
    is_active: bool = True


class ItemCreate(ItemBase):
    product_id: int | None = None


class ItemUpdate(BaseModel):
    """Every field optional - this is a PATCH. sku is deliberately absent:
    changing an SKU after stock and sales reference it is a data-migration
    decision, not an edit."""

    name: str | None = None
    description: str | None = None
    item_type: ItemType | None = None
    category_id: int | None = None
    brand: str | None = None
    barcode: str | None = None
    hsn_code: str | None = None
    tax_rate: Money | None = None
    size: str | None = None
    color: str | None = None
    stock_uom_id: int | None = None
    purchase_uom_id: int | None = None
    sales_uom_id: int | None = None
    cost_price: Money | None = None
    selling_price: Money | None = None
    mrp: Money | None = None
    reorder_level: Quantity | None = None
    min_stock: Quantity | None = None
    is_sellable: bool | None = None
    is_purchasable: bool | None = None
    is_stocked: bool | None = None
    notes: str | None = None
    is_active: bool | None = None


class ItemOut(ItemBase):
    id: int
    product_id: int | None = None
    product_name: str | None = None
    category_name: str | None = None
    stock_uom_code: str | None = None
    purchase_uom_code: str | None = None
    sales_uom_code: str | None = None
    display_name: str | None = None
    total_stock: Quantity = Decimal("0")

    model_config = {"from_attributes": True}
