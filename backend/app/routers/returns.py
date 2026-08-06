from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, get_db
from app.models.customer import BalanceType
from app.models.inventory import MovementType
from app.models.product import ProductVariant
from app.models.returns import ExchangeItem, RefundMode, Return, ReturnItem
from app.models.sale import Sale, SaleItem
from app.models.user import User
from app.schemas.returns import ExchangeItemCreate, ReturnCreate, ReturnOut
from app.services.customer import adjust_credit_balance
from app.services.inventory import apply_stock_delta, get_or_create_stock_level
from app.services.numbering import next_document_number

router = APIRouter(prefix="/api/returns", tags=["returns"])


def _to_out(ret: Return) -> ReturnOut:
    return ReturnOut(
        id=ret.id,
        return_number=ret.return_number,
        sale_id=ret.sale_id,
        sale_invoice_number=ret.sale.invoice_number,
        outlet_id=ret.outlet_id,
        outlet_name=ret.outlet.name,
        customer_id=ret.customer_id,
        customer_name=ret.customer.name if ret.customer else None,
        reason=ret.reason,
        refund_mode=ret.refund_mode,
        payment_mode=ret.payment_mode,
        returned_value=ret.returned_value,
        exchanged_value=ret.exchanged_value,
        difference=ret.difference,
        created_by_id=ret.created_by_id,
        created_at=ret.created_at,
        return_items=[
            {
                "id": i.id,
                "sale_item_id": i.sale_item_id,
                "variant_id": i.variant_id,
                "quantity": i.quantity,
                "unit_price": float(i.unit_price),
                "tax_rate": float(i.tax_rate),
                "restock": i.restock,
                "sku": i.variant.sku,
                "product_name": i.variant.display_name,
            }
            for i in ret.return_items
        ],
        exchange_items=[
            {
                "id": i.id,
                "variant_id": i.variant_id,
                "quantity": i.quantity,
                "unit_price": float(i.unit_price),
                "tax_rate": float(i.tax_rate),
                "sku": i.variant.sku,
                "product_name": i.variant.display_name,
            }
            for i in ret.exchange_items
        ],
    )


def _get_or_404(db: Session, return_id: int) -> Return:
    ret = (
        db.query(Return)
        .options(
            joinedload(Return.return_items).joinedload(ReturnItem.variant),
            joinedload(Return.exchange_items).joinedload(ExchangeItem.variant),
            joinedload(Return.outlet),
            joinedload(Return.customer),
            joinedload(Return.sale),
        )
        .filter(Return.id == return_id)
        .first()
    )
    if not ret:
        raise HTTPException(404, "Return not found")
    return ret


