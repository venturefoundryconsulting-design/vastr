from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator

from app.models.workforce import PayModel, WorkOrderStatus
from app.schemas.fields import Money, Quantity


class StageCreate(BaseModel):
    code: str
    name: str
    sequence: int = 0
    default_rate: Money = Decimal("0")
    is_qc: bool = False


class StageUpdate(BaseModel):
    name: str | None = None
    sequence: int | None = None
    default_rate: Money | None = None
    is_qc: bool | None = None
    is_active: bool | None = None


class StageOut(BaseModel):
    id: int
    code: str
    name: str
    sequence: int
    default_rate: Money
    is_qc: bool
    is_active: bool


class TailorSkillIn(BaseModel):
    name: str
    stage_id: int | None = None
    proficiency: int = 3

    @field_validator("proficiency")
    @classmethod
    def in_range(cls, v: int) -> int:
        if not 1 <= v <= 5:
            raise ValueError("Proficiency runs from 1 to 5")
        return v


class TailorCreate(BaseModel):
    code: str
    name: str
    phone: str | None = None
    # Optional: contracted tailors have no login. One who does gets their own
    # work queue and nothing else.
    user_id: int | None = None
    pay_model: PayModel = PayModel.PER_STAGE
    default_rate: Money = Decimal("0")
    joined_on: date | None = None
    notes: str | None = None
    skills: list[TailorSkillIn] = []


class TailorUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    user_id: int | None = None
    pay_model: PayModel | None = None
    default_rate: Money | None = None
    joined_on: date | None = None
    notes: str | None = None
    is_active: bool | None = None
    # None leaves skills untouched; a list replaces them wholesale.
    skills: list[TailorSkillIn] | None = None


class TailorOut(BaseModel):
    id: int
    code: str
    name: str
    phone: str | None = None
    user_id: int | None = None
    pay_model: PayModel
    default_rate: Money
    joined_on: date | None = None
    notes: str | None = None
    is_active: bool
    skills: list[TailorSkillIn] = []


class TailorWorkload(BaseModel):
    tailor_id: int
    name: str
    active: int = 0
    pending: int = 0
    completed: int = 0
    overdue: int = 0


class WorkOrderCreate(BaseModel):
    production_order_id: int
    stage_id: int
    tailor_id: int | None = None
    # Defaults to the production order's planned quantity.
    quantity: Quantity | None = None
    sequence: int | None = None
    due_date: date | None = None
    rate: Money | None = None
    notes: str | None = None


class AssignRequest(BaseModel):
    tailor_id: int
    # Overrides the tailor/stage default for this work order only.
    rate: Money | None = None


class CompleteWorkOrderRequest(BaseModel):
    # Defaults to the full work order quantity.
    completed_quantity: Quantity | None = None
    hours: Decimal | None = None


class IssueNoteRequest(BaseModel):
    reason: str | None = None


class WorkOrderOut(BaseModel):
    id: int
    wo_number: str
    production_order_id: int
    po_number: str | None = None
    item_name: str | None = None
    stage_id: int
    stage_name: str | None = None
    tailor_id: int | None = None
    tailor_name: str | None = None
    quantity: Quantity
    completed_quantity: Quantity
    status: WorkOrderStatus
    sequence: int
    due_date: date | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    pay_model: PayModel | None = None
    rate: Money
    hours: Decimal
    labour_cost: Money
    is_overdue: bool
    notes: str | None = None
    issue_note: str | None = None
    allowed_transitions: list[WorkOrderStatus] = []
