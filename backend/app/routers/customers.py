from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, get_db, require_manager_up
from app.models.customer import (
    Customer,
    CustomerAddress,
    CustomerBalanceAdjustment,
    CustomerLoyaltyAdjustment,
)
from app.models.sale import Sale
from app.models.user import User
from app.schemas.customer import (
    CustomerAddressCreate,
    CustomerAddressOut,
    CustomerAddressUpdate,
    CustomerBalanceAdjustmentCreate,
    CustomerBalanceAdjustmentOut,
    CustomerCreate,
    CustomerLoyaltyAdjustmentCreate,
    CustomerLoyaltyAdjustmentOut,
    CustomerOut,
    CustomerPurchaseOut,
    CustomerUpdate,
)
from app.services.customer import adjust_credit_balance, adjust_loyalty_points
from app.services.export import ExportFormat, build_export_response

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.get("", response_model=list[CustomerOut])
def list_customers(
    search: str | None = None,
    tag: str | None = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    query = db.query(Customer).filter(Customer.is_active.is_(True))
    if search:
        like = f"%{search}%"
        query = query.filter(
            (Customer.name.ilike(like)) | (Customer.phone.ilike(like)) | (Customer.email.ilike(like))
        )
    if tag:
        query = query.filter(Customer.tags.any(tag))
    return query.order_by(Customer.name).limit(50).all()


@router.get("/export")
def export_customers(
    search: str | None = None,
    tag: str | None = None,
    format: ExportFormat = "xlsx",
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    query = db.query(Customer).filter(Customer.is_active.is_(True))
    if search:
        like = f"%{search}%"
        query = query.filter(
            (Customer.name.ilike(like)) | (Customer.phone.ilike(like)) | (Customer.email.ilike(like))
        )
    if tag:
        query = query.filter(Customer.tags.any(tag))
    customers = query.order_by(Customer.name).all()

    rows = [
        {
            "name": c.name,
            "phone": c.phone,
            "email": c.email,
            "whatsapp_number": c.whatsapp_number,
            "tags": ", ".join(c.tags or []),
            "is_vip": "Yes" if c.is_vip else "No",
            "credit_balance": float(c.credit_balance),
            "loyalty_points": c.loyalty_points,
            "birthday": c.birthday,
        }
        for c in customers
    ]
    columns = [
        ("name", "Name"),
        ("phone", "Phone"),
        ("email", "Email"),
        ("whatsapp_number", "WhatsApp"),
        ("tags", "Tags"),
        ("is_vip", "VIP"),
        ("credit_balance", "Credit Balance"),
        ("loyalty_points", "Loyalty Points"),
        ("birthday", "Birthday"),
    ]
    return build_export_response(rows, columns, "Customers", format)


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(404, "Customer not found")
    return customer


@router.post("", response_model=CustomerOut)
def create_customer(
    payload: CustomerCreate, db: Session = Depends(get_db), _=Depends(get_current_user)
):
    customer = Customer(**payload.model_dump())
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@router.patch("/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(404, "Customer not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)
    db.commit()
    db.refresh(customer)
    return customer


@router.get("/{customer_id}/addresses", response_model=list[CustomerAddressOut])
def list_customer_addresses(
    customer_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)
):
    return (
        db.query(CustomerAddress)
        .filter(CustomerAddress.customer_id == customer_id)
        .order_by(CustomerAddress.is_default.desc(), CustomerAddress.id)
        .all()
    )


@router.post("/addresses", response_model=CustomerAddressOut)
def create_customer_address(
    payload: CustomerAddressCreate, db: Session = Depends(get_db), _=Depends(get_current_user)
):
    if not db.get(Customer, payload.customer_id):
        raise HTTPException(404, "Customer not found")
    if payload.is_default:
        db.query(CustomerAddress).filter(
            CustomerAddress.customer_id == payload.customer_id
        ).update({"is_default": False})
    address = CustomerAddress(**payload.model_dump())
    db.add(address)
    db.commit()
    db.refresh(address)
    return address


@router.patch("/addresses/{address_id}", response_model=CustomerAddressOut)
def update_customer_address(
    address_id: int,
    payload: CustomerAddressUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    address = db.get(CustomerAddress, address_id)
    if not address:
        raise HTTPException(404, "Address not found")
    data = payload.model_dump(exclude_unset=True)
    if data.get("is_default"):
        db.query(CustomerAddress).filter(
            CustomerAddress.customer_id == address.customer_id
        ).update({"is_default": False})
    for field, value in data.items():
        setattr(address, field, value)
    db.commit()
    db.refresh(address)
    return address


@router.delete("/addresses/{address_id}")
def delete_customer_address(
    address_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)
):
    address = db.get(CustomerAddress, address_id)
    if not address:
        raise HTTPException(404, "Address not found")
    db.delete(address)
    db.commit()
    return {"ok": True}


@router.get("/{customer_id}/purchases", response_model=list[CustomerPurchaseOut])
def list_customer_purchases(
    customer_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)
):
    if not db.get(Customer, customer_id):
        raise HTTPException(404, "Customer not found")
    sales = (
        db.query(Sale)
        .options(joinedload(Sale.outlet))
        .filter(Sale.customer_id == customer_id)
        .order_by(Sale.created_at.desc())
        .all()
    )
    return [
        CustomerPurchaseOut(
            sale_id=s.id,
            invoice_number=s.invoice_number,
            outlet_id=s.outlet_id,
            outlet_name=s.outlet.name,
            total=s.total,
            payment_mode=s.payment_mode,
            created_at=s.created_at,
        )
        for s in sales
    ]


