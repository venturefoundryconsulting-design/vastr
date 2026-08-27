"""Production orders and their material requirement snapshot.

PHASE 3C IS PLANNING ONLY. Nothing in this module writes to stock_levels or
stock_movements, directly or indirectly. Creating, planning, releasing,
cancelling or short-closing a production order leaves inventory byte-identical.
Reservation and physical movement are Phase 3D.

WHY A SNAPSHOT TABLE EXISTS AT ALL

Phase 3B already guarantees a bom_version is immutable once it leaves DRAFT, so
``production_orders.bom_version_id`` alone is enough to reproduce the recipe. The
snapshot in ``production_order_materials`` is not a workaround for that - it
exists because:

  * a multi-level explosion is expensive to recompute on every screen refresh;
  * Phase 3D needs somewhere to hang reserved / issued / consumed per material,
    and those columns belong on the order's own line, not on the shared BOM;
  * per-order deviations (substituting a material for one run) have to live
    somewhere that is not the BOM.

The snapshot is rebuilt while the order is still DRAFT or PLANNED - so changing
the quantity re-derives requirements - and frozen the moment it is RELEASED.
Releasing also sets ``bom_version.is_locked``, which Phase 3B defined and
deliberately left for whoever first consumed a version.
"""

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.bom import ScrapType
from app.models.inventory import QuantityType
from app.models.mixins import TenantMixin, TimestampMixin


class ProductionStatus(str, enum.Enum):
    DRAFT = "draft"
    PLANNED = "planned"
    RELEASED = "released"
    IN_PROGRESS = "in_progress"
    PARTIALLY_COMPLETED = "partially_completed"
    COMPLETED = "completed"
    ON_HOLD = "on_hold"
    CANCELLED = "cancelled"
    CLOSED_SHORT = "closed_short"


