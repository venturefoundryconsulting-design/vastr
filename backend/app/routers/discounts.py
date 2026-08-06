from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_manager_up
from app.models.customer import Customer
from app.models.discount import DiscountRule
from app.schemas.discount import (
    DiscountApplyRequest,
    DiscountApplyResult,
    DiscountRuleCreate,
    DiscountRuleOut,
    DiscountRuleUpdate,
)
from app.services.discounts import apply_coupon, find_best_automatic_discount

router = APIRouter(prefix="/api/discounts", tags=["discounts"])


@router.get("", response_model=list[DiscountRuleOut], dependencies=[Depends(require_manager_up)])
def list_discount_rules(db: Session = Depends(get_db)):
    return db.query(DiscountRule).order_by(DiscountRule.created_at.desc()).all()


@router.post("", response_model=DiscountRuleOut, dependencies=[Depends(require_manager_up)])
def create_discount_rule(payload: DiscountRuleCreate, db: Session = Depends(get_db)):
    if payload.code and db.query(DiscountRule).filter(DiscountRule.code.ilike(payload.code)).first():
        raise HTTPException(400, f"Coupon code '{payload.code}' already exists")
    rule = DiscountRule(**payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.patch("/{rule_id}", response_model=DiscountRuleOut, dependencies=[Depends(require_manager_up)])
def update_discount_rule(rule_id: int, payload: DiscountRuleUpdate, db: Session = Depends(get_db)):
    rule = db.get(DiscountRule, rule_id)
    if not rule:
        raise HTTPException(404, "Discount rule not found")
    data = payload.model_dump(exclude_unset=True)
    if "code" in data and data["code"] and data["code"] != rule.code:
        if db.query(DiscountRule).filter(DiscountRule.code.ilike(data["code"]), DiscountRule.id != rule_id).first():
            raise HTTPException(400, f"Coupon code '{data['code']}' already exists")
    for field, value in data.items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    return rule


@router.post("/apply", response_model=DiscountApplyResult)
def apply_discount(
    payload: DiscountApplyRequest, db: Session = Depends(get_db), _=Depends(get_current_user)
):
    customer = db.get(Customer, payload.customer_id) if payload.customer_id else None
    if payload.coupon_code:
        return apply_coupon(db, payload.coupon_code, payload.items, customer)
    return find_best_automatic_discount(db, payload.items, customer)
