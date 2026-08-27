"""Tailors, production stages and work orders.

TAILORS ARE RESOURCES, NOT INVENTORY LOCATIONS. This is the architectural
decision recorded in Phase 3A and it holds here: a work order attributes labour
and responsibility to a person, but material custody stays with the production
order (see app.models.material_flow). No stock ever sits "at" a tailor, so there
are no fake transfers between tailor locations to reconcile.

``user_id`` is nullable because most boutique tailors are contracted and have no
login - the existing ``alterations`` table already models them that way. A tailor
who does have an account can see and drive their own work orders, and nothing else.

STAGES ARE DATA, NOT CODE. The default nine (Design ... Completed) are seeded by
migration, not hard-coded in a branch anywhere, so a boutique can add "Beading"
or drop "Handwork" from the admin UI without a release.
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
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.inventory import QuantityType
from app.models.mixins import TenantMixin, TimestampMixin


class PayModel(str, enum.Enum):
    """How a tailor is paid for a piece of work.

    Stored per tailor as a default and copied onto the work order at assignment,
    so changing someone's rate never rewrites what past work cost.
    """

    PER_GARMENT = "per_garment"
    PER_STAGE = "per_stage"
    PER_PIECE = "per_piece"
    HOURLY = "hourly"
    FIXED = "fixed"


class WorkOrderStatus(str, enum.Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    REWORK = "rework"
    CANCELLED = "cancelled"


WO_TERMINAL = {WorkOrderStatus.COMPLETED, WorkOrderStatus.CANCELLED}

# Enforced server-side, exactly like the production order machine. A work order
# never has its status assigned directly.
WO_TRANSITIONS: dict[WorkOrderStatus, set[WorkOrderStatus]] = {
    WorkOrderStatus.PENDING: {WorkOrderStatus.ASSIGNED, WorkOrderStatus.CANCELLED},
    WorkOrderStatus.ASSIGNED: {
        WorkOrderStatus.IN_PROGRESS,
        WorkOrderStatus.PENDING,  # unassign
        WorkOrderStatus.CANCELLED,
    },
    WorkOrderStatus.IN_PROGRESS: {
        WorkOrderStatus.PAUSED,
        WorkOrderStatus.COMPLETED,
        WorkOrderStatus.CANCELLED,
    },
    WorkOrderStatus.PAUSED: {WorkOrderStatus.IN_PROGRESS, WorkOrderStatus.CANCELLED},
    # Rework re-opens finished work; QC in Phase 3G is what puts it here.
    WorkOrderStatus.COMPLETED: {WorkOrderStatus.REWORK},
    WorkOrderStatus.REWORK: {WorkOrderStatus.IN_PROGRESS, WorkOrderStatus.CANCELLED},
    WorkOrderStatus.CANCELLED: set(),
}


class Tailor(Base, TimestampMixin, TenantMixin):
    __tablename__ = "tailors"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_tailor_tenant_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), index=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(20), default=None)
    # Optional login. Contracted tailors typically have none; one who does gets
    # access to their own work queue only.
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None, index=True)

    pay_model: Mapped[PayModel] = mapped_column(Enum(PayModel), default=PayModel.PER_STAGE)
    default_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    joined_on: Mapped[date | None] = mapped_column(Date, default=None)
    notes: Mapped[str | None] = mapped_column(String(1000), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    skills: Mapped[list["TailorSkill"]] = relationship(
        back_populates="tailor", cascade="all, delete-orphan"
    )


class TailorSkill(Base, TimestampMixin, TenantMixin):
    """What a tailor is qualified for, tied to a stage where it maps to one.

    ``stage_id`` is nullable so a free-text speciality ("hand embroidery") can be
    recorded before anyone models it as a stage.
    """

    __tablename__ = "tailor_skills"
    __table_args__ = (
        UniqueConstraint("tenant_id", "tailor_id", "name", name="uq_tailor_skill_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tailor_id: Mapped[int] = mapped_column(ForeignKey("tailors.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    stage_id: Mapped[int | None] = mapped_column(ForeignKey("production_stages.id"), default=None)
    # 1-5, so assignment can prefer the person who is actually good at it.
    proficiency: Mapped[int] = mapped_column(Integer, default=3)

    tailor: Mapped["Tailor"] = relationship(back_populates="skills")
    stage: Mapped["ProductionStage | None"] = relationship()


class ProductionStage(Base, TimestampMixin, TenantMixin):
    """A step a garment passes through. Configurable data, never a code branch."""

    __tablename__ = "production_stages"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_production_stage_tenant_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(80))
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    # The rate paid for this stage when the tailor's model is PER_STAGE and they
    # have no rate of their own.
    default_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    # Marks the stage that hands off to quality control (Phase 3G).
    is_qc: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class WorkOrder(Base, TimestampMixin, TenantMixin):
    """One stage of one production order, assigned to one tailor.

    A production order fans out into several of these - cutting, stitching,
    embroidery, finishing - and each carries its own quantity, dates and rate.
    """

    __tablename__ = "work_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "wo_number", name="uq_work_order_tenant_number"),
        Index("ix_work_orders_tenant_status", "tenant_id", "status"),
        Index("ix_work_orders_tailor_status", "tailor_id", "status"),
        Index("ix_work_orders_order", "production_order_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    wo_number: Mapped[str] = mapped_column(String(30), index=True)
    production_order_id: Mapped[int] = mapped_column(ForeignKey("production_orders.id"), index=True)
    stage_id: Mapped[int] = mapped_column(ForeignKey("production_stages.id"), index=True)
    tailor_id: Mapped[int | None] = mapped_column(ForeignKey("tailors.id"), default=None, index=True)

    quantity: Mapped[Decimal] = mapped_column(QuantityType)
    completed_quantity: Mapped[Decimal] = mapped_column(QuantityType, default=Decimal("0"))

    status: Mapped[WorkOrderStatus] = mapped_column(
        Enum(WorkOrderStatus), default=WorkOrderStatus.PENDING, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, default=0)

    due_date: Mapped[date | None] = mapped_column(Date, default=None)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    # Copied from the tailor/stage at assignment so a later rate change never
    # rewrites the cost of work already done. Phase 3H reads these.
    pay_model: Mapped[PayModel | None] = mapped_column(Enum(PayModel), default=None)
    rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)

    notes: Mapped[str | None] = mapped_column(String(1000), default=None)
    issue_note: Mapped[str | None] = mapped_column(String(1000), default=None)
    assigned_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)

    production_order: Mapped["ProductionOrder"] = relationship()  # noqa: F821
    stage: Mapped["ProductionStage"] = relationship()
    tailor: Mapped["Tailor | None"] = relationship()

    @property
    def is_overdue(self) -> bool:
        if not self.due_date or self.status in WO_TERMINAL:
            return False
        return self.due_date < date.today()

    @property
    def labour_cost(self) -> Decimal:
        """What this work order costs, by the pay model captured at assignment.

        Computed rather than stored so it always reflects the completed quantity;
        the inputs (rate, model) are frozen, which is what matters.
        """
        rate = Decimal(self.rate or 0)
        if self.pay_model == PayModel.HOURLY:
            return rate * Decimal(self.hours or 0)
        if self.pay_model == PayModel.FIXED:
            return rate
        # per garment / per stage / per piece all scale with what was completed.
        return rate * Decimal(self.completed_quantity or 0)
