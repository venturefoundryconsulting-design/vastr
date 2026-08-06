from typing import Literal

from pydantic import BaseModel

from app.models.product import ImageAngle


class CategoryBase(BaseModel):
    name: str
    parent_id: int | None = None


class CategoryCreate(CategoryBase):
    pass


class CategoryOut(CategoryBase):
    id: int

    model_config = {"from_attributes": True}


class VariantBase(BaseModel):
    sku: str
    barcode: str | None = None
    size: str | None = None
    color: str | None = None
    cost_price: float = 0
    selling_price: float = 0
    mrp: float = 0
    reorder_level: int = 5


class VariantCreate(VariantBase):
    pass


class VariantUpdate(BaseModel):
    sku: str | None = None
    barcode: str | None = None
    size: str | None = None
    color: str | None = None
    cost_price: float | None = None
    selling_price: float | None = None
    mrp: float | None = None
    reorder_level: int | None = None
    is_active: bool | None = None


class VariantOut(VariantBase):
    id: int
    product_id: int
    is_active: bool

    model_config = {"from_attributes": True}


class VariantWithStock(VariantOut):
    product_name: str
    total_stock: int = 0


class ProductBase(BaseModel):
    name: str
    category_id: int | None = None
    brand: str | None = None
    description: str | None = None
    hsn_code: str | None = None
    tax_rate: float = 0


class ProductCreate(ProductBase):
    variants: list[VariantCreate] = []


class ProductUpdate(BaseModel):
    name: str | None = None
    category_id: int | None = None
    brand: str | None = None
    description: str | None = None
    hsn_code: str | None = None
    tax_rate: float | None = None
    is_active: bool | None = None


class ProductImageOut(BaseModel):
    id: int
    product_id: int
    color: str | None = None
    angle: ImageAngle
    url: str
    is_primary: bool
    sort_order: int

    model_config = {"from_attributes": True}


class ProductImageUpdate(BaseModel):
    color: str | None = None
    angle: ImageAngle | None = None
    is_primary: bool | None = None
    sort_order: int | None = None


class ProductOut(ProductBase):
    id: int
    is_active: bool
    variants: list[VariantOut] = []
    images: list[ProductImageOut] = []

    model_config = {"from_attributes": True}


class BulkImportError(BaseModel):
    row: int
    message: str


class BulkImportResult(BaseModel):
    created_products: int
    updated_products: int
    created_variants: int
    updated_variants: int
    total_rows: int
    errors: list[BulkImportError]


class LabelPrintItem(BaseModel):
    variant_id: int
    quantity: int = 1


class LabelPrintRequest(BaseModel):
    items: list[LabelPrintItem]
    layout: Literal["thermal_50x25", "a4_sheet"] = "thermal_50x25"