@router.get("", response_model=list[ReturnOut])
def list_returns(
    sale_id: int | None = None,
    outlet_id: int | None = None,
    customer_id: int | None = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    query = db.query(Return).options(
        joinedload(Return.return_items).joinedload(ReturnItem.variant),
        joinedload(Return.exchange_items).joinedload(ExchangeItem.variant),
        joinedload(Return.outlet),
        joinedload(Return.customer),
        joinedload(Return.sale),
    )
    if sale_id:
        query = query.filter(Return.sale_id == sale_id)
    if outlet_id:
        query = query.filter(Return.outlet_id == outlet_id)
    if customer_id:
        query = query.filter(Return.customer_id == customer_id)
    returns = query.order_by(Return.created_at.desc()).limit(100).all()
    return [_to_out(r) for r in returns]


@router.get("/{return_id}", response_model=ReturnOut)
def get_return(return_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return _to_out(_get_or_404(db, return_id))


def _lookup_exchange_item(db: Session, item: ExchangeItemCreate, outlet_id: int) -> ExchangeItem:
    variant = db.get(ProductVariant, item.variant_id)
    if not variant or not variant.is_active:
        raise HTTPException(404, f"Product variant {item.variant_id} not found")
    stock = get_or_create_stock_level(db, item.variant_id, outlet_id)
    if stock.quantity < item.quantity:
        raise HTTPException(
            400,
            f"Insufficient stock for {variant.sku}: have {stock.quantity}, need {item.quantity}",
        )
    return ExchangeItem(
        variant_id=item.variant_id,
        quantity=item.quantity,
        unit_price=variant.selling_price,
        tax_rate=variant.product.tax_rate,
    )


@router.post("", response_model=ReturnOut)
def create_return(payload: ReturnCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not payload.return_items:
        raise HTTPException(400, "A return needs at least one item from the original bill")

    sale = (
        db.query(Sale)
        .options(joinedload(Sale.items).joinedload(SaleItem.variant))
        .filter(Sale.id == payload.sale_id)
        .first()
    )
    if not sale:
        raise HTTPException(404, "Original sale not found")

    sale_items_by_id = {i.id: i for i in sale.items}
    returned_so_far: dict[int, int] = {}
    for sale_item_id, qty in (
        db.query(ReturnItem.sale_item_id, ReturnItem.quantity).join(Return).filter(Return.sale_id == sale.id).all()
    ):
        returned_so_far[sale_item_id] = returned_so_far.get(sale_item_id, 0) + qty

    ret = Return(
        return_number=next_document_number(db, Return, Return.return_number, "RET"),
        sale_id=sale.id,
        outlet_id=payload.outlet_id,
        customer_id=sale.customer_id,
        reason=payload.reason,
        created_by_id=user.id,
    )

    for req_item in payload.return_items:
        sale_item = sale_items_by_id.get(req_item.sale_item_id)
        if not sale_item:
            raise HTTPException(400, f"Sale item {req_item.sale_item_id} does not belong to this sale")
        prior = returned_so_far.get(req_item.sale_item_id, 0)
        if prior + req_item.quantity > sale_item.quantity:
            raise HTTPException(
                400,
                f"Cannot return {req_item.quantity} of {sale_item.variant.sku}: only "
                f"{sale_item.quantity - prior} left returnable from this bill",
            )
        ret.return_items.append(
            ReturnItem(
                sale_item_id=sale_item.id,
                variant_id=sale_item.variant_id,
                quantity=req_item.quantity,
                unit_price=sale_item.unit_price,
                tax_rate=sale_item.tax_rate,
                restock=req_item.restock,
            )
        )

    for exch_item in payload.exchange_items:
        ret.exchange_items.append(_lookup_exchange_item(db, exch_item, payload.outlet_id))

    db.add(ret)
    db.flush()

    difference = ret.difference
    if difference > 0:
        if not payload.payment_mode:
            raise HTTPException(400, "A payment mode is required to collect the difference from the customer")
        ret.payment_mode = payload.payment_mode
    elif difference < 0:
        if not payload.refund_mode:
            raise HTTPException(400, "A refund mode is required to refund the customer")
        if payload.refund_mode == RefundMode.STORE_CREDIT and not sale.customer_id:
            raise HTTPException(400, "Store credit refund requires a customer on the original sale")
        ret.refund_mode = payload.refund_mode

    for item in ret.return_items:
        if item.restock:
            apply_stock_delta(
                db,
                variant_id=item.variant_id,
                outlet_id=payload.outlet_id,
                quantity_delta=item.quantity,
                movement_type=MovementType.RETURN,
                reference_type="return",
                reference_id=ret.id,
                created_by_id=user.id,
            )

    for item in ret.exchange_items:
        apply_stock_delta(
            db,
            variant_id=item.variant_id,
            outlet_id=payload.outlet_id,
            quantity_delta=-item.quantity,
            movement_type=MovementType.SALE,
            reference_type="return",
            reference_id=ret.id,
            created_by_id=user.id,
        )

    if difference < 0 and ret.refund_mode == RefundMode.STORE_CREDIT:
        adjust_credit_balance(
            db,
            customer_id=sale.customer_id,
            amount_delta=-difference,
            balance_type=BalanceType.CREDIT,
            reference_type="return",
            reference_id=ret.id,
            reason="Refund for return",
            created_by_id=user.id,
        )

    db.commit()
    return _to_out(_get_or_404(db, ret.id))
