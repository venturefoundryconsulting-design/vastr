"""Phase 9 - AI-assisted invoice import.

STAGING, NEVER DIRECT WRITE. Extraction lands here, in ``ai_import_rows``, with
a confidence score per field. Nothing here is master data and nothing here
moves stock - approving a batch creates a DRAFT GoodsReceipt (see
app.services.ai_import.approve_batch), which still needs its own explicit
"post" before app.services.goods_receipt touches inventory. Two human gates,
not one: a person reviews what the model read off the invoice, and a
different (or the same) person still decides when stock actually arrives.

This mirrors the pattern every other manufacturing phase established for
anything irreversible - draft first, explicit human action to commit - rather
than inventing a new one for AI specifically.
"""

import enum
from decimal import Decimal

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.inventory import QuantityType
from app.models.mixins import TenantMixin, TimestampMixin

# 0.00 - 1.00. Small scale because it is a confidence, never a real quantity.
ConfidenceType = Numeric(3, 2)


class AiImportStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class AiImportBatch(Base, TimestampMixin, TenantMixin):
    """One uploaded invoice/photo and everything the model read off it."""

    __tablename__ = "ai_import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"), index=True)
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"), default=None, index=True)
    source_filename: Mapped[str] = mapped_column(String(255))
    source_path: Mapped[str] = mapped_column(String(500))

    status: Mapped[AiImportStatus] = mapped_column(
        Enum(AiImportStatus), default=AiImportStatus.PENDING, index=True
    )
    # The model's raw JSON response, kept verbatim for audit and for debugging
    # a bad extraction - never parsed back out of this at read time, the rows
    # below are the parsed/structured form.
    raw_extraction: Mapped[str | None] = mapped_column(Text, default=None)
    vendor_name_guess: Mapped[str | None] = mapped_column(String(150), default=None)
    invoice_ref_guess: Mapped[str | None] = mapped_column(String(80), default=None)

    # Set once approved - the draft this batch turned into. Never posted by
    # this module; posting is still an explicit act in Goods Receipts.
    goods_receipt_id: Mapped[int | None] = mapped_column(
        ForeignKey("goods_receipts.id"), default=None
    )

    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    notes: Mapped[str | None] = mapped_column(String(1000), default=None)

    outlet: Mapped["Outlet"] = relationship()  # noqa: F821
    vendor: Mapped["Vendor | None"] = relationship()  # noqa: F821
    rows: Mapped[list["AiImportRow"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan", order_by="AiImportRow.line_no"
    )


class AiImportRow(Base, TimestampMixin, TenantMixin):
    """One extracted invoice line - a proposal, until the batch is approved.

    ``matched_item_id`` is Phase 9's duplicate-detection: a simple name/SKU
    match against the existing item master, run once at extraction time and
    always overridable by a human before approval. No match means the row
    proposes a brand-new raw material, created only on approval - never
    silently, and never before a person has seen the description the model
    matched it from.
    """

    __tablename__ = "ai_import_rows"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("ai_import_batches.id"), index=True)
    line_no: Mapped[int] = mapped_column(Integer, default=0)

    raw_description: Mapped[str] = mapped_column(String(300))
    raw_unit_text: Mapped[str | None] = mapped_column(String(40), default=None)

    matched_item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"), default=None)
    is_new_item: Mapped[bool] = mapped_column(Boolean, default=False)
    proposed_sku: Mapped[str | None] = mapped_column(String(64), default=None)

    quantity: Mapped[Decimal] = mapped_column(QuantityType, default=Decimal("0"))
    uom_id: Mapped[int | None] = mapped_column(ForeignKey("units_of_measure.id"), default=None)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))

    description_confidence: Mapped[Decimal | None] = mapped_column(ConfidenceType, default=None)
    quantity_confidence: Mapped[Decimal | None] = mapped_column(ConfidenceType, default=None)
    cost_confidence: Mapped[Decimal | None] = mapped_column(ConfidenceType, default=None)
    match_confidence: Mapped[Decimal | None] = mapped_column(ConfidenceType, default=None)

    # A human unchecked this line - excluded from approval, kept for the record
    # rather than deleted, so the batch still shows everything the model read.
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)

    batch: Mapped["AiImportBatch"] = relationship(back_populates="rows")
    matched_item: Mapped["Item | None"] = relationship()  # noqa: F821
    uom: Mapped["UnitOfMeasure | None"] = relationship()  # noqa: F821
