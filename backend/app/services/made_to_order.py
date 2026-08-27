"""Customer orders: confirmation, production spawn, readiness and delivery.

The one rule worth stating plainly: **delivery goes through the ordinary POS
checkout**. This module never touches stock itself. It decides *when* a sale
should happen and with which lines; ``app.routers.sales.checkout`` is what
validates availability, writes the ledger row and settles the money - exactly as
it does for an off-the-rack sale.
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.money import money, to_decimal
from app.models.bom import Bom, BomStatus
from app.models.inventory import StockLevel
from app.models.made_to_order import (
    CO_TRANSITIONS,
    CustomerOrder,
    CustomerOrderItem,
    CustomerOrderStatus,
    Fulfilment,
)
from app.models.production import ProductionOrder, ProductionStatus
from app.services import production as prod


class CustomerOrderError(ValueError):
    """A customer order rule was violated. Message is user-facing."""


class InvalidCustomerOrderTransition(CustomerOrderError):
    pass


def assert_transition(current: CustomerOrderStatus, target: CustomerOrderStatus) -> None:
    if current == target:
        raise InvalidCustomerOrderTransition(f"This order is already {target.value}")
    allowed = CO_TRANSITIONS.get(current, set())
    if target not in allowed:
        if not allowed:
            raise InvalidCustomerOrderTransition(
                f"A {current.value} customer order is final and cannot change state."
            )
        raise InvalidCustomerOrderTransition(
            f"Cannot go from {current.value} to {target.value}. From {current.value} you can "
            f"move to: {', '.join(sorted(s.value for s in allowed))}."
        )


# ------------------------------------------------------------- confirmation


def confirm(
    db: Session,
    order: CustomerOrder,
    *,
    user_id: int | None = None,
    numbering=None,
) -> list[ProductionOrder]:
    """Confirm the order and spawn production for every made-to-order line.

    Ready-stock lines spawn nothing - the garment already exists and will simply
    be sold at delivery. Only made-to-order lines create a production order, one
    per line, so a customer commissioning two different garments gets two runs
    that can progress independently.

    Production orders are created in DRAFT: confirming a customer order is a
    commercial decision, releasing material is a production one, and collapsing
    them would have a counter clerk committing stock.
    """
    if not order.items:
        raise CustomerOrderError("Add at least one item before confirming this order")

    assert_transition(order.status, CustomerOrderStatus.CONFIRMED)

    spawned: list[ProductionOrder] = []
    for line in order.items:
        if line.fulfilment != Fulfilment.MADE_TO_ORDER:
            continue
        if line.production_order_id:
            continue  # already spawned; confirming twice must not duplicate

        bom = db.query(Bom).filter(Bom.item_id == line.item_id).first()
        version = None
        if bom:
            version = next((v for v in bom.versions if v.status == BomStatus.ACTIVE), None)
        if not version:
            raise CustomerOrderError(
                f"{line.item.sku if line.item else line.item_id} is made to order but has no "
                "active bill of materials. Create and activate one before confirming."
            )

        po = ProductionOrder(
            po_number=(numbering() if numbering else f"PRD-CO{order.id}-{line.id}"),
            item_id=line.item_id, bom_id=bom.id, bom_version_id=version.id,
            planned_quantity=to_decimal(line.quantity),
            uom_id=line.item.stock_uom_id if line.item else None,
            location_id=order.outlet_id,
            planned_completion=order.promised_date,
            status=ProductionStatus.DRAFT, created_by_id=user_id,
            notes=f"Made to order for {order.order_number}",
        )
        db.add(po)
        db.flush()
        prod.rebuild_materials(db, po)
        # rebuild_materials inserts through the session, so the order's own
        # `materials` collection - loaded empty a moment ago - is stale. Expire it
        # so the caller sees the snapshot it just created.
        db.refresh(po)
        line.production_order_id = po.id
        spawned.append(po)

    order.status = (
        CustomerOrderStatus.IN_PRODUCTION if spawned else CustomerOrderStatus.CONFIRMED
    )
    db.flush()
    return spawned


# ---------------------------------------------------------------- readiness


def readiness(db: Session, order: CustomerOrder) -> dict:
    """Whether every line can actually be handed over.

    A made-to-order line is ready when its production order has produced enough;
    a ready-stock line is ready when the stock is physically there. Both are
    checked, because a customer order that "looks" ready but cannot be invoiced
    is worse than one that says it is waiting.
    """
    lines = []
    for line in order.items:
        needed = to_decimal(line.quantity)
        ready = False
        note = None

        if line.fulfilment == Fulfilment.MADE_TO_ORDER:
            po = line.production_order
            produced = to_decimal(po.produced_quantity) if po else Decimal("0")
            ready = po is not None and produced >= needed
            if not po:
                note = "No production order"
            elif not ready:
                note = f"{produced} of {needed} produced"
        else:
            level = (
                db.query(StockLevel)
                .filter(
                    StockLevel.variant_id == line.item_id,
                    StockLevel.outlet_id == order.outlet_id,
                )
                .first()
            )
            on_hand = to_decimal(level.quantity) if level else Decimal("0")
            ready = on_hand >= needed
            if not ready:
                note = f"{on_hand} in stock, needs {needed}"

        lines.append({
            "item_id": line.item_id,
            "sku": line.item.sku if line.item else None,
            "name": line.item.resolved_name if line.item else None,
            "quantity": needed,
            "fulfilment": line.fulfilment,
            "production_order_id": line.production_order_id,
            "is_ready": ready,
            "note": note,
        })

    return {"all_ready": all(line["is_ready"] for line in lines) if lines else False,
            "lines": lines}


def mark_ready(db: Session, order: CustomerOrder) -> None:
    """Move to READY once everything can be handed over."""
    state = readiness(db, order)
    if not state["all_ready"]:
        waiting = [line["sku"] for line in state["lines"] if not line["is_ready"]]
        raise CustomerOrderError(
            "Not everything is ready yet: " + ", ".join(w for w in waiting if w)
        )
    assert_transition(order.status, CustomerOrderStatus.READY)
    order.status = CustomerOrderStatus.READY
    db.flush()


# ----------------------------------------------------------------- delivery


def sale_payload_lines(order: CustomerOrder) -> list[dict]:
    """The order's lines shaped for the ordinary POS checkout.

    Deliberately produces the same structure a counter sale would: delivery is
    not a special kind of sale, it is a sale whose lines were agreed earlier.
    """
    return [
        {
            "variant_id": line.item_id,
            "quantity": to_decimal(line.quantity),
            "unit_price": to_decimal(line.unit_price),
            "tax_rate": to_decimal(line.tax_rate),
        }
        for line in order.items
    ]


def attach_sale(db: Session, order: CustomerOrder, sale_id: int) -> None:
    """Record the sale that delivered this order and close it out."""
    assert_transition(order.status, CustomerOrderStatus.DELIVERED)
    order.sale_id = sale_id
    order.status = CustomerOrderStatus.DELIVERED
    order.delivered_at = datetime.now(timezone.utc)
    db.flush()


def cancel(db: Session, order: CustomerOrder, reason: str | None = None) -> list[ProductionOrder]:
    """Cancel the order and every production run it spawned.

    Cancelling the production orders is what releases their material
    reservations (Phase 3D, Rule 8) - leaving them open would hold stock for a
    garment nobody is waiting for.
    """
    assert_transition(order.status, CustomerOrderStatus.CANCELLED)
    cancelled: list[ProductionOrder] = []
    for line in order.items:
        po = line.production_order
        if po and po.status not in (
            ProductionStatus.COMPLETED,
            ProductionStatus.CANCELLED,
            ProductionStatus.CLOSED_SHORT,
        ):
            cancelled.append(po)
    order.status = CustomerOrderStatus.CANCELLED
    order.cancel_reason = reason
    db.flush()
    return cancelled


def order_total(order: CustomerOrder) -> Decimal:
    return money(order.total_amount)
