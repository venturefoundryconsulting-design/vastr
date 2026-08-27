import enum
from decimal import Decimal

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TenantMixin, TimestampMixin


class ImageAngle(str, enum.Enum):
    FRONT = "front"
    BACK = "back"
    SIDE = "side"
    DETAIL = "detail"
    OTHER = "other"


class Category(Base, TimestampMixin, TenantMixin):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), default=None)

    parent: Mapped["Category | None"] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list["Category"]] = relationship(back_populates="parent")
    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Product(Base, TimestampMixin, TenantMixin):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), default=None)
    brand: Mapped[str | None] = mapped_column(String(120), default=None)
    description: Mapped[str | None] = mapped_column(String(2000), default=None)
    hsn_code: Mapped[str | None] = mapped_column(String(20), default=None)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    category: Mapped["Category | None"] = relationship(back_populates="products")
    variants: Mapped[list["Item"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    images: Mapped[list["ProductImage"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", order_by="ProductImage.sort_order"
    )


class ItemType(str, enum.Enum):
    RAW_MATERIAL = "raw_material"
    SEMI_FINISHED = "semi_finished"
    FINISHED_PRODUCT = "finished_product"
    PACKAGING = "packaging"
    SERVICE = "service"


class Item(Base, TimestampMixin, TenantMixin):
    """The unified item master - raw materials, garments, packaging, services.

    This is the table formerly called ``product_variants``, renamed rather than
    replaced. Eight tables hold foreign keys to its id (stock_levels,
    stock_movements, sale_items, return_items, exchange_items,
    stock_transfer_items, purchase_order_items, vendor_items), and PostgreSQL
    carries those constraints through a RENAME automatically - so every existing
    id, every sale in history, and every stock level stayed valid with no data
    movement. A new table plus a compatibility *view* was the other option and
    was rejected: a view cannot be the target of a foreign key, so it would have
    meant dropping all eight constraints.

    ``product_id`` is nullable because only finished garments have a parent
    Product to be a variant of; a bolt of silk is an item in its own right. The
    descriptive fields (name, category, brand, tax) live here and were backfilled
    from the parent Product during the migration, so an Item is self-describing
    either way - existing POS code reading ``variant.product.name`` still works,
    and new code can read ``item.name`` directly.
    """

    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sku", name="uq_variant_tenant_sku"),
        UniqueConstraint("tenant_id", "barcode", name="uq_variant_tenant_barcode"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_type: Mapped[ItemType] = mapped_column(
        Enum(ItemType), default=ItemType.FINISHED_PRODUCT, index=True
    )

    # Null for anything that isn't a variant of a garment (raw materials,
    # packaging, services). Kept so existing variant grouping keeps working.
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), default=None)

    sku: Mapped[str] = mapped_column(String(64), index=True)
    barcode: Mapped[str | None] = mapped_column(String(64), index=True, default=None)
    name: Mapped[str | None] = mapped_column(String(200), default=None)
    description: Mapped[str | None] = mapped_column(String(2000), default=None)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), default=None)
    brand: Mapped[str | None] = mapped_column(String(120), default=None)
    hsn_code: Mapped[str | None] = mapped_column(String(20), default=None)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)

    size: Mapped[str | None] = mapped_column(String(20), default=None)
    color: Mapped[str | None] = mapped_column(String(40), default=None)

    stock_uom_id: Mapped[int | None] = mapped_column(
        ForeignKey("units_of_measure.id"), default=None
    )
    purchase_uom_id: Mapped[int | None] = mapped_column(
        ForeignKey("units_of_measure.id"), default=None
    )
    sales_uom_id: Mapped[int | None] = mapped_column(
        ForeignKey("units_of_measure.id"), default=None
    )

    cost_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    selling_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    mrp: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)

    reorder_level: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=5)
    min_stock: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0)

    # Behaviour flags. A raw material is purchasable and stocked but not sellable;
    # a service is neither stocked nor purchasable. These drive which fields the
    # item form shows and whether POS will offer the item at all.
    is_sellable: Mapped[bool] = mapped_column(Boolean, default=True)
    is_purchasable: Mapped[bool] = mapped_column(Boolean, default=True)
    is_stocked: Mapped[bool] = mapped_column(Boolean, default=True)

    notes: Mapped[str | None] = mapped_column(String(1000), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    product: Mapped["Product | None"] = relationship(back_populates="variants")
    category: Mapped["Category | None"] = relationship()
    stock_uom: Mapped["UnitOfMeasure | None"] = relationship(  # noqa: F821
        foreign_keys=[stock_uom_id]
    )
    purchase_uom: Mapped["UnitOfMeasure | None"] = relationship(  # noqa: F821
        foreign_keys=[purchase_uom_id]
    )
    sales_uom: Mapped["UnitOfMeasure | None"] = relationship(  # noqa: F821
        foreign_keys=[sales_uom_id]
    )
    stock_levels: Mapped[list["StockLevel"]] = relationship(back_populates="variant")  # noqa: F821

    @property
    def resolved_name(self) -> str:
        """The item's own name, falling back to its parent product's."""
        return self.name or (self.product.name if self.product else "") or self.sku

    @property
    def display_name(self) -> str:
        bits = [self.resolved_name, self.color, self.size]
        return " / ".join([b for b in bits if b])


# Every pre-Phase-2 module imports ProductVariant by this name (68 references
# across 19 files). It is the same class and the same table - the alias exists so
# that renaming the concept did not require touching working POS, sales, returns
# and reporting code.
ProductVariant = Item


class ProductImage(Base, TimestampMixin, TenantMixin):
    __tablename__ = "product_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    # Ties the image to one color's variants; null means it applies to the whole product.
    color: Mapped[str | None] = mapped_column(String(40), default=None)
    angle: Mapped[ImageAngle] = mapped_column(Enum(ImageAngle), default=ImageAngle.OTHER)
    file_path: Mapped[str] = mapped_column(String(300))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    product: Mapped["Product"] = relationship(back_populates="images")

    @property
    def url(self) -> str:
        return f"/uploads/{self.file_path}"
