from datetime import date, datetime

from pydantic import BaseModel

from app.models.hrm import AttendanceStatus, LeaveStatus, LeaveType


class StaffOut(BaseModel):
    id: int
    name: str
    role: str
    outlet_id: int | None = None
    outlet_name: str | None = None

    model_config = {"from_attributes": True}


class AttendanceOut(BaseModel):
    id: int
    staff_id: int
    staff_name: str | None = None
    outlet_id: int | None = None
    outlet_name: str | None = None
    date: date
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None
    status: AttendanceStatus
    notes: str | None = None

    model_config = {"from_attributes": True}


class AttendanceUpdate(BaseModel):
    status: AttendanceStatus | None = None
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None
    notes: str | None = None


class LeaveRequestCreate(BaseModel):
    leave_type: LeaveType
    start_date: date
    end_date: date
    reason: str | None = None


class LeaveRequestOut(BaseModel):
    id: int
    staff_id: int
    staff_name: str | None = None
    leave_type: LeaveType
    start_date: date
    end_date: date
    reason: str | None = None
    status: LeaveStatus
    reviewed_by_id: int | None = None
    reviewed_by_name: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LeaveReview(BaseModel):
    status: LeaveStatus
    review_note: str | None = None
