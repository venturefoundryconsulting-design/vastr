from datetime import datetime

from pydantic import BaseModel

from app.models.payroll import PayslipStatus


class StaffSalaryOut(BaseModel):
    staff_id: int
    staff_name: str | None = None
    monthly_salary: float | None = None
    notes: str | None = None


class StaffSalaryUpdate(BaseModel):
    monthly_salary: float
    notes: str | None = None


class PayslipOut(BaseModel):
    id: int
    staff_id: int
    staff_name: str | None = None
    month: str
    basic_amount: float
    allowances: float
    deductions: float
    net_amount: float
    status: PayslipStatus
    paid_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PayslipGenerate(BaseModel):
    month: str
    staff_id: int | None = None


class PayslipUpdate(BaseModel):
    allowances: float | None = None
    deductions: float | None = None
    status: PayslipStatus | None = None
