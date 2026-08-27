"""Reservation, issue, consumption and return of production material.

FOUR QUANTITIES, FOUR MEANINGS. They are never collapsed:

  ON HAND   physical stock (stock_levels.quantity)
  RESERVED  committed to a production order, still physically present
  ISSUED    physically handed to production - stock has left the store
  CONSUMED  actually used up in manufacturing

Only ISSUE and RETURN move physical stock. Reservation is a promise, not a
movement. Consumption records what happened to material that already left at
issue time, so it must not deduct stock a second time.

WHERE TRUTH LIVES

The three transaction tables (issues, consumptions, returns) are the immutable
history - nothing edits or deletes a row once written; a mistake is corrected by
a compensating row. The aggregate columns on ProductionOrderMaterial
(reserved/issued/consumed/returned) are a *cache* over those rows, maintained in
the same transaction and under the same lock, exactly as stock_levels caches
stock_movements. A test asserts the cache equals the sum of its transactions,
and that is the invariant to fix if it ever fails - not the assertion.

THE INVARIANTS

  reserved  <= available_at_location            (enforced under row lock)
  issued    <= reserved                         (unless materials.issue_unreserved)
  issued    <= planned                          (no silent over-issue)
  consumed + returned <= issued                 (cannot use what you never had)
  returnable = issued - consumed - returned
  still_with_production = issued - consumed - returned
"""

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.inventory import QuantityType
from app.models.mixins import TenantMixin, TimestampMixin


class ReservationStatus(str, enum.Enum):
    ACTIVE = "active"
    PARTIALLY_ISSUED = "partially_issued"
    CONSUMED = "consumed"
    RELEASED = "released"
    CANCELLED = "cancelled"


# A reservation only holds stock while it is in one of these states; everything
# else is history. The availability query filters on exactly this set, so adding
# a status without deciding which side it falls on is a compile-time-ish error.
HOLDING_STATUSES = {ReservationStatus.ACTIVE, ReservationStatus.PARTIALLY_ISSUED}


