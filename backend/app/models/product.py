import enum

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
    variants: Mapped[list["ProductVariant"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    images: Mapped[list["ProductImage"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", order_by="ProductImage.sort_order"
    )


class ProductVariant(Base, TimestampMixin, TenantMixin):
    __tablename__ = "product_variants"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sku", name="uq_variant_tenant_sku"),
        UniqueConstraint("tenant_id", "barcode", name="uq_variant_tenant_barcode"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    sku: Mapped[str] = mapped_column(String(64), index=True)
    barcode: Mapped[str | None] = mapped_column(String(64), index=True, default=None)
    size: Mapped[str | None] = mapped_column(String(20), default=None)
    color: Mapped[str | None] = mapped_column(String(40), default=None)
    cost_price: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    selling_price: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    mrp: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    reorder_level: Mapped[int] = mapped_column(default=5)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    product: Mapped["Product"] = relationship(back_populates="variants")
    stock_levels: Mapped[list["StockLevel"]] = relationship(back_populates="variant")  # noqa: F821

    @property
    def display_name(self) -> str:
        bits = [self.product.name if self.product else "", self.color, self.size]
        return " / ".join([b for b in bits if b])


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
