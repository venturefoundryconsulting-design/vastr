import enum
from decimal import Decimal

from sqlalchemy import Enum, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TenantMixin, TimestampMixin

# Every stock quantity in the system uses this type. 4 decimal places covers the
# manufacturing cases that motivated it (4.5 m of fabric, 0.125 kg of beads,
# 200.75 g of thread) with room to spare; 14 total digits leaves 10 for the
# integer part, far beyond any real boutique stock level. Numeric - never Float -
# because inventory and money must not accumulate binary rounding error.
QUANTITY_PRECISION = 14
QUANTITY_SCALE = 4
QuantityType = Numeric(QUANTITY_PRECISION, QUANTITY_SCALE)


class StockLevel(Base, TimestampMixin, TenantMixin):
    """Current on-hand quantity of a variant at an outlet/warehouse."""

    __tablename__ = "stock_levels"
    __table_args__ = (
        UniqueConstraint("tenant_id", "variant_id", "outlet_id", name="uq_stock_variant_outlet"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"))
    quantity: Mapped[Decimal] = mapped_column(QuantityType, default=Decimal("0"))

    variant: Mapped["Item"] = relationship(back_populates="stock_levels")  # noqa: F821
    outlet: Mapped["Outlet"] = relationship(back_populates="stock_levels")  # noqa: F821


class MovementType(str, enum.Enum):
    PURCHASE_RECEIPT = "purchase_receipt"
    SALE = "sale"
    TRANSFER_OUT = "transfer_out"
    TRANSFER_IN = "transfer_in"
    ADJUSTMENT = "adjustment"
    RETURN = "return"
    # The balance a stock level started life with, before any transaction. Added
    # in Phase 3A: opening balances used to be written straight onto
    # stock_levels.quantity (see app/seed.py), which left the ledger unable to
    # explain the difference. Every opening balance is now a movement, so
    # replaying stock_movements reproduces stock_levels exactly - the invariant
    # the whole manufacturing phase depends on.
    OPENING_STOCK = "opening_stock"
    # Phase 3D. Material physically leaving the store for a production order,
    # and unused material coming back. Consumption is deliberately NOT a movement
    # type: the stock already left at issue, and deducting again would double-count.
    PRODUCTION_ISSUE = "production_issue"
    PRODUCTION_RETURN = "production_return"
    # Phase 3E. The manufactured item arriving in stock - the mirror of
    # PRODUCTION_ISSUE, and the only way finished goods are created.
    PRODUCTION_OUTPUT = "production_output"
    # Phase 5. Goods sent back to a vendor - a compensating movement against a
    # receipt, never an edit of it. Distinct from RETURN, which is a customer
    # returning a sale.
    PURCHASE_RETURN = "purchase_return"


class StockMovement(Base, TimestampMixin, TenantMixin):
    """Immutable audit trail of every stock quantity change."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        # Every ledger reconciliation, availability check and movements list
        # groups or filters on exactly this triple - see RECONCILE_SQL in
        # tests/test_ledger_integrity.py and list_movements() in
        # routers/inventory.py. Never indexed before Phase 10; at 100k+ rows
        # each of those was a sequential scan.
        Index("ix_stock_movements_tenant_variant_outlet", "tenant_id", "variant_id", "outlet_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"))
    movement_type: Mapped[MovementType] = mapped_column(Enum(MovementType))
    # positive = stock in, negative = stock out
    quantity_delta: Mapped[Decimal] = mapped_column(QuantityType)
    reference_type: Mapped[str | None] = mapped_column(String(40), default=None)
    reference_id: Mapped[int | None] = mapped_column(Integer, default=None)
    note: Mapped[str | None] = mapped_column(String(255), default=None)
    # Cost per stock unit at the moment this movement happened. Written on
    # receipts and returns; null elsewhere. Costs nothing to carry now and is the
    # only thing that would make FIFO addable later without rebuilding history
    # from invoices.
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), default=None)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)

    variant: Mapped["Item"] = relationship()  # noqa: F821
    outlet: Mapped["Outlet"] = relationship()  # noqa: F821
