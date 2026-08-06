from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, get_db, require_manager_up
from app.models.inventory import MovementType
from app.models.transfer import StockTransfer, StockTransferItem, TransferStatus
from app.models.user import User
from app.schemas.transfer import (
    DispatchRequest,
    ReceiveRequest,
    TransferCreate,
    TransferOut,
    TransferUpdate,
)
from app.services.inventory import apply_stock_delta, get_or_create_stock_level
from app.services.app_settings import get_app_settings
from app.services.numbering import next_document_number
from app.services.pdf import render_transfer_pdf

router = APIRouter(prefix="/api/transfers", tags=["transfers"], dependencies=[Depends(require_manager_up)])


def _to_out(t: StockTransfer) -> TransferOut:
    return TransferOut(
        id=t.id,
        transfer_number=t.transfer_number,
        source_outlet_id=t.source_outlet_id,
        source_outlet_name=t.source_outlet.name,
        dest_outlet_id=t.dest_outlet_id,
        dest_outlet_name=t.dest_outlet.name,
        status=t.status,
        notes=t.notes,
        dispatched_at=t.dispatched_at,
        received_at=t.received_at,
        items=[
            {
                "id": i.id,
                "variant_id": i.variant_id,
                "quantity_requested": i.quantity_requested,
                "quantity_sent": i.quantity_sent,
                "quantity_received": i.quantity_received,
                "sku": i.variant.sku,
                "product_name": i.variant.display_name,
            }
            for i in t.items
        ],
    )


def _get_or_404(db: Session, transfer_id: int) -> StockTransfer:
    t = (
        db.query(StockTransfer)
        .options(
            joinedload(StockTransfer.items).joinedload(StockTransferItem.variant),
            joinedload(StockTransfer.source_outlet),
            joinedload(StockTransfer.dest_outlet),
        )
        .filter(StockTransfer.id == transfer_id)
        .first()
    )
    if not t:
        raise HTTPException(404, "Transfer not found")
    return t


@router.get("", response_model=list[TransferOut])
def list_transfers(
    status: TransferStatus | None = None,
    outlet_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(StockTransfer).options(
        joinedload(StockTransfer.items).joinedload(StockTransferItem.variant),
        joinedload(StockTransfer.source_outlet),
        joinedload(StockTransfer.dest_outlet),
    )
    if status:
        query = query.filter(StockTransfer.status == status)
    if outlet_id:
        query = query.filter(
            (StockTransfer.source_outlet_id == outlet_id) | (StockTransfer.dest_outlet_id == outlet_id)
        )
    transfers = query.order_by(StockTransfer.created_at.desc()).limit(100).all()
    return [_to_out(t) for t in transfers]


@router.get("/{transfer_id}", response_model=TransferOut)
def get_transfer(transfer_id: int, db: Session = Depends(get_db)):
    return _to_out(_get_or_404(db, transfer_id))


@router.get("/{transfer_id}/pdf")
def download_transfer_pdf(transfer_id: int, db: Session = Depends(get_db)):
    transfer = _get_or_404(db, transfer_id)
    pdf_bytes = render_transfer_pdf(transfer, get_app_settings(db))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{transfer.transfer_number}.pdf"'},
    )


