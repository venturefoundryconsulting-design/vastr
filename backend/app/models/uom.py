"""Units of measure and conversion.

Two kinds of conversion exist here, and keeping them apart is the whole design:

**Standard conversion** is physics and lives on the unit itself. Every unit
carries ``factor_to_base``, the multiplier that takes it to its category's base
unit (metre for LENGTH, gram for WEIGHT...). Converting between any two units of
the same category is then ``qty * from.factor_to_base / to.factor_to_base`` - no
lookup table, no missing-pair problem, and m->cm->mm all follow automatically.
Converting *across* categories is refused: piece -> metre is not a fact about the
world.

**Item-specific conversion** is packaging, and lives in ItemUomConversion. "1 roll
= 25 m" is true of one particular lace from one particular vendor, not of rolls in
general - another vendor's roll is 50 m. These conversions are therefore allowed
to cross categories (a roll is a count, a metre is a length), because that is
exactly what a packaging rule expresses.
"""

from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TenantMixin, TimestampMixin

# Conversion factors need far more headroom than quantities: 1 gram in tonnes is
# 0.000001, and chaining conversions multiplies the error if the scale is tight.
FactorType = Numeric(20, 10)


class UomCategory(Base, TimestampMixin, TenantMixin):
    """A dimension - LENGTH, WEIGHT, VOLUME, COUNT.

    A table rather than an enum because the admin UI has to be able to add one
    (AREA, TIME) without a code change, per the Phase 2 brief. Each category has
    exactly one base unit, which is the anchor all its factors are relative to.
    """

    __tablename__ = "uom_categories"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_uom_category_tenant_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), index=True)
    name: Mapped[str] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    units: Mapped[list["UnitOfMeasure"]] = relationship(
        back_populates="category", cascade="all, delete-orphan"
    )


class UnitOfMeasure(Base, TimestampMixin, TenantMixin):
    __tablename__ = "units_of_measure"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_uom_tenant_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(80))
    symbol: Mapped[str | None] = mapped_column(String(12), default=None)
    category_id: Mapped[int] = mapped_column(ForeignKey("uom_categories.id"), index=True)

    # Multiplier to this category's base unit. Base unit itself is exactly 1.
    factor_to_base: Mapped[Decimal] = mapped_column(FactorType, default=Decimal("1"))
    is_base: Mapped[bool] = mapped_column(Boolean, default=False)

    # How many decimals make sense when *displaying* this unit. Pieces are whole;
    # metres are sensibly shown to 2-3 dp. Storage is always 4 dp regardless -
    # this is a UI hint, not a storage constraint.
    decimal_precision: Mapped[int] = mapped_column(Integer, default=2)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    category: Mapped["UomCategory"] = relationship(back_populates="units")

    @property
    def display(self) -> str:
        return self.symbol or self.code


class ItemUomConversion(Base, TimestampMixin, TenantMixin):
    """A packaging rule for one item: 1 <from_uom> = <factor> <to_uom>.

    ``vendor_id`` is nullable and is what makes "vendor A's roll is 25 m, vendor
    B's is 50 m" expressible. Resolution order when converting is: a rule for this
    item AND this vendor, then a rule for this item with no vendor, then the
    standard same-category factor. See app.services.uom.convert.
    """

    __tablename__ = "item_uom_conversions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "item_id", "from_uom_id", "to_uom_id", "vendor_id",
            name="uq_item_uom_conversion",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    from_uom_id: Mapped[int] = mapped_column(ForeignKey("units_of_measure.id"))
    to_uom_id: Mapped[int] = mapped_column(ForeignKey("units_of_measure.id"))
    factor: Mapped[Decimal] = mapped_column(FactorType)
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"), default=None, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    from_uom: Mapped["UnitOfMeasure"] = relationship(foreign_keys=[from_uom_id])
    to_uom: Mapped["UnitOfMeasure"] = relationship(foreign_keys=[to_uom_id])
