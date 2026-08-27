"""Finished and semi-finished output from a production order.

Output is the mirror of issue: issue takes raw material out of stock, output puts
the manufactured thing in. Both write immutable ledger rows through the same
``apply_stock_delta`` chokepoint, so a garment appearing in inventory is as
explainable as the fabric that left.

PARTIAL PRODUCTION

An order for 10 that yields 6 does **not** close. It moves to
PARTIALLY_COMPLETED and keeps ordered / produced / remaining answerable, because
"we stopped at 6" is a decision someone has to make deliberately - via close
short, which records who and why (see Phase 3C).

Reaching the planned quantity is different: nothing is being abandoned, so
completing is not a judgement call and the order closes on its own. The rule the
brief protects is "never silently close *short*", and that still holds.
"""

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.inventory import QuantityType
from app.models.mixins import TenantMixin, TimestampMixin


class ProductionOutput(Base, TimestampMixin, TenantMixin):
    """One delivery of finished goods from a production order into stock.

    Recorded per event rather than as a running total, so a run that yields 3 on
    Monday and 3 on Wednesday keeps both dates. Immutable: a mistake is corrected
    by a stock adjustment, never by editing the row that already moved inventory.
    """

    __tablename__ = "production_outputs"
    __table_args__ = (
        Index("ix_production_outputs_order", "production_order_id"),
        Index("ix_production_outputs_item", "item_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    production_order_id: Mapped[int] = mapped_column(ForeignKey("production_orders.id"), index=True)
    # Normally the order's own item. Kept explicit so a future by-product or
    # co-product does not need a schema change to be recorded.
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"))

    quantity: Mapped[Decimal] = mapped_column(QuantityType)
    uom_id: Mapped[int | None] = mapped_column(ForeignKey("units_of_measure.id"), default=None)
    # The ledger row this output created - the tie between the garment in stock
    # and the order that made it.
    stock_movement_id: Mapped[int | None] = mapped_column(
        ForeignKey("stock_movements.id"), default=None
    )

    note: Mapped[str | None] = mapped_column(String(500), default=None)
    produced_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)

    production_order: Mapped["ProductionOrder"] = relationship()  # noqa: F821
    item: Mapped["Item"] = relationship()  # noqa: F821
    uom: Mapped["UnitOfMeasure | None"] = relationship()  # noqa: F821
