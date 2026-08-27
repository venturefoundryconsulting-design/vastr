"""Bill of Materials.

NAMING: the line table is ``bom_components``, not ``bom_items``. The existing
convention for document lines is ``<doc>_items`` (sale_items, return_items,
purchase_order_items), but since Phase 2 ``items`` is the Item Master table, and
"bom_items" would read as "items that are BOMs" rather than "the materials a BOM
consumes". Clarity wins over consistency in this one case.

HISTORICAL INTEGRITY - the property everything else depends on:

A production order will reference a *version*, never the BOM header, and a
version is immutable from the moment it leaves DRAFT. Edits to an ACTIVE or
ARCHIVED version are refused by the service layer; changing a live recipe means
creating a new version, which copies the current lines forward. ``is_locked`` is
the harder stop, set when production first consumes the version, and it survives
archiving.

That is why ``production_order.bom_version_id`` alone is enough to reproduce what
the BOM looked like at the time: the row it points at cannot have changed. Phase
3C layers a per-order snapshot on top of this, but that snapshot exists to record
per-order *overrides*, not to compensate for a mutable BOM.

QUANTITY SEMANTICS:

``BomComponent.quantity`` is expected **net consumption** - the material that ends
up in the finished garment. ``scrap_pct`` is the additional expected loss on top.
So 8 m of lace with 5% scrap is stored as quantity=8, scrap_pct=5, and the planned
issue requirement is 8 x 1.05 = 8.4 m. The base quantity is never rewritten to
fold wastage in; planned and actual stay separately answerable.
"""

import enum
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.inventory import QuantityType
from app.models.mixins import TenantMixin, TimestampMixin

# Scrap is a percentage with room for fine tolerances (0.125% is meaningful on
# expensive stones), hence 3 decimal places rather than 2.
ScrapType = Numeric(6, 3)


class BomStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class Bom(Base, TimestampMixin, TenantMixin):
    """The recipe header for one manufactured item.

    One BOM per item (enforced by the unique constraint): "only one appropriate
    BOM version active for an item at a time" then follows directly from the
    one-ACTIVE-version-per-BOM rule, with no cross-BOM coordination needed. If
    alternate production routes for the same garment are ever required, that
    becomes a deliberate schema change rather than something the data model
    silently already allowed.
    """

    __tablename__ = "boms"
    __table_args__ = (UniqueConstraint("tenant_id", "item_id", name="uq_bom_tenant_item"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(2000), default=None)
    notes: Mapped[str | None] = mapped_column(String(1000), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    item: Mapped["Item"] = relationship()  # noqa: F821
    versions: Mapped[list["BomVersion"]] = relationship(
        back_populates="bom", cascade="all, delete-orphan", order_by="BomVersion.version_no"
    )

    @property
    def active_version(self) -> "BomVersion | None":
        return next((v for v in self.versions if v.status == BomStatus.ACTIVE), None)


class BomVersion(Base, TimestampMixin, TenantMixin):
    __tablename__ = "bom_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "bom_id", "version_no", name="uq_bom_version_no"),
        # One ACTIVE version per BOM, enforced by the database rather than by
        # application discipline. Partial unique index - DRAFT and ARCHIVED rows
        # are unconstrained, so a BOM may have many drafts and much history.
        Index(
            "uq_bom_one_active_version",
            "bom_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bom_id: Mapped[int] = mapped_column(ForeignKey("boms.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[BomStatus] = mapped_column(Enum(BomStatus), default=BomStatus.DRAFT, index=True)

    # What one "batch" of this recipe yields. Requirements scale by
    # requested_qty / output_quantity, so a BOM whose natural batch is 10 metres
    # of piping is expressible without pretending it makes exactly one thing.
    output_quantity: Mapped[Decimal] = mapped_column(QuantityType, default=Decimal("1"))
    output_uom_id: Mapped[int | None] = mapped_column(
        ForeignKey("units_of_measure.id"), default=None
    )

    effective_from: Mapped[Date | None] = mapped_column(Date, default=None)
    effective_to: Mapped[Date | None] = mapped_column(Date, default=None)
    notes: Mapped[str | None] = mapped_column(String(1000), default=None)

    # Set the first time a production order references this version. Distinct
    # from status: an ARCHIVED version that was never used may still be deleted,
    # a locked one may not, ever.
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)

    bom: Mapped["Bom"] = relationship(back_populates="versions")
    output_uom: Mapped["UnitOfMeasure | None"] = relationship()  # noqa: F821
    components: Mapped[list["BomComponent"]] = relationship(
        back_populates="version", cascade="all, delete-orphan", order_by="BomComponent.sequence"
    )

    @property
    def is_editable(self) -> bool:
        return self.status == BomStatus.DRAFT and not self.is_locked


class BomComponent(Base, TimestampMixin, TenantMixin):
    __tablename__ = "bom_components"
    __table_args__ = (
        Index("ix_bom_components_version_seq", "bom_version_id", "sequence"),
        Index("ix_bom_components_item", "item_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bom_version_id: Mapped[int] = mapped_column(ForeignKey("bom_versions.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))

    # Net consumption, in `uom_id`. Not necessarily the item's stock UoM - a BOM
    # may specify 450 cm of a fabric stocked in metres, and the Phase 2
    # conversion engine reconciles the two.
    quantity: Mapped[Decimal] = mapped_column(QuantityType)
    uom_id: Mapped[int] = mapped_column(ForeignKey("units_of_measure.id"))

    scrap_pct: Mapped[Decimal] = mapped_column(ScrapType, default=Decimal("0"))
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(String(500), default=None)

    version: Mapped["BomVersion"] = relationship(back_populates="components")
    item: Mapped["Item"] = relationship()  # noqa: F821
    substitutes: Mapped[list["BomComponentSubstitute"]] = relationship(
        back_populates="component", cascade="all, delete-orphan",
        order_by="BomComponentSubstitute.priority",
    )

    @property
    def gross_quantity(self) -> Decimal:
        """Net consumption plus expected scrap - what production should issue.

        The stored `quantity` is deliberately left alone; this is derived on read
        so planned-vs-actual variance stays answerable against the real recipe.
        """
        return self.quantity * (Decimal("1") + self.scrap_pct / Decimal("100"))


class BomComponentSubstitute(Base, TimestampMixin, TenantMixin):
    """An approved alternative for a component.

    Deliberately inert: nothing substitutes automatically. Production records
    which material was actually used, and that record - not this table - is what
    costing and traceability read. This is a list of what a tailor is *allowed*
    to reach for when the primary runs out.
    """

    __tablename__ = "bom_component_substitutes"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "bom_component_id", "item_id", name="uq_bom_substitute_component_item"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bom_component_id: Mapped[int] = mapped_column(ForeignKey("bom_components.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    priority: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(String(500), default=None)

    component: Mapped["BomComponent"] = relationship(back_populates="substitutes")
    item: Mapped["Item"] = relationship()  # noqa: F821
