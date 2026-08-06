from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TenantMixin, TimestampMixin


class Vendor(Base, TimestampMixin, TenantMixin):
    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    contact_person: Mapped[str | None] = mapped_column(String(120), default=None)
    # Full international format e.g. 91XXXXXXXXXX, used for wa.me links / Cloud API
    whatsapp_number: Mapped[str | None] = mapped_column(String(20), default=None)
    phone: Mapped[str | None] = mapped_column(String(20), default=None)
    email: Mapped[str | None] = mapped_column(String(255), default=None)
    address: Mapped[str | None] = mapped_column(String(255), default=None)
    gstin: Mapped[str | None] = mapped_column(String(20), default=None)
    payment_terms: Mapped[str | None] = mapped_column(String(120), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    supplied_products: Mapped[list["VendorProduct"]] = relationship(
        back_populates="vendor", cascade="all, delete-orphan"
    )


class VendorProduct(Base, TimestampMixin, TenantMixin):
    """Which vendor supplies which variant, and at what cost - drives reorder suggestions."""

    __tablename__ = "vendor_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"))
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id"))
    vendor_sku: Mapped[str | None] = mapped_column(String(64), default=None)
    cost_price: Mapped[float] = mapped_column(default=0)
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=True)

    vendor: Mapped["Vendor"] = relationship(back_populates="supplied_products")
    variant: Mapped["ProductVariant"] = relationship()  # noqa: F821