@router.post("", response_model=TransferOut)
def create_transfer(
    payload: TransferCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    if payload.source_outlet_id == payload.dest_outlet_id:
        raise HTTPException(400, "Source and destination outlets must differ")
    transfer = StockTransfer(
        transfer_number=next_document_number(db, StockTransfer, StockTransfer.transfer_number, "TRF"),
        source_outlet_id=payload.source_outlet_id,
        dest_outlet_id=payload.dest_outlet_id,
        notes=payload.notes,
        requested_by_id=user.id,
        status=TransferStatus.REQUESTED,
    )
    for item in payload.items:
        transfer.items.append(StockTransferItem(**item.model_dump()))
    db.add(transfer)
    db.commit()
    return _to_out(_get_or_404(db, transfer.id))


@router.patch("/{transfer_id}", response_model=TransferOut)
def update_transfer(transfer_id: int, payload: TransferUpdate, db: Session = Depends(get_db)):
    transfer = _get_or_404(db, transfer_id)
    if transfer.status != TransferStatus.REQUESTED:
        raise HTTPException(
            400,
            f"Cannot edit a transfer in status '{transfer.status.value}' - "
            "editing is only allowed while it's still 'requested'",
        )
    if payload.source_outlet_id == payload.dest_outlet_id:
        raise HTTPException(400, "Source and destination outlets must differ")

    transfer.source_outlet_id = payload.source_outlet_id
    transfer.dest_outlet_id = payload.dest_outlet_id
    transfer.notes = payload.notes
    for item in list(transfer.items):
        db.delete(item)
    db.flush()
    for item in payload.items:
        transfer.items.append(StockTransferItem(**item.model_dump()))

    db.commit()
    return _to_out(_get_or_404(db, transfer_id))


@router.post("/{transfer_id}/cancel", response_model=TransferOut)
def cancel_transfer(transfer_id: int, db: Session = Depends(get_db)):
    transfer = _get_or_404(db, transfer_id)
    if transfer.status != TransferStatus.REQUESTED:
        raise HTTPException(
            400, f"Cannot cancel a transfer in status '{transfer.status.value}' - it has already dispatched"
        )
    transfer.status = TransferStatus.CANCELLED
    db.commit()
    return _to_out(_get_or_404(db, transfer_id))


@router.post("/{transfer_id}/dispatch", response_model=TransferOut)
def dispatch_transfer(
    transfer_id: int,
    payload: DispatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    transfer = _get_or_404(db, transfer_id)
    if transfer.status != TransferStatus.REQUESTED:
        raise HTTPException(400, f"Cannot dispatch a transfer in status '{transfer.status.value}'")

    items_by_id = {item.id: item for item in transfer.items}
    for dispatch_item in payload.items:
        item = items_by_id.get(dispatch_item.item_id)
        if not item:
            raise HTTPException(400, f"Item {dispatch_item.item_id} not on this transfer")
        if dispatch_item.quantity_sent <= 0:
            continue
        available = get_or_create_stock_level(db, item.variant_id, transfer.source_outlet_id)
        if dispatch_item.quantity_sent > available.quantity:
            raise HTTPException(
                400,
                f"Only {available.quantity} available for {item.variant.sku} at source outlet",
            )
        item.quantity_sent += dispatch_item.quantity_sent
        apply_stock_delta(
            db,
            variant_id=item.variant_id,
            outlet_id=transfer.source_outlet_id,
            quantity_delta=-dispatch_item.quantity_sent,
            movement_type=MovementType.TRANSFER_OUT,
            reference_type="stock_transfer",
            reference_id=transfer.id,
            created_by_id=user.id,
        )

    transfer.status = TransferStatus.DISPATCHED
    transfer.dispatched_at = datetime.now(timezone.utc)
    db.commit()
    return _to_out(_get_or_404(db, transfer_id))


@router.post("/{transfer_id}/receive", response_model=TransferOut)
def receive_transfer(
    transfer_id: int,
    payload: ReceiveRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    transfer = _get_or_404(db, transfer_id)
    if transfer.status != TransferStatus.DISPATCHED:
        raise HTTPException(400, f"Cannot receive a transfer in status '{transfer.status.value}'")

    items_by_id = {item.id: item for item in transfer.items}
    for receive_item in payload.items:
        item = items_by_id.get(receive_item.item_id)
        if not item:
            raise HTTPException(400, f"Item {receive_item.item_id} not on this transfer")
        remaining = item.quantity_sent - item.quantity_received
        if receive_item.quantity_received > remaining:
            raise HTTPException(400, f"Cannot receive more than {remaining} for {item.variant.sku}")
        if receive_item.quantity_received <= 0:
            continue
        item.quantity_received += receive_item.quantity_received
        apply_stock_delta(
            db,
            variant_id=item.variant_id,
            outlet_id=transfer.dest_outlet_id,
            quantity_delta=receive_item.quantity_received,
            movement_type=MovementType.TRANSFER_IN,
            reference_type="stock_transfer",
            reference_id=transfer.id,
            created_by_id=user.id,
        )

    if all(i.quantity_received >= i.quantity_sent for i in transfer.items):
        transfer.status = TransferStatus.RECEIVED
        transfer.received_at = datetime.now(timezone.utc)

    db.commit()
    return _to_out(_get_or_404(db, transfer_id))
