"""Customer measurements and made-to-order customer orders.

DELIVERY REUSES THE POS. ``/deliver`` builds a normal SaleCreate and calls
``app.routers.sales.checkout`` - the same function the counter uses. That is what
validates stock, writes the SALE ledger row, applies loyalty and produces a
receipt. Nothing here deducts stock itself, so a made-to-order garment leaves
inventory by exactly the same path as an off-the-rack one.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, get_db, require_permission
from app.models.customer import Customer
from app.models.made_to_order import (
    CO_TRANSITIONS,
    CustomerOrder,
    CustomerOrderItem,
    CustomerOrderStatus,
    Fulfilment,
    MeasurementField,
    MeasurementProfile,
    MeasurementValue,
)
from app.models.outlet import Outlet
from app.models.product import Item
from app.models.production import ProductionOrder
from app.models.sale import PaymentMode
from app.models.user import User
from app.schemas.fields import Money, Quantity
from app.schemas.sale import SaleCreate, SaleItemCreate
from app.services import made_to_order as mto
from app.services.audit import log_activity
from app.services.numbering import next_document_number

router = APIRouter(prefix="/api", tags=["made-to-order"])


# --------------------------------------------------------------------- DTOs


class MeasurementFieldOut(BaseModel):
    id: int
    code: str
    name: str
    unit: str
    sequence: int
    group_name: str | None = None
    is_active: bool


class MeasurementFieldCreate(BaseModel):
    code: str
    name: str
    unit: str = "inch"
    sequence: int = 0
    group_name: str | None = None


class MeasurementValueIn(BaseModel):
    field_id: int
    value: Decimal
    notes: str | None = None

    @field_validator("value")
    @classmethod
    def positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("A measurement must be greater than zero")
        return v


class ProfileCreate(BaseModel):
    customer_id: int
    name: str
    notes: str | None = None
    values: list[MeasurementValueIn] = []


class ProfileUpdate(BaseModel):
    name: str | None = None
    notes: str | None = None
    is_active: bool | None = None
    # Replaces the whole set. A re-measure that changes three numbers is still
    # one act of measuring.
    values: list[MeasurementValueIn] | None = None


class ProfileOut(BaseModel):
    id: int
    customer_id: int
    name: str
    notes: str | None = None
    taken_at: datetime | None = None
    is_active: bool
    values: list[dict] = []


class OrderItemIn(BaseModel):
    item_id: int
    quantity: Quantity = Decimal("1")
    unit_price: Money = Decimal("0")
    tax_rate: Money = Decimal("0")
    fulfilment: Fulfilment = Fulfilment.READY_STOCK
    measurement_profile_id: int | None = None
    notes: str | None = None


class OrderCreate(BaseModel):
    customer_id: int
    outlet_id: int
    promised_date: date | None = None
    advance_amount: Money = Decimal("0")
    notes: str | None = None
    items: list[OrderItemIn]


class DeliverRequest(BaseModel):
    payment_mode: PaymentMode = PaymentMode.CASH
    # The advance already taken is deducted from what is collected now.
    discount_amount: Money = Decimal("0")


class CancelRequest(BaseModel):
    reason: str | None = None


def _guard(fn):
    try:
        return fn()
    except mto.CustomerOrderError as e:
        raise HTTPException(409, str(e)) from e


def _order(db: Session, order_id: int) -> CustomerOrder:
    o = (
        db.query(CustomerOrder)
        .options(
            joinedload(CustomerOrder.customer), joinedload(CustomerOrder.outlet),
            joinedload(CustomerOrder.items).joinedload(CustomerOrderItem.item),
            joinedload(CustomerOrder.items).joinedload(CustomerOrderItem.production_order),
        )
        .filter(CustomerOrder.id == order_id)
        .first()
    )
    if not o:
        raise HTTPException(404, "Customer order not found")
    return o


def _order_out(db: Session, o: CustomerOrder) -> dict:
    return {
        "id": o.id, "order_number": o.order_number, "customer_id": o.customer_id,
        "customer_name": o.customer.name if o.customer else None,
        "outlet_id": o.outlet_id, "outlet_name": o.outlet.name if o.outlet else None,
        "status": o.status, "order_date": o.order_date, "promised_date": o.promised_date,
        "delivered_at": o.delivered_at, "advance_amount": o.advance_amount,
        "total_amount": o.total_amount, "balance_due": o.balance_due,
        "sale_id": o.sale_id, "notes": o.notes, "cancel_reason": o.cancel_reason,
        "has_made_to_order": o.has_made_to_order,
        "allowed_transitions": sorted(
            (s.value for s in CO_TRANSITIONS.get(o.status, set()))
        ),
        "items": [
            {
                "id": i.id, "item_id": i.item_id,
                "sku": i.item.sku if i.item else None,
                "name": i.item.resolved_name if i.item else None,
                "quantity": i.quantity, "unit_price": i.unit_price, "tax_rate": i.tax_rate,
                "line_total": i.line_total, "fulfilment": i.fulfilment,
                "measurement_profile_id": i.measurement_profile_id,
                "production_order_id": i.production_order_id,
                "production_status": (
                    i.production_order.status if i.production_order else None
                ),
                "produced_quantity": (
                    i.production_order.produced_quantity if i.production_order else None
                ),
                "notes": i.notes,
            }
            for i in o.items
        ],
    }


# ----------------------------------------------------------- measurements


@router.get("/measurement-fields", response_model=list[MeasurementFieldOut])
def list_fields(
    db: Session = Depends(get_db), _: User = Depends(require_permission("measurements.view")),
    include_inactive: bool = False,
):
    q = db.query(MeasurementField)
    if not include_inactive:
        q = q.filter(MeasurementField.is_active.is_(True))
    return q.order_by(MeasurementField.sequence).all()


@router.post("/measurement-fields", response_model=MeasurementFieldOut, status_code=201)
def create_field(
    payload: MeasurementFieldCreate, db: Session = Depends(get_db),
    _: User = Depends(require_permission("measurements.manage")),
):
    """Add a measurement the boutique takes. Data, not a schema change."""
    if db.query(MeasurementField).filter(MeasurementField.code == payload.code).first():
        raise HTTPException(409, f"A measurement with code '{payload.code}' already exists")
    field = MeasurementField(**payload.model_dump())
    db.add(field)
    db.commit()
    db.refresh(field)
    return field


@router.get("/customers/{customer_id}/measurements", response_model=list[ProfileOut])
def list_profiles(
    customer_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("measurements.view")),
):
    if not db.get(Customer, customer_id):
        raise HTTPException(404, "Customer not found")
    profiles = (
        db.query(MeasurementProfile)
        .options(joinedload(MeasurementProfile.values).joinedload(MeasurementValue.field))
        .filter(MeasurementProfile.customer_id == customer_id)
        .order_by(MeasurementProfile.id.desc())
        .all()
    )
    return [
        ProfileOut(
            id=p.id, customer_id=p.customer_id, name=p.name, notes=p.notes,
            taken_at=p.taken_at, is_active=p.is_active,
            values=[
                {"field_id": v.field_id,
                 "code": v.field.code if v.field else None,
                 "label": v.field.name if v.field else None,
                 "unit": v.field.unit if v.field else None,
                 "value": v.value, "notes": v.notes}
                for v in p.values
            ],
        )
        for p in profiles
    ]


@router.post("/measurement-profiles", response_model=ProfileOut, status_code=201)
def create_profile(
    payload: ProfileCreate, db: Session = Depends(get_db),
    user: User = Depends(require_permission("measurements.manage")),
):
    if not db.get(Customer, payload.customer_id):
        raise HTTPException(404, "Customer not found")
    profile = MeasurementProfile(
        customer_id=payload.customer_id, name=payload.name, notes=payload.notes,
        taken_by_id=user.id, taken_at=datetime.now(timezone.utc),
    )
    db.add(profile)
    db.flush()
    for v in payload.values:
        if not db.get(MeasurementField, v.field_id):
            raise HTTPException(404, f"Measurement field {v.field_id} not found")
        db.add(MeasurementValue(profile_id=profile.id, **v.model_dump()))
    db.commit()
    return list_profiles(payload.customer_id, db, user)[0]


@router.patch("/measurement-profiles/{profile_id}", response_model=ProfileOut)
def update_profile(
    profile_id: int, payload: ProfileUpdate, db: Session = Depends(get_db),
    user: User = Depends(require_permission("measurements.manage")),
):
    profile = db.get(MeasurementProfile, profile_id)
    if not profile:
        raise HTTPException(404, "Measurement profile not found")
    for f, v in payload.model_dump(exclude_unset=True, exclude={"values"}).items():
        setattr(profile, f, v)
    if payload.values is not None:
        for existing in list(profile.values):
            db.delete(existing)
        db.flush()
        for v in payload.values:
            db.add(MeasurementValue(profile_id=profile.id, **v.model_dump()))
        profile.taken_at = datetime.now(timezone.utc)
        profile.taken_by_id = user.id
    db.commit()
    return next(p for p in list_profiles(profile.customer_id, db, user) if p.id == profile_id)


# --------------------------------------------------------- customer orders


@router.get("/customer-orders")
def list_orders(
    db: Session = Depends(get_db), _: User = Depends(require_permission("customer_orders.view")),
    status: CustomerOrderStatus | None = None,
    customer_id: int | None = None,
    limit: int = Query(50, le=200),
):
    q = db.query(CustomerOrder).options(
        joinedload(CustomerOrder.customer), joinedload(CustomerOrder.outlet),
        joinedload(CustomerOrder.items).joinedload(CustomerOrderItem.item),
        joinedload(CustomerOrder.items).joinedload(CustomerOrderItem.production_order),
    )
    if status:
        q = q.filter(CustomerOrder.status == status)
    if customer_id:
        q = q.filter(CustomerOrder.customer_id == customer_id)
    return [_order_out(db, o) for o in q.order_by(CustomerOrder.id.desc()).limit(limit).all()]


@router.get("/customer-orders/{order_id}")
def get_order(
    order_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("customer_orders.view")),
):
    return _order_out(db, _order(db, order_id))


@router.post("/customer-orders", status_code=201)
def create_order(
    payload: OrderCreate, db: Session = Depends(get_db),
    user: User = Depends(require_permission("customer_orders.create")),
):
    """Take an order. Ready-stock and made-to-order lines can sit side by side."""
    if not db.get(Customer, payload.customer_id):
        raise HTTPException(404, "Customer not found")
    if not db.get(Outlet, payload.outlet_id):
        raise HTTPException(404, "Outlet not found")
    if not payload.items:
        raise HTTPException(400, "A customer order needs at least one item")

    order = CustomerOrder(
        order_number=next_document_number(db, CustomerOrder, CustomerOrder.order_number, "CO"),
        customer_id=payload.customer_id, outlet_id=payload.outlet_id,
        order_date=date.today(), promised_date=payload.promised_date,
        advance_amount=payload.advance_amount, notes=payload.notes,
        status=CustomerOrderStatus.DRAFT, created_by_id=user.id,
    )
    db.add(order)
    db.flush()

    for line in payload.items:
        item = db.get(Item, line.item_id)
        if not item:
            raise HTTPException(404, f"Item {line.item_id} not found")
        if line.measurement_profile_id and not db.get(
            MeasurementProfile, line.measurement_profile_id
        ):
            raise HTTPException(404, "Measurement profile not found")
        db.add(CustomerOrderItem(customer_order_id=order.id, **line.model_dump()))

    log_activity(db, action="customer_order.create", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="CustomerOrder", entity_id=order.id,
                 details={"order_number": order.order_number, "lines": len(payload.items)})
    db.commit()
    return _order_out(db, _order(db, order.id))


@router.post("/customer-orders/{order_id}/confirm")
def confirm_order(
    order_id: int, db: Session = Depends(get_db),
    user: User = Depends(require_permission("customer_orders.confirm")),
):
    """Confirm, spawning a DRAFT production order per made-to-order line.

    Production is created but not released - committing material is a production
    decision, not a counter one.
    """
    order = _order(db, order_id)
    spawned = _guard(lambda: mto.confirm(
        db, order, user_id=user.id,
        numbering=lambda: next_document_number(
            db, ProductionOrder, ProductionOrder.po_number, "PRD"
        ),
    ))
    log_activity(db, action="customer_order.confirm", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="CustomerOrder", entity_id=order.id,
                 details={"production_orders": [p.po_number for p in spawned]})
    db.commit()
    return _order_out(db, _order(db, order_id))


@router.get("/customer-orders/{order_id}/readiness")
def order_readiness(
    order_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("customer_orders.view")),
):
    """Can this actually be handed over? Read-only."""
    return mto.readiness(db, _order(db, order_id))


@router.post("/customer-orders/{order_id}/ready")
def mark_ready(
    order_id: int, db: Session = Depends(get_db),
    user: User = Depends(require_permission("customer_orders.confirm")),
):
    order = _order(db, order_id)
    _guard(lambda: mto.mark_ready(db, order))
    log_activity(db, action="customer_order.ready", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="CustomerOrder", entity_id=order.id, details={})
    db.commit()
    return _order_out(db, _order(db, order_id))


@router.post("/customer-orders/{order_id}/deliver")
def deliver_order(
    order_id: int, payload: DeliverRequest, db: Session = Depends(get_db),
    user: User = Depends(require_permission("customer_orders.deliver")),
):
    """Hand the order over: raise an ordinary POS sale and close the order.

    The sale is created through the same checkout the counter uses, so stock
    deduction, the ledger row, loyalty and the receipt all behave identically to
    an off-the-rack sale. The advance already taken is applied as a discount so
    the customer is only charged the balance.
    """
    from app.routers import sales as sales_router

    order = _order(db, order_id)
    if order.status != CustomerOrderStatus.READY:
        raise HTTPException(
            409,
            f"This order is {order.status.value}. Mark it ready once everything can be "
            "handed over, then deliver it.",
        )

    sale_payload = SaleCreate(
        outlet_id=order.outlet_id,
        customer_id=order.customer_id,
        payment_mode=payload.payment_mode,
        # The advance is money already taken, so it reduces what is collected now
        # rather than being charged twice.
        discount_amount=Decimal(order.advance_amount or 0) + Decimal(payload.discount_amount or 0),
        items=[
            SaleItemCreate(
                variant_id=line.item_id, quantity=line.quantity,
                unit_price=line.unit_price, tax_rate=line.tax_rate,
            )
            for line in order.items
        ],
    )
    # checkout() raises 400 on insufficient stock - the right failure, and it
    # happens before the order is marked delivered.
    sale = sales_router.checkout(sale_payload, db, user)

    _guard(lambda: mto.attach_sale(db, order, sale.id))
    log_activity(db, action="customer_order.deliver", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="CustomerOrder", entity_id=order.id,
                 details={"sale_id": sale.id, "invoice": sale.invoice_number,
                          "total": order.total_amount})
    db.commit()
    return _order_out(db, _order(db, order_id))


@router.post("/customer-orders/{order_id}/cancel")
def cancel_order(
    order_id: int, payload: CancelRequest, db: Session = Depends(get_db),
    user: User = Depends(require_permission("customer_orders.cancel")),
):
    """Cancel the order and every production run it spawned.

    Cancelling production is what releases the material reservations it was
    holding - see Phase 3D, Rule 8.
    """
    from app.routers import production_orders as po_router
    from app.schemas.production import TransitionRequest

    order = _order(db, order_id)
    to_cancel = _guard(lambda: mto.cancel(db, order, payload.reason))
    for po in to_cancel:
        po_router.cancel_order(
            po.id,
            TransitionRequest(reason=f"Customer order {order.order_number} cancelled"),
            db, user,
        )
    log_activity(db, action="customer_order.cancel", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="CustomerOrder", entity_id=order.id,
                 details={"reason": payload.reason,
                          "production_orders_cancelled": [p.po_number for p in to_cancel]})
    db.commit()
    return _order_out(db, _order(db, order_id))
