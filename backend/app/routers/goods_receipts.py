"""Goods receipts and purchase returns.

The one function permitted to write PURCHASE_RECEIPT is
``services.goods_receipt.post_receipt``; every route here goes through the
service layer rather than touching stock itself.
"""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, require_permission
from app.models.goods_receipt import (
    GoodsReceipt,
    GoodsReceiptItem,
    PurchaseReturn,
    PurchaseReturnItem,
    ReceiptStatus,
)
from app.models.outlet import Outlet
from app.models.product import Item
from app.models.purchase import PurchaseOrder
from app.models.user import User
from app.schemas.fields import Money, Quantity
from app.services import goods_receipt as gr
from app.services.audit import log_activity
from app.services.numbering import next_document_number

router = APIRouter(prefix="/api", tags=["goods-receipts"])


# --------------------------------------------------------------------- DTOs


class ReceiptLineIn(BaseModel):
    purchase_order_item_id: int | None = None
    item_id: int | None = None  # for a receipt not against a PO
    quantity: Quantity
    uom_id: int | None = None
    unit_cost: Money = Decimal("0")
    note: str | None = None


class ReceiptCreate(BaseModel):
    purchase_order_id: int | None = None
    vendor_id: int | None = None
    outlet_id: int | None = None
    vendor_invoice_ref: str | None = None
    notes: str | None = None
    lines: list[ReceiptLineIn]


class ReturnLineIn(BaseModel):
    goods_receipt_item_id: int | None = None
    item_id: int | None = None
    quantity: Quantity
    uom_id: int | None = None
    unit_cost: Money = Decimal("0")


class ReturnCreate(BaseModel):
    goods_receipt_id: int | None = None
    vendor_id: int | None = None
    outlet_id: int
    reason: str | None = None
    notes: str | None = None
    lines: list[ReturnLineIn]


def _guard(fn):
    try:
        return fn()
    except gr.GoodsReceiptError as e:
        raise HTTPException(409, str(e)) from e


def _receipt(db: Session, receipt_id: int) -> GoodsReceipt:
    r = (
        db.query(GoodsReceipt)
        .options(
            joinedload(GoodsReceipt.vendor), joinedload(GoodsReceipt.outlet),
            joinedload(GoodsReceipt.purchase_order),
            joinedload(GoodsReceipt.items).joinedload(GoodsReceiptItem.item),
            joinedload(GoodsReceipt.items).joinedload(GoodsReceiptItem.uom),
        )
        .filter(GoodsReceipt.id == receipt_id)
        .first()
    )
    if not r:
        raise HTTPException(404, "Goods receipt not found")
    return r


def _receipt_out(r: GoodsReceipt) -> dict:
    return {
        "id": r.id, "receipt_number": r.receipt_number,
        "purchase_order_id": r.purchase_order_id,
        "po_number": r.purchase_order.po_number if r.purchase_order else None,
        "vendor_id": r.vendor_id, "vendor_name": r.vendor.name if r.vendor else None,
        "outlet_id": r.outlet_id, "outlet_name": r.outlet.name if r.outlet else None,
        "receipt_date": r.receipt_date, "vendor_invoice_ref": r.vendor_invoice_ref,
        "status": r.status, "posted_at": r.posted_at, "notes": r.notes,
        "total_cost": r.total_cost,
        "items": [
            {
                "id": i.id, "item_id": i.item_id,
                "sku": i.item.sku if i.item else None,
                "name": i.item.resolved_name if i.item else None,
                "quantity": i.quantity, "uom_code": i.uom.code if i.uom else None,
                "quantity_in_stock_uom": i.quantity_in_stock_uom,
                "unit_cost": i.unit_cost, "line_cost": i.line_cost,
                "stock_movement_id": i.stock_movement_id, "note": i.note,
            }
            for i in r.items
        ],
    }


def _return(db: Session, return_id: int) -> PurchaseReturn:
    r = (
        db.query(PurchaseReturn)
        .options(
            joinedload(PurchaseReturn.vendor),
            joinedload(PurchaseReturn.items).joinedload(PurchaseReturnItem.item),
        )
        .filter(PurchaseReturn.id == return_id)
        .first()
    )
    if not r:
        raise HTTPException(404, "Purchase return not found")
    return r


