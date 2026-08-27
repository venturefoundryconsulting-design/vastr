from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String
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

    supplied_products: Mapped[list["VendorItem"]] = relationship(
        back_populates="vendor", cascade="all, delete-orphan"
    )


class VendorItem(Base, TimestampMixin, TenantMixin):
    """What a given vendor charges for a given item, and on what terms.

    Deliberately many-per-item: Gold Lace may come from three vendors at three
    prices, in three different pack sizes. ``is_preferred`` picks the default for
    reorder suggestions; it is not a uniqueness constraint.

    ``purchase_uom_id`` is what lets a vendor quote in rolls while stock is kept
    in metres - paired with an ItemUomConversion carrying this vendor_id, since
    one supplier's roll is 25 m and another's is 50 m.
    """

    __tablename__ = "vendor_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    vendor_sku: Mapped[str | None] = mapped_column(String(64), default=None)
    cost_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=True)

    purchase_uom_id: Mapped[int | None] = mapped_column(
        ForeignKey("units_of_measure.id"), default=None
    )
    min_order_qty: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0)
    lead_time_days: Mapped[int | None] = mapped_column(Integer, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    vendor: Mapped["Vendor"] = relationship(back_populates="supplied_products")
    variant: Mapped["Item"] = relationship()  # noqa: F821
    purchase_uom: Mapped["UnitOfMeasure | None"] = relationship()  # noqa: F821

    @property
    def item_id(self) -> int:
        """New-world alias. The column stays ``variant_id`` so the existing FK,
        index and all pre-Phase-2 queries keep working untouched."""
        return self.variant_id


# Pre-Phase-2 name; same class, same table.
VendorProduct = VendorItem
