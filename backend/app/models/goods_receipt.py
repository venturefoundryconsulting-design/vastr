"""Goods receipts and purchase returns.

RULE 2, MADE AUDITABLE. "Only receiving increases inventory" was true before this
module but not *provable*: receiving was a quantity nudged onto
``purchase_order_items.quantity_received``, with no document, no date, no
receiver and no vendor invoice to point at. A goods receipt is now a real thing
that happened, at a time, to a person, against a supplier's paperwork.

TWO CAPABILITIES THIS UNLOCKS

**Units.** A vendor sells rolls; stock is kept in metres. The receipt converts
through the Phase 2 engine, so ordering 2 ROLL of a lace stocked in M puts 50 M
in the ledger. Before this, purchasing silently assumed the PO unit and the stock
unit were the same - fine for a boutique buying garments by the piece, wrong the
moment it buys fabric.

**Cost.** Weighted-average cost is recalculated on every receipt, and the unit
cost is written onto the ledger row itself. That second part costs nothing today
and is the only thing that makes FIFO addable later without a backfill.

RETURNS ARE COMPENSATING, NEVER EDITS. Sending goods back writes a negative
PURCHASE_RETURN movement referencing the receipt. The receipt stays exactly as
written, because the pair of rows is the audit trail.
"""

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.inventory import QuantityType
from app.models.mixins import TenantMixin, TimestampMixin


class ReceiptStatus(str, enum.Enum):
    DRAFT = "draft"
    POSTED = "posted"
    CANCELLED = "cancelled"


class GoodsReceipt(Base, TimestampMixin, TenantMixin):
    """One delivery arriving from a vendor.

    Posting is what moves stock. A draft receipt is a counted delivery note that
    nobody has committed yet; once posted it is immutable, and a mistake is
    corrected with a purchase return rather than an edit.
    """

    __tablename__ = "goods_receipts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "receipt_number", name="uq_goods_receipt_number"),
        Index("ix_goods_receipts_po", "purchase_order_id"),
        Index("ix_goods_receipts_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_number: Mapped[str] = mapped_column(String(30), index=True)
    purchase_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchase_orders.id"), default=None, index=True
    )
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"), default=None)
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"), index=True)

    receipt_date: Mapped[date | None] = mapped_column(Date, default=None)
    # The supplier's own paperwork, so a receipt can be tied back to an invoice
    # during a dispute without anyone searching through emails.
    vendor_invoice_ref: Mapped[str | None] = mapped_column(String(60), default=None)

    status: Mapped[ReceiptStatus] = mapped_column(
        Enum(ReceiptStatus), default=ReceiptStatus.DRAFT, index=True
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    notes: Mapped[str | None] = mapped_column(String(1000), default=None)
    received_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)

    purchase_order: Mapped["PurchaseOrder | None"] = relationship()  # noqa: F821
    vendor: Mapped["Vendor | None"] = relationship()  # noqa: F821
    outlet: Mapped["Outlet"] = relationship()  # noqa: F821
    items: Mapped[list["GoodsReceiptItem"]] = relationship(
        back_populates="receipt", cascade="all, delete-orphan", order_by="GoodsReceiptItem.id"
    )

    @property
    def total_cost(self) -> Decimal:
        return sum((i.line_cost for i in self.items), Decimal("0"))


class GoodsReceiptItem(Base, TimestampMixin, TenantMixin):
    """One line of a delivery.

    Quantity is recorded twice on purpose: as counted in the vendor's unit, and
    as it lands in stock. "We received 2 rolls" and "that is 50 metres" are both
    true and both worth keeping - the first is what the delivery note says, the
    second is what the ledger holds.
    """

    __tablename__ = "goods_receipt_items"
    __table_args__ = (Index("ix_goods_receipt_items_receipt", "goods_receipt_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    goods_receipt_id: Mapped[int] = mapped_column(ForeignKey("goods_receipts.id"), index=True)
    purchase_order_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchase_order_items.id"), default=None
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)

    # As counted, in the vendor's unit.
    quantity: Mapped[Decimal] = mapped_column(QuantityType)
    uom_id: Mapped[int | None] = mapped_column(ForeignKey("units_of_measure.id"), default=None)
    # As it enters the ledger, in the item's stock unit.
    quantity_in_stock_uom: Mapped[Decimal] = mapped_column(QuantityType)

    # Per vendor unit, matching `quantity` - the number on the invoice.
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    stock_movement_id: Mapped[int | None] = mapped_column(
        ForeignKey("stock_movements.id"), default=None
    )
    note: Mapped[str | None] = mapped_column(String(500), default=None)

    receipt: Mapped["GoodsReceipt"] = relationship(back_populates="items")
    item: Mapped["Item"] = relationship()  # noqa: F821
    uom: Mapped["UnitOfMeasure | None"] = relationship()  # noqa: F821

    @property
    def line_cost(self) -> Decimal:
        return Decimal(self.unit_cost or 0) * Decimal(self.quantity or 0)


class PurchaseReturn(Base, TimestampMixin, TenantMixin):
    """Goods sent back to a vendor - a compensating movement, never an edit."""

    __tablename__ = "purchase_returns"
    __table_args__ = (
        UniqueConstraint("tenant_id", "return_number", name="uq_purchase_return_number"),
        Index("ix_purchase_returns_receipt", "goods_receipt_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    return_number: Mapped[str] = mapped_column(String(30), index=True)
    goods_receipt_id: Mapped[int | None] = mapped_column(
        ForeignKey("goods_receipts.id"), default=None, index=True
    )
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"), default=None)
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"))

    return_date: Mapped[date | None] = mapped_column(Date, default=None)
    reason: Mapped[str | None] = mapped_column(String(500), default=None)
    notes: Mapped[str | None] = mapped_column(String(1000), default=None)
    returned_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)

    goods_receipt: Mapped["GoodsReceipt | None"] = relationship()
    vendor: Mapped["Vendor | None"] = relationship()  # noqa: F821
    items: Mapped[list["PurchaseReturnItem"]] = relationship(
        back_populates="purchase_return", cascade="all, delete-orphan"
    )

    @property
    def total_cost(self) -> Decimal:
        return sum((i.line_cost for i in self.items), Decimal("0"))


class PurchaseReturnItem(Base, TimestampMixin, TenantMixin):
    __tablename__ = "purchase_return_items"
    __table_args__ = (Index("ix_purchase_return_items_return", "purchase_return_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_return_id: Mapped[int] = mapped_column(ForeignKey("purchase_returns.id"), index=True)
    goods_receipt_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("goods_receipt_items.id"), default=None
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)

    # In the item's stock unit - what actually leaves the ledger.
    quantity: Mapped[Decimal] = mapped_column(QuantityType)
    uom_id: Mapped[int | None] = mapped_column(ForeignKey("units_of_measure.id"), default=None)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    stock_movement_id: Mapped[int | None] = mapped_column(
        ForeignKey("stock_movements.id"), default=None
    )

    purchase_return: Mapped["PurchaseReturn"] = relationship(back_populates="items")
    item: Mapped["Item"] = relationship()  # noqa: F821

    @property
    def line_cost(self) -> Decimal:
        return Decimal(self.unit_cost or 0) * Decimal(self.quantity or 0)
