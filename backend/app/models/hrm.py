import enum

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin


class AttendanceStatus(str, enum.Enum):
    PRESENT = "present"
    ABSENT = "absent"
    HALF_DAY = "half_day"
    ON_LEAVE = "on_leave"


class Attendance(Base, TimestampMixin):
    """One row per staff member per calendar day. Staff self-check-in/out; admin/manager
    can add manual corrections (e.g. marking a no-show absent, fixing a missed check-out)."""

    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("staff_id", "date", name="uq_attendance_staff_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    outlet_id: Mapped[int | None] = mapped_column(ForeignKey("outlets.id"), default=None)
    date: Mapped[Date] = mapped_column(Date)
    check_in_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), default=None)
    check_out_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), default=None)
    status: Mapped[AttendanceStatus] = mapped_column(Enum(AttendanceStatus), default=AttendanceStatus.PRESENT)
    notes: Mapped[str | None] = mapped_column(String(300), default=None)

    staff: Mapped["User"] = relationship(foreign_keys=[staff_id])  # noqa: F821
    outlet: Mapped["Outlet | None"] = relationship()  # noqa: F821


class LeaveType(str, enum.Enum):
    SICK = "sick"
    CASUAL = "casual"
    UNPAID = "unpaid"
    OTHER = "other"


class LeaveStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class LeaveRequest(Base, TimestampMixin):
    __tablename__ = "leave_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    leave_type: Mapped[LeaveType] = mapped_column(Enum(LeaveType))
    start_date: Mapped[Date] = mapped_column(Date)
    end_date: Mapped[Date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(String(500), default=None)
    status: Mapped[LeaveStatus] = mapped_column(Enum(LeaveStatus), default=LeaveStatus.PENDING)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    reviewed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), default=None)
    review_note: Mapped[str | None] = mapped_column(String(300), default=None)

    staff: Mapped["User"] = relationship(foreign_keys=[staff_id])  # noqa: F821
    reviewed_by: Mapped["User | None"] = relationship(foreign_keys=[reviewed_by_id])  # noqa: F821