class StockReservation(Base, TimestampMixin, TenantMixin):
    """A commitment against stock that has not physically moved.

    Deliberately a row rather than a counter on stock_levels: a counter cannot be
    aged, released selectively, attributed to an order, or explained to the person
    asking why they cannot have the lace. Releasing is a status change, which
    keeps the history intact.

    Reservations hang off the Phase 3C *snapshot* line, never off the live BOM -
    so a BOM edited tomorrow cannot retroactively change what this order holds.
    """

    __tablename__ = "stock_reservations"
    __table_args__ = (
        Index("ix_reservation_item_location_status", "item_id", "location_id", "status"),
        Index("ix_reservation_order", "production_order_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    production_order_id: Mapped[int] = mapped_column(ForeignKey("production_orders.id"), index=True)
    production_order_material_id: Mapped[int] = mapped_column(
        ForeignKey("production_order_materials.id"), index=True
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"), index=True)

    quantity: Mapped[Decimal] = mapped_column(QuantityType)
    # How much of this reservation has already been drawn down by issues. The
    # reservation stops holding stock for the issued portion - that stock has
    # physically gone, so continuing to reserve it would double-count.
    issued_quantity: Mapped[Decimal] = mapped_column(QuantityType, default=Decimal("0"))
    uom_id: Mapped[int] = mapped_column(ForeignKey("units_of_measure.id"))

    status: Mapped[ReservationStatus] = mapped_column(
        Enum(ReservationStatus), default=ReservationStatus.ACTIVE, index=True
    )
    note: Mapped[str | None] = mapped_column(String(500), default=None)

    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    released_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    release_reason: Mapped[str | None] = mapped_column(String(500), default=None)

    production_order: Mapped["ProductionOrder"] = relationship()  # noqa: F821
    material: Mapped["ProductionOrderMaterial"] = relationship()  # noqa: F821
    item: Mapped["Item"] = relationship()  # noqa: F821
    uom: Mapped["UnitOfMeasure"] = relationship()  # noqa: F821

    @property
    def outstanding(self) -> Decimal:
        """Quantity still being held - i.e. reserved but not yet issued."""
        if self.status not in HOLDING_STATUSES:
            return Decimal("0")
        return self.quantity - self.issued_quantity


class ProductionMaterialIssue(Base, TimestampMixin, TenantMixin):
    """Material physically handed to production. Immutable once written.

    Every row has exactly one matching stock_movements row of type
    PRODUCTION_ISSUE, created in the same transaction. A mistake is corrected
    with a return, never by editing or deleting this row.
    """

    __tablename__ = "production_material_issues"
    __table_args__ = (
        Index("ix_pmi_order_material", "production_order_id", "production_order_material_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    production_order_id: Mapped[int] = mapped_column(ForeignKey("production_orders.id"), index=True)
    production_order_material_id: Mapped[int] = mapped_column(
        ForeignKey("production_order_materials.id"), index=True
    )
    reservation_id: Mapped[int | None] = mapped_column(
        ForeignKey("stock_reservations.id"), default=None
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"))

    quantity: Mapped[Decimal] = mapped_column(QuantityType)
    uom_id: Mapped[int] = mapped_column(ForeignKey("units_of_measure.id"))
    # The ledger row this issue created, so the two can always be tied together.
    stock_movement_id: Mapped[int | None] = mapped_column(
        ForeignKey("stock_movements.id"), default=None
    )

    # Set when issued beyond what was reserved, which needs its own permission
    # and a stated reason. Null on an ordinary issue.
    unreserved_reason: Mapped[str | None] = mapped_column(String(500), default=None)
    note: Mapped[str | None] = mapped_column(String(500), default=None)
    issued_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)

    item: Mapped["Item"] = relationship()  # noqa: F821
    uom: Mapped["UnitOfMeasure"] = relationship()  # noqa: F821


class ProductionMaterialConsumption(Base, TimestampMixin, TenantMixin):
    """Material actually used up. Does NOT move stock.

    The stock left inventory at issue time. Recording consumption here is what
    lets planned-versus-actual be answered and what makes the leftover explicit;
    deducting stock again would be a double count.
    """

    __tablename__ = "production_material_consumptions"
    __table_args__ = (
        Index("ix_pmc_order_material", "production_order_id", "production_order_material_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    production_order_id: Mapped[int] = mapped_column(ForeignKey("production_orders.id"), index=True)
    production_order_material_id: Mapped[int] = mapped_column(
        ForeignKey("production_order_materials.id"), index=True
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)

    quantity: Mapped[Decimal] = mapped_column(QuantityType)
    uom_id: Mapped[int] = mapped_column(ForeignKey("units_of_measure.id"))

    # Recorded when actual consumption exceeds what was planned. Deliberately
    # does not touch the BOM or the snapshot - the variance is the signal.
    over_consumption_reason: Mapped[str | None] = mapped_column(String(500), default=None)
    note: Mapped[str | None] = mapped_column(String(500), default=None)
    recorded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)

    item: Mapped["Item"] = relationship()  # noqa: F821
    uom: Mapped["UnitOfMeasure"] = relationship()  # noqa: F821


class ProductionMaterialReturn(Base, TimestampMixin, TenantMixin):
    """Unused material coming back from production - a compensating movement.

    Writes a positive PRODUCTION_RETURN ledger row. The original issue is never
    edited: the pair of movements is the audit trail, and rewriting history would
    destroy it.
    """

    __tablename__ = "production_material_returns"
    __table_args__ = (
        Index("ix_pmr_order_material", "production_order_id", "production_order_material_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    production_order_id: Mapped[int] = mapped_column(ForeignKey("production_orders.id"), index=True)
    production_order_material_id: Mapped[int] = mapped_column(
        ForeignKey("production_order_materials.id"), index=True
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"))

    quantity: Mapped[Decimal] = mapped_column(QuantityType)
    uom_id: Mapped[int] = mapped_column(ForeignKey("units_of_measure.id"))
    stock_movement_id: Mapped[int | None] = mapped_column(
        ForeignKey("stock_movements.id"), default=None
    )

    reason: Mapped[str | None] = mapped_column(String(500), default=None)
    # False when the material comes back damaged and should not re-enter usable
    # stock. Phase 3G owns wastage proper; this flag is the hook.
    restock: Mapped[bool] = mapped_column(Boolean, default=True)
    returned_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)

    item: Mapped["Item"] = relationship()  # noqa: F821
    uom: Mapped["UnitOfMeasure"] = relationship()  # noqa: F821