def _return_out(r: PurchaseReturn) -> dict:
    return {
        "id": r.id, "return_number": r.return_number,
        "goods_receipt_id": r.goods_receipt_id,
        "vendor_id": r.vendor_id, "vendor_name": r.vendor.name if r.vendor else None,
        "outlet_id": r.outlet_id, "return_date": r.return_date, "reason": r.reason,
        "total_cost": r.total_cost,
        "items": [
            {
                "id": i.id, "item_id": i.item_id,
                "sku": i.item.sku if i.item else None,
                "quantity": i.quantity, "unit_cost": i.unit_cost, "line_cost": i.line_cost,
                "stock_movement_id": i.stock_movement_id,
            }
            for i in r.items
        ],
    }


# ------------------------------------------------------------ goods receipts


@router.get("/goods-receipts")
def list_receipts(
    db: Session = Depends(get_db), _: User = Depends(require_permission("goods_receipts.view")),
    status: ReceiptStatus | None = None, purchase_order_id: int | None = None,
    limit: int = Query(50, le=200),
):
    q = db.query(GoodsReceipt).options(
        joinedload(GoodsReceipt.vendor), joinedload(GoodsReceipt.outlet),
        joinedload(GoodsReceipt.purchase_order),
    )
    if status:
        q = q.filter(GoodsReceipt.status == status)
    if purchase_order_id:
        q = q.filter(GoodsReceipt.purchase_order_id == purchase_order_id)
    return [_receipt_out(r) for r in q.order_by(GoodsReceipt.id.desc()).limit(limit).all()]


@router.get("/goods-receipts/{receipt_id}")
def get_receipt(
    receipt_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("goods_receipts.view")),
):
    return _receipt_out(_receipt(db, receipt_id))


@router.post("/goods-receipts", status_code=201)
def create_receipt(
    payload: ReceiptCreate, db: Session = Depends(get_db),
    user: User = Depends(require_permission("goods_receipts.create")),
):
    """Draft a receipt. Stock is untouched until it is posted."""
    number = next_document_number(db, GoodsReceipt, GoodsReceipt.receipt_number, "GRN")

    if payload.purchase_order_id:
        po = db.get(PurchaseOrder, payload.purchase_order_id)
        if not po:
            raise HTTPException(404, "Purchase order not found")
        receipt = _guard(lambda: gr.build_from_purchase_order(
            db, po,
            [{"purchase_order_item_id": ln.purchase_order_item_id, "quantity": ln.quantity,
              "unit_cost": ln.unit_cost, "uom_id": ln.uom_id, "note": ln.note}
             for ln in payload.lines],
            receipt_number=number, user_id=user.id,
            vendor_invoice_ref=payload.vendor_invoice_ref, notes=payload.notes,
        ))
    else:
        if not payload.outlet_id:
            raise HTTPException(400, "A goods receipt with no purchase order needs an outlet")
        if not db.get(Outlet, payload.outlet_id):
            raise HTTPException(404, "Outlet not found")
        receipt = GoodsReceipt(
            receipt_number=number, vendor_id=payload.vendor_id, outlet_id=payload.outlet_id,
            receipt_date=date.today(), vendor_invoice_ref=payload.vendor_invoice_ref,
            notes=payload.notes, received_by_id=user.id, status=ReceiptStatus.DRAFT,
        )
        db.add(receipt)
        db.flush()
        for ln in payload.lines:
            if not ln.item_id:
                raise HTTPException(400, "Each line needs an item_id when there is no purchase order")
            if not db.get(Item, ln.item_id):
                raise HTTPException(404, f"Item {ln.item_id} not found")
            db.add(GoodsReceiptItem(
                goods_receipt_id=receipt.id, item_id=ln.item_id, quantity=ln.quantity,
                uom_id=ln.uom_id, quantity_in_stock_uom=ln.quantity,
                unit_cost=ln.unit_cost, note=ln.note,
            ))
        db.flush()

    log_activity(db, action="goods_receipt.create", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="GoodsReceipt", entity_id=receipt.id,
                 details={"receipt_number": receipt.receipt_number, "lines": len(payload.lines)})
    db.commit()
    return _receipt_out(_receipt(db, receipt.id))


