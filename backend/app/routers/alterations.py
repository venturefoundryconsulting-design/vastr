from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, get_db
from app.models.alteration import Alteration, AlterationStatus
from app.models.customer import Customer
from app.models.sale import Sale, SaleItem
from app.models.user import User
from app.schemas.alteration import AlterationCreate, AlterationOut, AlterationUpdate
from app.services.numbering import next_document_number

router = APIRouter(prefix="/api/alterations", tags=["alterations"])


def _to_out(a: Alteration) -> AlterationOut:
    return AlterationOut(
        id=a.id,
        alteration_number=a.alteration_number,
        outlet_id=a.outlet_id,
        outlet_name=a.outlet.name if a.outlet else None,
        sale_id=a.sale_id,
        sale_invoice_number=a.sale.invoice_number if a.sale else None,
        sale_item_id=a.sale_item_id,
        item_name=a.sale_item.variant.display_name if a.sale_item else None,
        customer_id=a.customer_id,
        customer_name=a.customer_name,
        customer_phone=a.customer_phone,
        description=a.description,
        tailor_name=a.tailor_name,
        status=a.status,
        expected_ready_date=a.expected_ready_date,
        delivered_at=a.delivered_at,
        notes=a.notes,
        created_at=a.created_at,
    )


def _get_or_404(db: Session, alteration_id: int) -> Alteration:
    alteration = (
        db.query(Alteration)
        .options(
            joinedload(Alteration.outlet),
            joinedload(Alteration.sale),
            joinedload(Alteration.sale_item).joinedload(SaleItem.variant),
        )
        .filter(Alteration.id == alteration_id)
        .first()
    )
    if not alteration:
        raise HTTPException(404, "Alteration not found")
    return alteration


@router.get("", response_model=list[AlterationOut])
def list_alterations(
    outlet_id: int | None = None,
    status: AlterationStatus | None = None,
    customer_id: int | None = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    query = db.query(Alteration).options(
        joinedload(Alteration.outlet),
        joinedload(Alteration.sale),
        joinedload(Alteration.sale_item).joinedload(SaleItem.variant),
    )
    if outlet_id:
        query = query.filter(Alteration.outlet_id == outlet_id)
    if status:
        query = query.filter(Alteration.status == status)
    if customer_id:
        query = query.filter(Alteration.customer_id == customer_id)
    alterations = query.order_by(Alteration.created_at.desc()).all()
    return [_to_out(a) for a in alterations]


@router.post("", response_model=AlterationOut)
def create_alteration(
    payload: AlterationCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    if payload.sale_item_id:
        sale_item = db.get(SaleItem, payload.sale_item_id)
        if not sale_item or (payload.sale_id and sale_item.sale_id != payload.sale_id):
            raise HTTPException(400, "That item does not belong to the selected sale")

    customer_name = payload.customer_name
    customer_phone = payload.customer_phone
    if payload.customer_id and not (customer_name and customer_phone):
        customer = db.get(Customer, payload.customer_id)
        if customer:
            customer_name = customer_name or customer.name
            customer_phone = customer_phone or customer.phone
    elif payload.sale_id and not payload.customer_id:
        sale = db.get(Sale, payload.sale_id)
        if sale:
            customer_name = customer_name or sale.customer_name
            customer_phone = customer_phone or sale.customer_phone

    alteration = Alteration(
        alteration_number=next_document_number(db, Alteration, Alteration.alteration_number, "ALT"),
        outlet_id=payload.outlet_id,
        sale_id=payload.sale_id,
        sale_item_id=payload.sale_item_id,
        customer_id=payload.customer_id,
        customer_name=customer_name,
        customer_phone=customer_phone,
        description=payload.description,
        tailor_name=payload.tailor_name,
        status=AlterationStatus.ASSIGNED if payload.tailor_name else AlterationStatus.REQUESTED,
        expected_ready_date=payload.expected_ready_date,
        notes=payload.notes,
        created_by_id=user.id,
    )
    db.add(alteration)
    db.commit()
    return _to_out(_get_or_404(db, alteration.id))


@router.patch("/{alteration_id}", response_model=AlterationOut)
def update_alteration(
    alteration_id: int, payload: AlterationUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)
):
    alteration = db.get(Alteration, alteration_id)
    if not alteration:
        raise HTTPException(404, "Alteration not found")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(alteration, field, value)
    if data.get("status") == AlterationStatus.DELIVERED and not alteration.delivered_at:
        alteration.delivered_at = datetime.now(timezone.utc)
    db.commit()
    return _to_out(_get_or_404(db, alteration_id))
