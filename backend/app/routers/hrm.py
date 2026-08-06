from calendar import monthrange
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, get_db, require_manager_up
from app.models.hrm import Attendance, AttendanceStatus, LeaveRequest, LeaveStatus
from app.models.user import User
from app.schemas.hrm import (
    AttendanceOut,
    AttendanceUpdate,
    LeaveRequestCreate,
    LeaveRequestOut,
    LeaveReview,
    StaffOut,
)

router = APIRouter(prefix="/api/hrm", tags=["hrm"])


def _attendance_out(a: Attendance) -> AttendanceOut:
    return AttendanceOut(
        id=a.id,
        staff_id=a.staff_id,
        staff_name=a.staff.name if a.staff else None,
        outlet_id=a.outlet_id,
        outlet_name=a.outlet.name if a.outlet else None,
        date=a.date,
        check_in_at=a.check_in_at,
        check_out_at=a.check_out_at,
        status=a.status,
        notes=a.notes,
    )


def _leave_out(lr: LeaveRequest) -> LeaveRequestOut:
    return LeaveRequestOut(
        id=lr.id,
        staff_id=lr.staff_id,
        staff_name=lr.staff.name if lr.staff else None,
        leave_type=lr.leave_type,
        start_date=lr.start_date,
        end_date=lr.end_date,
        reason=lr.reason,
        status=lr.status,
        reviewed_by_id=lr.reviewed_by_id,
        reviewed_by_name=lr.reviewed_by.name if lr.reviewed_by else None,
        reviewed_at=lr.reviewed_at,
        review_note=lr.review_note,
        created_at=lr.created_at,
    )


@router.get("/staff", response_model=list[StaffOut], dependencies=[Depends(require_manager_up)])
def list_staff(db: Session = Depends(get_db)):
    users = db.query(User).options(joinedload(User.outlet)).filter(User.is_active.is_(True)).order_by(User.name).all()
    return [
        StaffOut(id=u.id, name=u.name, role=u.role.value, outlet_id=u.outlet_id, outlet_name=u.outlet.name if u.outlet else None)
        for u in users
    ]


# ---- Attendance ----


@router.post("/attendance/check-in", response_model=AttendanceOut)
def check_in(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    today = date.today()
    record = db.query(Attendance).filter(Attendance.staff_id == user.id, Attendance.date == today).first()
    if record and record.check_in_at:
        raise HTTPException(400, "Already checked in today")
    if not record:
        record = Attendance(staff_id=user.id, outlet_id=user.outlet_id, date=today)
        db.add(record)
    record.check_in_at = datetime.now(timezone.utc)
    record.status = AttendanceStatus.PRESENT
    db.commit()
    db.refresh(record)
    return _attendance_out(record)


@router.post("/attendance/check-out", response_model=AttendanceOut)
def check_out(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    today = date.today()
    record = db.query(Attendance).filter(Attendance.staff_id == user.id, Attendance.date == today).first()
    if not record or not record.check_in_at:
        raise HTTPException(400, "You haven't checked in today")
    if record.check_out_at:
        raise HTTPException(400, "Already checked out today")
    record.check_out_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(record)
    return _attendance_out(record)


@router.get("/attendance/me", response_model=list[AttendanceOut])
def my_attendance(days: int = 30, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cutoff = date.today() - timedelta(days=days)
    records = (
        db.query(Attendance)
        .options(joinedload(Attendance.staff), joinedload(Attendance.outlet))
        .filter(Attendance.staff_id == user.id, Attendance.date >= cutoff)
        .order_by(Attendance.date.desc())
        .all()
    )
    return [_attendance_out(a) for a in records]


@router.get("/attendance", response_model=list[AttendanceOut], dependencies=[Depends(require_manager_up)])
def list_attendance(
    staff_id: int | None = None,
    outlet_id: int | None = None,
    month: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Attendance).options(joinedload(Attendance.staff), joinedload(Attendance.outlet))
    if staff_id:
        query = query.filter(Attendance.staff_id == staff_id)
    if outlet_id:
        query = query.filter(Attendance.outlet_id == outlet_id)
    if month:
        year, mon = (int(part) for part in month.split("-"))
        last_day = monthrange(year, mon)[1]
        query = query.filter(Attendance.date >= date(year, mon, 1), Attendance.date <= date(year, mon, last_day))
    return [_attendance_out(a) for a in query.order_by(Attendance.date.desc()).limit(500).all()]


@router.patch("/attendance/{attendance_id}", response_model=AttendanceOut, dependencies=[Depends(require_manager_up)])
def update_attendance(attendance_id: int, payload: AttendanceUpdate, db: Session = Depends(get_db)):
    record = db.get(Attendance, attendance_id)
    if not record:
        raise HTTPException(404, "Attendance record not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(record, field, value)
    db.commit()
    db.refresh(record)
    return _attendance_out(record)


# ---- Leave requests ----


@router.post("/leave-requests", response_model=LeaveRequestOut)
def create_leave_request(payload: LeaveRequestCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.end_date < payload.start_date:
        raise HTTPException(400, "End date can't be before start date")
    request = LeaveRequest(staff_id=user.id, **payload.model_dump())
    db.add(request)
    db.commit()
    db.refresh(request)
    return _leave_out(request)


@router.get("/leave-requests/me", response_model=list[LeaveRequestOut])
def my_leave_requests(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    requests = (
        db.query(LeaveRequest)
        .options(joinedload(LeaveRequest.staff), joinedload(LeaveRequest.reviewed_by))
        .filter(LeaveRequest.staff_id == user.id)
        .order_by(LeaveRequest.created_at.desc())
        .all()
    )
    return [_leave_out(r) for r in requests]


@router.get("/leave-requests", response_model=list[LeaveRequestOut], dependencies=[Depends(require_manager_up)])
def list_leave_requests(
    status: LeaveStatus | None = None, staff_id: int | None = None, db: Session = Depends(get_db)
):
    query = db.query(LeaveRequest).options(joinedload(LeaveRequest.staff), joinedload(LeaveRequest.reviewed_by))
    if status:
        query = query.filter(LeaveRequest.status == status)
    if staff_id:
        query = query.filter(LeaveRequest.staff_id == staff_id)
    return [_leave_out(r) for r in query.order_by(LeaveRequest.created_at.desc()).limit(500).all()]


@router.patch("/leave-requests/{request_id}/review", response_model=LeaveRequestOut, dependencies=[Depends(require_manager_up)])
def review_leave_request(
    request_id: int, payload: LeaveReview, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    request = db.get(LeaveRequest, request_id)
    if not request:
        raise HTTPException(404, "Leave request not found")
    if request.status != LeaveStatus.PENDING:
        raise HTTPException(400, "This request has already been reviewed")
    if payload.status == LeaveStatus.PENDING:
        raise HTTPException(400, "Review status must be approved or rejected")
    request.status = payload.status
    request.review_note = payload.review_note
    request.reviewed_by_id = user.id
    request.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(request)
    return _leave_out(request)
