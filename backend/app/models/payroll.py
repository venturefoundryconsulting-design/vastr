import enum

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TenantMixin, TimestampMixin


class PayslipStatus(str, enum.Enum):
    DRAFT = "draft"
    PAID = "paid"


class StaffSalary(Base, TimestampMixin, TenantMixin):
    """Current monthly base salary per staff member - admin-configured. Payslips are
    generated from this figure but can be adjusted per-month without changing it."""

    __tablename__ = "staff_salaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    monthly_salary: Mapped[float] = mapped_column(Numeric(10, 2))
    notes: Mapped[str | None] = mapped_column(String(300), default=None)

    staff: Mapped["User"] = relationship()  # noqa: F821


class Payslip(Base, TimestampMixin, TenantMixin):
    """One row per staff member per month, generated from StaffSalary at the time of
    generation. Allowances/deductions are editable after generation; net_amount is
    recomputed whenever they change."""

    __tablename__ = "payslips"
    __table_args__ = (UniqueConstraint("tenant_id", "staff_id", "month", name="uq_payslip_staff_month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    month: Mapped[str] = mapped_column(String(7))  # "YYYY-MM"
    basic_amount: Mapped[float] = mapped_column(Numeric(10, 2))
    allowances: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    deductions: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    net_amount: Mapped[float] = mapped_column(Numeric(10, 2))
    status: Mapped[PayslipStatus] = mapped_column(Enum(PayslipStatus), default=PayslipStatus.DRAFT)
    paid_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), default=None)

    staff: Mapped["User"] = relationship()  # noqa: F821
