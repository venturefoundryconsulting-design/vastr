"""Receiving goods and sending them back.

THE ONLY WRITER OF PURCHASE_RECEIPT. Rule 2 ("only receiving increases
inventory") is enforced by there being exactly one function that can emit that
movement type, and it lives here. Creating or approving a purchase order writes
nothing.

WEIGHTED-AVERAGE COST is recalculated on every posting:

    new_avg = (on_hand x old_avg + received x receipt_cost) / (on_hand + received)

and the resulting unit cost is stamped onto the ledger row. Storing it per
movement rather than only on the item is what would let FIFO be added later
without reconstructing history from invoices.

Cost is held on ``Item.cost_price`` rather than a separate ``moving_avg_cost``
column, so BOM estimates and reorder suggestions automatically follow real
purchase prices instead of a number somebody typed once. That is a deliberate
choice, not an omission: a boutique that wants a frozen standard cost would need
a second column, and none has asked.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.money import money, to_decimal
from app.models.goods_receipt import (
    GoodsReceipt,
    GoodsReceiptItem,
    PurchaseReturn,
    PurchaseReturnItem,
    ReceiptStatus,
)
from app.models.inventory import MovementType
from app.models.product import Item
from app.models.purchase import PurchaseOrder, PurchaseOrderItem, PurchaseOrderStatus
from app.models.uom import UnitOfMeasure
from app.services.inventory import apply_stock_delta, get_or_create_stock_level
from app.services.uom import UomConversionError, convert


class GoodsReceiptError(ValueError):
    """A receiving rule was violated. Message is user-facing."""


def to_stock_quantity(
    db: Session, item: Item, quantity: Decimal, uom_id: int | None, *, vendor_id: int | None = None
) -> Decimal:
    """Convert a counted quantity into the item's stock unit.

    This is where "2 rolls" becomes "50 metres". Falls back to the raw quantity
    when the item has no stock unit set, which is every pre-Phase-2 product.
    """
    if not uom_id or not item.stock_uom_id or uom_id == item.stock_uom_id:
        return to_decimal(quantity)
    from_uom = db.get(UnitOfMeasure, uom_id)
    stock_uom = db.get(UnitOfMeasure, item.stock_uom_id)
    if not from_uom or not stock_uom:
        return to_decimal(quantity)
    try:
        return convert(db, quantity, from_uom, stock_uom, item_id=item.id, vendor_id=vendor_id)
    except UomConversionError as e:
        raise GoodsReceiptError(
            f"{item.sku}: cannot receive in {from_uom.code} when stock is kept in "
            f"{stock_uom.code}. {e}"
        ) from e


def _update_average_cost(
    db: Session, item: Item, received_in_stock_uom: Decimal, unit_cost_stock_uom: Decimal
) -> None:
    """Weighted average over everything currently on hand, all locations.

    Read *before* the receipt's own movement is applied, so the incoming quantity
    is not counted on both sides of the average.
    """
    if received_in_stock_uom <= 0 or unit_cost_stock_uom <= 0:
        return
    from app.models.inventory import StockLevel

    on_hand = to_decimal(
        db.query(func.coalesce(func.sum(StockLevel.quantity), 0))
        .filter(StockLevel.variant_id == item.id)
        .scalar()
    )
    old = to_decimal(item.cost_price)
    total = on_hand + received_in_stock_uom
    if total <= 0:
        return
    item.cost_price = money((on_hand * old + received_in_stock_uom * unit_cost_stock_uom) / total)


def post_receipt(
    db: Session, receipt: GoodsReceipt, *, user_id: int | None = None
) -> GoodsReceipt:
    """Commit a counted delivery: move stock, update costs, advance the PO.

    Everything happens under the ledger's own row lock, and the caller commits -
    so a receipt and its stock movements land together or not at all.
    """
    if receipt.status == ReceiptStatus.POSTED:
        raise GoodsReceiptError(f"{receipt.receipt_number} has already been posted")
    if receipt.status == ReceiptStatus.CANCELLED:
        raise GoodsReceiptError(f"{receipt.receipt_number} was cancelled and cannot be posted")
    if not receipt.items:
        raise GoodsReceiptError("A goods receipt needs at least one line before it can be posted")

    vendor_id = receipt.vendor_id
    for line in receipt.items:
        item = db.get(Item, line.item_id)
        if not item:
            raise GoodsReceiptError(f"Item {line.item_id} no longer exists")

        qty = to_decimal(line.quantity)
        if qty <= 0:
            raise GoodsReceiptError(f"{item.sku}: received quantity must be greater than zero")

        in_stock_uom = to_stock_quantity(db, item, qty, line.uom_id, vendor_id=vendor_id)
        line.quantity_in_stock_uom = in_stock_uom

        # Cost per *stock* unit: a roll at 3000 that yields 50 m is 60/m.
        unit_cost_stock = (
            money(to_decimal(line.unit_cost) * qty / in_stock_uom)
            if in_stock_uom > 0
            else to_decimal(line.unit_cost)
        )

        get_or_create_stock_level(db, item.id, receipt.outlet_id)
        _update_average_cost(db, item, in_stock_uom, unit_cost_stock)

        movement = apply_stock_delta(
            db,
            variant_id=item.id,
            outlet_id=receipt.outlet_id,
            quantity_delta=in_stock_uom,
            movement_type=MovementType.PURCHASE_RECEIPT,
            reference_type="goods_receipt",
            reference_id=receipt.id,
            note=f"Received on {receipt.receipt_number}",
            created_by_id=user_id,
        )
        movement.unit_cost = unit_cost_stock
        line.stock_movement_id = movement.id

        # Advance the purchase order line, if this receipt is against one.
        if line.purchase_order_item_id:
            po_item = db.get(PurchaseOrderItem, line.purchase_order_item_id)
            if po_item:
                remaining = to_decimal(po_item.quantity_ordered) - to_decimal(
                    po_item.quantity_received
                )
                if qty > remaining:
                    raise GoodsReceiptError(
                        f"{item.sku}: {qty} exceeds the {remaining} still outstanding on this "
                        "purchase order."
                    )
                po_item.quantity_received = to_decimal(po_item.quantity_received) + qty

    receipt.status = ReceiptStatus.POSTED
    receipt.posted_at = datetime.now(timezone.utc)
    receipt.received_by_id = receipt.received_by_id or user_id
    db.flush()

    if receipt.purchase_order_id:
        _sync_po_status(db, receipt.purchase_order_id)
    return receipt


def _sync_po_status(db: Session, po_id: int) -> None:
    po = db.get(PurchaseOrder, po_id)
    if not po or po.status == PurchaseOrderStatus.CANCELLED:
        return
    if all(
        to_decimal(i.quantity_received) >= to_decimal(i.quantity_ordered) for i in po.items
    ):
        po.status = PurchaseOrderStatus.RECEIVED
    elif any(to_decimal(i.quantity_received) > 0 for i in po.items):
        po.status = PurchaseOrderStatus.PARTIALLY_RECEIVED
    db.flush()


def returnable(
    db: Session, receipt_line: GoodsReceiptItem, *, exclude_return_item_id: int | None = None
) -> Decimal:
    """How much of a received line can still go back, in stock units.

    ``exclude_return_item_id`` matters when checking a return line that has
    already been flushed to get its id (as ``post_return`` does): without
    excluding it, the line would count itself as "already returned" against its
    own limit, which understates what is actually still returnable.
    """
    q = db.query(func.coalesce(func.sum(PurchaseReturnItem.quantity), 0)).filter(
        PurchaseReturnItem.goods_receipt_item_id == receipt_line.id
    )
    if exclude_return_item_id is not None:
        q = q.filter(PurchaseReturnItem.id != exclude_return_item_id)
    already = to_decimal(q.scalar())
    return to_decimal(receipt_line.quantity_in_stock_uom) - already


def post_return(
    db: Session, purchase_return: PurchaseReturn, *, user_id: int | None = None
) -> PurchaseReturn:
    """Send goods back: a negative movement that leaves the receipt untouched."""
    if not purchase_return.items:
        raise GoodsReceiptError("A purchase return needs at least one line")

    for line in purchase_return.items:
        item = db.get(Item, line.item_id)
        if not item:
            raise GoodsReceiptError(f"Item {line.item_id} no longer exists")

        qty = to_decimal(line.quantity)
        if qty <= 0:
            raise GoodsReceiptError(f"{item.sku}: return quantity must be greater than zero")

        if line.goods_receipt_item_id:
            source = db.get(GoodsReceiptItem, line.goods_receipt_item_id)
            if not source:
                raise GoodsReceiptError("The receipt line being returned no longer exists")
            allowed = returnable(db, source, exclude_return_item_id=line.id)
            if qty > allowed:
                raise GoodsReceiptError(
                    f"{item.sku}: at most {allowed} can still be returned against "
                    f"{source.receipt.receipt_number} - {qty} requested."
                )

        level = get_or_create_stock_level(db, item.id, purchase_return.outlet_id)
        on_hand = to_decimal(level.quantity)
        if qty > on_hand:
            raise GoodsReceiptError(
                f"{item.sku}: only {on_hand} is physically in stock, so {qty} cannot be sent back."
            )

        movement = apply_stock_delta(
            db,
            variant_id=item.id,
            outlet_id=purchase_return.outlet_id,
            quantity_delta=-qty,
            movement_type=MovementType.PURCHASE_RETURN,
            reference_type="purchase_return",
            reference_id=purchase_return.id,
            note=f"Returned on {purchase_return.return_number}",
            created_by_id=user_id,
        )
        movement.unit_cost = to_decimal(line.unit_cost) or to_decimal(item.cost_price)
        line.stock_movement_id = movement.id

    db.flush()
    return purchase_return


def build_from_purchase_order(
    db: Session,
    po: PurchaseOrder,
    lines: list[dict],
    *,
    receipt_number: str,
    user_id: int | None = None,
    vendor_invoice_ref: str | None = None,
    notes: str | None = None,
) -> GoodsReceipt:
    """Draft a receipt against a purchase order.

    ``lines`` is ``[{purchase_order_item_id, quantity, unit_cost?, uom_id?}]``.
    Unit cost defaults to what the order agreed, so the common case - the vendor
    delivered what was ordered at the price quoted - needs no extra typing.
    """
    receipt = GoodsReceipt(
        receipt_number=receipt_number,
        purchase_order_id=po.id, vendor_id=po.vendor_id, outlet_id=po.outlet_id,
        receipt_date=date.today(), vendor_invoice_ref=vendor_invoice_ref,
        notes=notes, received_by_id=user_id, status=ReceiptStatus.DRAFT,
    )
    db.add(receipt)
    db.flush()

    by_id = {i.id: i for i in po.items}
    for raw in lines:
        po_item = by_id.get(raw["purchase_order_item_id"])
        if not po_item:
            raise GoodsReceiptError(
                f"Line {raw['purchase_order_item_id']} is not on {po.po_number}"
            )
        qty = to_decimal(raw["quantity"])
        if qty <= 0:
            continue
        item = db.get(Item, po_item.variant_id)
        db.add(GoodsReceiptItem(
            goods_receipt_id=receipt.id,
            purchase_order_item_id=po_item.id,
            item_id=po_item.variant_id,
            quantity=qty,
            uom_id=raw.get("uom_id") or (item.purchase_uom_id if item else None),
            quantity_in_stock_uom=qty,  # recomputed at posting
            unit_cost=to_decimal(raw.get("unit_cost", po_item.unit_cost)),
            note=raw.get("note"),
        ))
    db.flush()
    db.refresh(receipt)
    if not receipt.items:
        raise GoodsReceiptError("No quantities were entered on this receipt")
    return receipt