class ProductionPriority(str, enum.Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class MaterialAvailability(str, enum.Enum):
    """Per-material verdict. Computed, never stored - stock moves underneath it."""

    AVAILABLE = "available"
    PARTIAL = "partial"
    SHORT = "short"
    NOT_STOCKED = "not_stocked"
    INVALID = "invalid"


class OrderAvailability(str, enum.Enum):
    READY = "ready"
    PARTIAL_MATERIAL = "partial_material"
    MATERIAL_SHORTAGE = "material_shortage"
    INVALID_MATERIAL = "invalid_material"


# Terminal states accept no further transition.
TERMINAL = {ProductionStatus.COMPLETED, ProductionStatus.CANCELLED, ProductionStatus.CLOSED_SHORT}

# The state machine, enforced server-side. A status is never assignable
# directly - every change goes through app.services.production.transition, which
# checks membership here. Anything absent is refused.
ALLOWED_TRANSITIONS: dict[ProductionStatus, set[ProductionStatus]] = {
    ProductionStatus.DRAFT: {ProductionStatus.PLANNED, ProductionStatus.CANCELLED},
    ProductionStatus.PLANNED: {
        ProductionStatus.RELEASED,
        ProductionStatus.DRAFT,  # back to editing while nothing is committed
        ProductionStatus.CANCELLED,
    },
    ProductionStatus.RELEASED: {
        ProductionStatus.IN_PROGRESS,
        ProductionStatus.ON_HOLD,
        ProductionStatus.CANCELLED,
    },
    ProductionStatus.IN_PROGRESS: {
        ProductionStatus.PARTIALLY_COMPLETED,
        ProductionStatus.COMPLETED,
        ProductionStatus.ON_HOLD,
        ProductionStatus.CLOSED_SHORT,
    },
    ProductionStatus.PARTIALLY_COMPLETED: {
        ProductionStatus.IN_PROGRESS,
        ProductionStatus.COMPLETED,
        ProductionStatus.ON_HOLD,
        ProductionStatus.CLOSED_SHORT,
    },
    # Resume returns to whichever state the order was paused from; the service
    # records that, so ON_HOLD can legitimately go back to either.
    ProductionStatus.ON_HOLD: {
        ProductionStatus.RELEASED,
        ProductionStatus.IN_PROGRESS,
        ProductionStatus.CANCELLED,
    },
    ProductionStatus.COMPLETED: set(),
    ProductionStatus.CANCELLED: set(),
    ProductionStatus.CLOSED_SHORT: set(),
}

# While in these states the requirement snapshot is still derived from the BOM;
# after that it is frozen and only Phase 3D's consumption columns may change.
RECALCULABLE = {ProductionStatus.DRAFT, ProductionStatus.PLANNED}


class ProductionOrder(Base, TimestampMixin, TenantMixin):
    __tablename__ = "production_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "po_number", name="uq_production_order_tenant_number"),
        Index("ix_production_orders_tenant_status", "tenant_id", "status"),
        Index("ix_production_orders_tenant_item", "tenant_id", "item_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    po_number: Mapped[str] = mapped_column(String(30), index=True)

    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    bom_id: Mapped[int | None] = mapped_column(ForeignKey("boms.id"), default=None)
    # The exact recipe this order was planned against. Never updated when a newer
    # BOM version is activated - that is the whole point.
    bom_version_id: Mapped[int | None] = mapped_column(ForeignKey("bom_versions.id"), default=None)

    planned_quantity: Mapped[Decimal] = mapped_column(QuantityType)
    produced_quantity: Mapped[Decimal] = mapped_column(QuantityType, default=Decimal("0"))
    cancelled_quantity: Mapped[Decimal] = mapped_column(QuantityType, default=Decimal("0"))
    uom_id: Mapped[int | None] = mapped_column(ForeignKey("units_of_measure.id"), default=None)

    location_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"), index=True)

    planned_start: Mapped[date | None] = mapped_column(Date, default=None)
    planned_completion: Mapped[date | None] = mapped_column(Date, default=None)
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    actual_completion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    status: Mapped[ProductionStatus] = mapped_column(
        Enum(ProductionStatus), default=ProductionStatus.DRAFT, index=True
    )
    priority: Mapped[ProductionPriority] = mapped_column(
        Enum(ProductionPriority), default=ProductionPriority.NORMAL
    )
    notes: Mapped[str | None] = mapped_column(String(1000), default=None)

    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    released_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    # Closing short is never implicit: all four of these are required together,
    # so "we stopped at 6 of 10" always carries who decided that and why.
    close_short_reason: Mapped[str | None] = mapped_column(String(500), default=None)
    closed_short_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    closed_short_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    # Remembers where ON_HOLD was entered from so Resume is unambiguous.
    resume_status: Mapped[ProductionStatus | None] = mapped_column(
        Enum(ProductionStatus), default=None
    )

    item: Mapped["Item"] = relationship(foreign_keys=[item_id])  # noqa: F821
    bom_version: Mapped["BomVersion | None"] = relationship()  # noqa: F821
    location: Mapped["Outlet"] = relationship()  # noqa: F821
    uom: Mapped["UnitOfMeasure | None"] = relationship()  # noqa: F821
    materials: Mapped[list["ProductionOrderMaterial"]] = relationship(
        back_populates="production_order",
        cascade="all, delete-orphan",
        order_by="ProductionOrderMaterial.sequence",
    )

    @property
    def remaining_quantity(self) -> Decimal:
        return self.planned_quantity - self.produced_quantity - self.cancelled_quantity

    @property
    def is_editable(self) -> bool:
        return self.status in RECALCULABLE


class ProductionOrderMaterial(Base, TimestampMixin, TenantMixin):
    """One material this order needs - snapshotted from the BOM explosion.

    Base quantity, expected wastage and planned issue are stored as three
    separate numbers rather than one blended figure, so "we planned 80 m and
    expected to waste 4" stays answerable after the fact. Phase 3B's convention
    holds: base is net consumption, planned issue is base x (1 + scrap%).
    """

    __tablename__ = "production_order_materials"
    __table_args__ = (
        Index("ix_pom_order_sequence", "production_order_id", "sequence"),
        Index("ix_pom_item", "item_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    production_order_id: Mapped[int] = mapped_column(
        ForeignKey("production_orders.id"), index=True
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    # Provenance back to the recipe line, for the "why do I need 45 m?" trace.
    bom_component_id: Mapped[int | None] = mapped_column(
        ForeignKey("bom_components.id"), default=None
    )

    # Per one unit of the parent, straight off the BOM - kept so the explanation
    # can be reconstructed without re-exploding.
    quantity_per_unit: Mapped[Decimal] = mapped_column(QuantityType, default=Decimal("0"))
    base_quantity: Mapped[Decimal] = mapped_column(QuantityType)
    scrap_pct: Mapped[Decimal] = mapped_column(ScrapType, default=Decimal("0"))
    planned_quantity: Mapped[Decimal] = mapped_column(QuantityType)
    uom_id: Mapped[int] = mapped_column(ForeignKey("units_of_measure.id"))

    # Depth in the BOM tree, and which parent pulled this material in. Together
    # they reconstruct the full path for multi-level orders.
    level: Mapped[int] = mapped_column(Integer, default=0)
    parent_item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"), default=None)

    is_optional: Mapped[bool] = mapped_column(Boolean, default=False)
    # A sub-assembly line is shown for visibility but excluded from material
    # totals - its own children are already in the list, and counting both would
    # double-count.
    is_subassembly: Mapped[bool] = mapped_column(Boolean, default=False)
    sequence: Mapped[int] = mapped_column(Integer, default=0)

    # ---- Phase 3D aggregate cache -------------------------------------------
    # These four mirror the sum of the immutable transaction rows in
    # stock_reservations / production_material_{issues,consumptions,returns}.
    # They are maintained in the same transaction and under the same row lock as
    # the transactions themselves - the same relationship stock_levels has with
    # stock_movements. Validation reads them under lock; a test asserts they
    # equal the sum of their transactions.
    reserved_quantity: Mapped[Decimal] = mapped_column(QuantityType, default=Decimal("0"))
    issued_quantity: Mapped[Decimal] = mapped_column(QuantityType, default=Decimal("0"))
    consumed_quantity: Mapped[Decimal] = mapped_column(QuantityType, default=Decimal("0"))
    returned_quantity: Mapped[Decimal] = mapped_column(QuantityType, default=Decimal("0"))
    # Phase 3G. Material that was issued and will never become product -
    # distinct from consumed (which did become product) so planned-vs-actual
    # variance stays meaningful.
    wasted_quantity: Mapped[Decimal] = mapped_column(QuantityType, default=Decimal("0"))

    production_order: Mapped["ProductionOrder"] = relationship(back_populates="materials")
    item: Mapped["Item"] = relationship(foreign_keys=[item_id])  # noqa: F821
    parent_item: Mapped["Item | None"] = relationship(foreign_keys=[parent_item_id])  # noqa: F821
    uom: Mapped["UnitOfMeasure"] = relationship()  # noqa: F821

    @property
    def expected_wastage(self) -> Decimal:
        return self.planned_quantity - self.base_quantity

    # ---- Phase 3D derived positions -----------------------------------------

    @property
    def remaining_to_reserve(self) -> Decimal:
        return max(self.planned_quantity - self.reserved_quantity, Decimal("0"))

    @property
    def remaining_to_issue(self) -> Decimal:
        return max(self.planned_quantity - self.issued_quantity, Decimal("0"))

    @property
    def accounted_quantity(self) -> Decimal:
        """Everything issued whose fate is known: used, wasted or handed back."""
        return self.consumed_quantity + self.returned_quantity + self.wasted_quantity

    @property
    def returnable_quantity(self) -> Decimal:
        """What could still legitimately come back from the floor.

        Bounded by every rule at once: a return cannot exceed what was issued,
        less what already came back, less what was consumed, less what was
        scrapped. Material that was wasted is gone - it cannot also be returned.
        """
        return max(self.issued_quantity - self.accounted_quantity, Decimal("0"))

    @property
    def still_with_production(self) -> Decimal:
        """Issued, but not yet used, wasted or handed back - on the floor.

        Made explicit rather than left implied: at the end of a run this is the
        number that tells the boutique what is sitting in a tailor's tray.
        """
        return self.issued_quantity - self.accounted_quantity