@router.get("/{customer_id}/balance-adjustments", response_model=list[CustomerBalanceAdjustmentOut])
def list_balance_adjustments(
    customer_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)
):
    if not db.get(Customer, customer_id):
        raise HTTPException(404, "Customer not found")
    return (
        db.query(CustomerBalanceAdjustment)
        .filter(CustomerBalanceAdjustment.customer_id == customer_id)
        .order_by(CustomerBalanceAdjustment.created_at.desc())
        .all()
    )


@router.post(
    "/{customer_id}/adjust-balance",
    response_model=CustomerBalanceAdjustmentOut,
    dependencies=[Depends(require_manager_up)],
)
def adjust_balance(
    customer_id: int,
    payload: CustomerBalanceAdjustmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not db.get(Customer, customer_id):
        raise HTTPException(404, "Customer not found")
    adjustment = adjust_credit_balance(
        db,
        customer_id=customer_id,
        amount_delta=payload.amount_delta,
        balance_type=payload.balance_type,
        reference_type="manual",
        reason=payload.reason,
        created_by_id=user.id,
    )
    db.commit()
    db.refresh(adjustment)
    return adjustment


@router.get("/{customer_id}/loyalty-adjustments", response_model=list[CustomerLoyaltyAdjustmentOut])
def list_loyalty_adjustments(
    customer_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)
):
    if not db.get(Customer, customer_id):
        raise HTTPException(404, "Customer not found")
    return (
        db.query(CustomerLoyaltyAdjustment)
        .filter(CustomerLoyaltyAdjustment.customer_id == customer_id)
        .order_by(CustomerLoyaltyAdjustment.created_at.desc())
        .all()
    )


@router.post(
    "/{customer_id}/adjust-loyalty",
    response_model=CustomerLoyaltyAdjustmentOut,
    dependencies=[Depends(require_manager_up)],
)
def adjust_loyalty(
    customer_id: int,
    payload: CustomerLoyaltyAdjustmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not db.get(Customer, customer_id):
        raise HTTPException(404, "Customer not found")
    adjustment = adjust_loyalty_points(
        db,
        customer_id=customer_id,
        points_delta=payload.points_delta,
        reference_type="manual",
        reason=payload.reason,
        created_by_id=user.id,
    )
    db.commit()
    db.refresh(adjustment)
    return adjustment
