from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, require_admin
from app.models.payroll import Payslip, PayslipStatus, StaffSalary
from app.models.user import User
from app.schemas.payroll import PayslipGenerate, PayslipOut, PayslipUpdate, StaffSalaryOut, StaffSalaryUpdate

router = APIRouter(prefix="/api/payroll", tags=["payroll"], dependencies=[Depends(require_admin)])


def _payslip_out(p: Payslip) -> PayslipOut:
    return PayslipOut(
        id=p.id,
        staff_id=p.staff_id,
        staff_name=p.staff.name if p.staff else None,
        month=p.month,
        basic_amount=float(p.basic_amount),
        allowances=float(p.allowances),
        deductions=float(p.deductions),
        net_amount=float(p.net_amount),
        status=p.status,
        paid_at=p.paid_at,
        created_at=p.created_at,
    )


@router.get("/salaries", response_model=list[StaffSalaryOut])
def list_salaries(db: Session = Depends(get_db)):
    staff = db.query(User).filter(User.is_active.is_(True)).order_by(User.name).all()
    salaries = {s.staff_id: s for s in db.query(StaffSalary).all()}
    return [
        StaffSalaryOut(
            staff_id=u.id,
            staff_name=u.name,
            monthly_salary=float(salaries[u.id].monthly_salary) if u.id in salaries else None,
            notes=salaries[u.id].notes if u.id in salaries else None,
        )
        for u in staff
    ]


@router.patch("/salaries/{staff_id}", response_model=StaffSalaryOut)
def update_salary(staff_id: int, payload: StaffSalaryUpdate, db: Session = Depends(get_db)):
    staff = db.get(User, staff_id)
    if not staff:
        raise HTTPException(404, "Staff member not found")
    salary = db.query(StaffSalary).filter(StaffSalary.staff_id == staff_id).first()
    if not salary:
        salary = StaffSalary(staff_id=staff_id, monthly_salary=payload.monthly_salary, notes=payload.notes)
        db.add(salary)
    else:
        salary.monthly_salary = payload.monthly_salary
        salary.notes = payload.notes
    db.commit()
    db.refresh(salary)
    return StaffSalaryOut(staff_id=staff_id, staff_name=staff.name, monthly_salary=float(salary.monthly_salary), notes=salary.notes)


@router.get("/payslips", response_model=list[PayslipOut])
def list_payslips(month: str | None = None, staff_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(Payslip).options(joinedload(Payslip.staff))
    if month:
        query = query.filter(Payslip.month == month)
    if staff_id:
        query = query.filter(Payslip.staff_id == staff_id)
    return [_payslip_out(p) for p in query.order_by(Payslip.month.desc(), Payslip.staff_id).all()]


@router.post("/payslips/generate", response_model=list[PayslipOut])
def generate_payslips(payload: PayslipGenerate, db: Session = Depends(get_db)):
    query = db.query(StaffSalary)
    if payload.staff_id:
        query = query.filter(StaffSalary.staff_id == payload.staff_id)
    salaries = query.all()
    if not salaries:
        raise HTTPException(400, "No staff salary configured yet - set a monthly salary under Salary Setup first")

    existing_staff_ids = {
        p.staff_id for p in db.query(Payslip.staff_id).filter(Payslip.month == payload.month).all()
    }

    created = []
    for salary in salaries:
        if salary.staff_id in existing_staff_ids:
            continue
        payslip = Payslip(
            staff_id=salary.staff_id,
            month=payload.month,
            basic_amount=salary.monthly_salary,
            allowances=0,
            deductions=0,
            net_amount=salary.monthly_salary,
        )
        db.add(payslip)
        created.append(payslip)

    if not created:
        raise HTTPException(400, f"Payslips for {payload.month} already exist for the selected staff")

    db.commit()
    for p in created:
        db.refresh(p)
    return [_payslip_out(p) for p in created]


@router.patch("/payslips/{payslip_id}", response_model=PayslipOut)
def update_payslip(payslip_id: int, payload: PayslipUpdate, db: Session = Depends(get_db)):
    payslip = db.get(Payslip, payslip_id)
    if not payslip:
        raise HTTPException(404, "Payslip not found")

    data = payload.model_dump(exclude_unset=True)
    if "allowances" in data:
        payslip.allowances = data["allowances"]
    if "deductions" in data:
        payslip.deductions = data["deductions"]
    if "allowances" in data or "deductions" in data:
        payslip.net_amount = float(payslip.basic_amount) + float(payslip.allowances) - float(payslip.deductions)
    if data.get("status") == PayslipStatus.PAID and payslip.status != PayslipStatus.PAID:
        payslip.paid_at = datetime.now(timezone.utc)
    if "status" in data:
        payslip.status = data["status"]

    db.commit()
    db.refresh(payslip)
    return _payslip_out(payslip)