@router.post("/goods-receipts/{receipt_id}/post")
def post_receipt(
    receipt_id: int, db: Session = Depends(get_db),
    user: User = Depends(require_permission("goods_receipts.post")),
):
    """Commit the receipt: move stock, update cost, advance the PO. The only
    action in this module that mutates inventory."""
    receipt = _receipt(db, receipt_id)
    _guard(lambda: gr.post_receipt(db, receipt, user_id=user.id))
    log_activity(db, action="goods_receipt.post", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="GoodsReceipt", entity_id=receipt.id,
                 details={"total_cost": receipt.total_cost})
    db.commit()
    return _receipt_out(_receipt(db, receipt_id))


@router.post("/goods-receipts/{receipt_id}/cancel")
def cancel_receipt(
    receipt_id: int, db: Session = Depends(get_db),
    user: User = Depends(require_permission("goods_receipts.create")),
):
    """Cancel a draft that will never be posted. A posted receipt cannot be
    cancelled - send the goods back with a purchase return instead."""
    receipt = _receipt(db, receipt_id)
    if receipt.status == ReceiptStatus.POSTED:
        raise HTTPException(
            409, "This receipt has already posted real stock movements and cannot be "
            "cancelled. Record a purchase return instead."
        )
    receipt.status = ReceiptStatus.CANCELLED
    log_activity(db, action="goods_receipt.cancel", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="GoodsReceipt", entity_id=receipt.id, details={})
    db.commit()
    return _receipt_out(_receipt(db, receipt_id))


# ----------------------------------------------------------- purchase returns


@router.get("/purchase-returns")
def list_returns(
    db: Session = Depends(get_db), _: User = Depends(require_permission("goods_receipts.view")),
    goods_receipt_id: int | None = None, limit: int = Query(50, le=200),
):
    q = db.query(PurchaseReturn).options(joinedload(PurchaseReturn.vendor))
    if goods_receipt_id:
        q = q.filter(PurchaseReturn.goods_receipt_id == goods_receipt_id)
    return [_return_out(r) for r in q.order_by(PurchaseReturn.id.desc()).limit(limit).all()]


@router.get("/purchase-returns/{return_id}")
def get_return(
    return_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("goods_receipts.view")),
):
    return _return_out(_return(db, return_id))


@router.post("/purchase-returns", status_code=201)
def create_return(
    payload: ReturnCreate, db: Session = Depends(get_db),
    user: User = Depends(require_permission("purchase_returns.manage")),
):
    """Create and post a purchase return in one step - unlike a receipt, there is
    no draft stage worth having, since the goods are already physically gone."""
    if not db.get(Outlet, payload.outlet_id):
        raise HTTPException(404, "Outlet not found")

    number = next_document_number(db, PurchaseReturn, PurchaseReturn.return_number, "PRET")
    purchase_return = PurchaseReturn(
        return_number=number, goods_receipt_id=payload.goods_receipt_id,
        vendor_id=payload.vendor_id, outlet_id=payload.outlet_id,
        return_date=date.today(), reason=payload.reason, notes=payload.notes,
        returned_by_id=user.id,
    )
    db.add(purchase_return)
    db.flush()

    for ln in payload.lines:
        item_id = ln.item_id
        if not item_id and ln.goods_receipt_item_id:
            src = db.get(GoodsReceiptItem, ln.goods_receipt_item_id)
            item_id = src.item_id if src else None
        if not item_id:
            raise HTTPException(400, "Each return line needs an item_id or a receipt line to return against")
        db.add(PurchaseReturnItem(
            purchase_return_id=purchase_return.id, goods_receipt_item_id=ln.goods_receipt_item_id,
            item_id=item_id, quantity=ln.quantity, uom_id=ln.uom_id, unit_cost=ln.unit_cost,
        ))
    db.flush()

    _guard(lambda: gr.post_return(db, purchase_return, user_id=user.id))
    log_activity(db, action="purchase_return.post", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="PurchaseReturn", entity_id=purchase_return.id,
                 details={"return_number": number, "total_cost": purchase_return.total_cost})
    db.commit()
    return _return_out(_return(db, purchase_return.id))
