"""Quality control, rework and production wastage.

QC AND REWORK

A failed check does **not** spawn a duplicate production order. Rework is tracked
against the original order, because the boutique needs "this order took two
passes at stitching" to stay one order - splitting it would double the apparent
output and lose the link between the fault and the run that caused it.

WASTAGE

Wastage is recorded separately from consumption, even though both describe
material that will not come back. Consumption is material that ended up in the
garment; wastage is material that did not. Collapsing them would make the
planned-versus-actual variance meaningless, which is the one number that tells a
boutique whether its BOM is honest.

Wastage does not move stock on its own: the material already left inventory when
it was issued. What wastage adds is the *reason* it never came back, and the cost
attribution Phase 3H reads.
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
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.inventory import QuantityType
from app.models.mixins import TenantMixin, TimestampMixin


class QcResult(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"


class ReworkStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


class DefectCategory(Base, TimestampMixin, TenantMixin):
    """Configurable defect reasons.

    A table rather than an enum so a boutique can add "zip misaligned" without a
    release - and so the rework report can group by something stable instead of
    free text that everyone spells differently.
    """

    __tablename__ = "defect_categories"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_defect_category_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class WastageReason(Base, TimestampMixin, TenantMixin):
    """Configurable wastage reasons, for the same reason defects are."""

    __tablename__ = "wastage_reasons"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_wastage_reason_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class QualityCheck(Base, TimestampMixin, TenantMixin):
    """One inspection of a production order, optionally of a specific work order."""

    __tablename__ = "quality_checks"
    __table_args__ = (
        Index("ix_qc_order", "production_order_id"),
        Index("ix_qc_result", "tenant_id", "result"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    production_order_id: Mapped[int] = mapped_column(ForeignKey("production_orders.id"), index=True)
    work_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("work_orders.id"), default=None, index=True
    )

    result: Mapped[QcResult] = mapped_column(Enum(QcResult), index=True)
    checked_quantity: Mapped[Decimal] = mapped_column(QuantityType, default=Decimal("0"))
    passed_quantity: Mapped[Decimal] = mapped_column(QuantityType, default=Decimal("0"))
    failed_quantity: Mapped[Decimal] = mapped_column(QuantityType, default=Decimal("0"))

    notes: Mapped[str | None] = mapped_column(Text, default=None)
    # Path under /uploads, same convention as product images. Optional - a phone
    # photo of a fault is the most useful evidence a boutique actually captures.
    photo_path: Mapped[str | None] = mapped_column(String(300), default=None)

    inspector_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    production_order: Mapped["ProductionOrder"] = relationship()  # noqa: F821
    work_order: Mapped["WorkOrder | None"] = relationship()  # noqa: F821
    defects: Mapped[list["QualityDefect"]] = relationship(
        back_populates="quality_check", cascade="all, delete-orphan"
    )


class QualityDefect(Base, TimestampMixin, TenantMixin):
    """A specific fault found by a check, categorised so it can be reported on."""

    __tablename__ = "quality_defects"

    id: Mapped[int] = mapped_column(primary_key=True)
    quality_check_id: Mapped[int] = mapped_column(ForeignKey("quality_checks.id"), index=True)
    defect_category_id: Mapped[int] = mapped_column(ForeignKey("defect_categories.id"))
    quantity: Mapped[Decimal] = mapped_column(QuantityType, default=Decimal("0"))
    notes: Mapped[str | None] = mapped_column(String(500), default=None)

    quality_check: Mapped["QualityCheck"] = relationship(back_populates="defects")
    category: Mapped["DefectCategory"] = relationship()


class ReworkOrder(Base, TimestampMixin, TenantMixin):
    """Corrective work against the original production order.

    Deliberately not a new production order: the fault and the run that caused it
    stay linked, and output is not double-counted.
    """

    __tablename__ = "rework_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "rework_number", name="uq_rework_tenant_number"),
        Index("ix_rework_order", "production_order_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    rework_number: Mapped[str] = mapped_column(String(30), index=True)
    production_order_id: Mapped[int] = mapped_column(ForeignKey("production_orders.id"), index=True)
    quality_check_id: Mapped[int | None] = mapped_column(
        ForeignKey("quality_checks.id"), default=None
    )
    # The work order re-opened to fix it, when the fix belongs to a stage.
    work_order_id: Mapped[int | None] = mapped_column(ForeignKey("work_orders.id"), default=None)
    assigned_tailor_id: Mapped[int | None] = mapped_column(ForeignKey("tailors.id"), default=None)

    quantity: Mapped[Decimal] = mapped_column(QuantityType)
    reason: Mapped[str] = mapped_column(String(500))
    status: Mapped[ReworkStatus] = mapped_column(
        Enum(ReworkStatus), default=ReworkStatus.OPEN, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)

    production_order: Mapped["ProductionOrder"] = relationship()  # noqa: F821
    quality_check: Mapped["QualityCheck | None"] = relationship()
    tailor: Mapped["Tailor | None"] = relationship()  # noqa: F821


class ProductionWastage(Base, TimestampMixin, TenantMixin):
    """Material that was issued but will never become product.

    Recorded against the production order, the material, and - where it is known
    - the work order and tailor, so wastage is reportable by any of them.

    Writes no ledger row: the stock left at issue. This records where it went and
    why, and feeds the cost of waste in Phase 3H.
    """

    __tablename__ = "production_wastage"
    __table_args__ = (
        Index("ix_wastage_order", "production_order_id"),
        Index("ix_wastage_item", "item_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    production_order_id: Mapped[int] = mapped_column(ForeignKey("production_orders.id"), index=True)
    production_order_material_id: Mapped[int] = mapped_column(
        ForeignKey("production_order_materials.id"), index=True
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    work_order_id: Mapped[int | None] = mapped_column(ForeignKey("work_orders.id"), default=None)
    tailor_id: Mapped[int | None] = mapped_column(ForeignKey("tailors.id"), default=None, index=True)

    quantity: Mapped[Decimal] = mapped_column(QuantityType)
    uom_id: Mapped[int] = mapped_column(ForeignKey("units_of_measure.id"))
    reason_id: Mapped[int | None] = mapped_column(ForeignKey("wastage_reasons.id"), default=None)
    notes: Mapped[str | None] = mapped_column(String(500), default=None)
    recorded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)

    item: Mapped["Item"] = relationship()  # noqa: F821
    uom: Mapped["UnitOfMeasure"] = relationship()  # noqa: F821
    reason: Mapped["WastageReason | None"] = relationship()
    tailor: Mapped["Tailor | None"] = relationship()  # noqa: F821
