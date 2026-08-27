"""Reserve, issue, consume and return production material.

CONCURRENCY STRATEGY - the whole point of this module.

Every mutating operation takes the **same** lock: the ``stock_levels`` row for
(item, location), via ``get_or_create_stock_level``'s ``SELECT ... FOR UPDATE``.
That one lock serializes reservation against reservation, reservation against
issue, and issue against issue, because all three reason about the same scarce
thing. Reusing the ledger's existing lock rather than inventing a second one is
deliberate: two independent locking schemes over the same rows is how deadlocks
and lost updates get in.

The sequence is always:

    1. lock the stock_levels row
    2. recompute the true position from the database, inside the transaction
    3. validate the request against that freshly-read position
    4. write the transaction row and update the cached aggregates
    5. let the caller commit

Step 2 is non-negotiable. The availability number the frontend rendered a moment
ago is stale by definition; if the server trusted it, two orders could each
reserve the last 10 m.

ATOMICITY: none of these functions commit. They flush so the caller sees ids,
and the router commits once at the end - so a stock movement and its production
record either both land or neither does.
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.money import quantity as q
from app.core.money import to_decimal
from app.models.inventory import MovementType, StockLevel
from app.models.material_flow import (
    HOLDING_STATUSES,
    ProductionMaterialConsumption,
    ProductionMaterialIssue,
    ProductionMaterialReturn,
    ReservationStatus,
    StockReservation,
)
from app.models.production import ProductionOrder, ProductionOrderMaterial, ProductionStatus
from app.services.inventory import apply_stock_delta, get_or_create_stock_level

# Material may only move for an order that is actually live. Planning states have
# nothing to commit against, and terminal states are finished.
ISSUABLE_STATUSES = {
    ProductionStatus.RELEASED,
    ProductionStatus.IN_PROGRESS,
    ProductionStatus.PARTIALLY_COMPLETED,
}
RESERVABLE_STATUSES = ISSUABLE_STATUSES | {ProductionStatus.ON_HOLD}


class MaterialFlowError(ValueError):
    """A material rule was violated. Message is user-facing and quantitative."""


class InsufficientStock(MaterialFlowError):
    pass


# ------------------------------------------------------------------- helpers


def reserved_at_location(db: Session, item_id: int, location_id: int) -> Decimal:
    """Sum of reservations still holding stock for this item at this location.

    Read inside the caller's locked transaction, never cached across one.
    """
    total = (
        db.query(func.coalesce(func.sum(StockReservation.quantity - StockReservation.issued_quantity), 0))
        .filter(
            StockReservation.item_id == item_id,
            StockReservation.location_id == location_id,
            StockReservation.status.in_(HOLDING_STATUSES),
        )
        .scalar()
    )
    return to_decimal(total)


def available_at_location(db: Session, item_id: int, location_id: int) -> Decimal:
    """on_hand - reserved. The quantity a new reservation may draw from."""
    level = (
        db.query(StockLevel)
        .filter(StockLevel.variant_id == item_id, StockLevel.outlet_id == location_id)
        .first()
    )
    on_hand = to_decimal(level.quantity) if level else Decimal("0")
    return on_hand - reserved_at_location(db, item_id, location_id)


def _material(db: Session, order: ProductionOrder, material_id: int) -> ProductionOrderMaterial:
    m = db.get(ProductionOrderMaterial, material_id)
    if not m or m.production_order_id != order.id:
        raise MaterialFlowError("That material line does not belong to this production order")
    if m.is_subassembly:
        raise MaterialFlowError(
            "Sub-assemblies are produced by their own production order, not issued as material"
        )
    return m


def _lock(db: Session, item_id: int, location_id: int) -> StockLevel:
    """Take the ledger's row lock. Everything in this module goes through here."""
    return get_or_create_stock_level(db, item_id, location_id)


def _lock_and_refresh(
    db: Session, material: ProductionOrderMaterial, location_id: int
) -> StockLevel:
    """Take the row lock, then re-read the material's aggregates under it.

    The refresh is the part that is easy to forget and expensive to omit.
    ``material`` was loaded into the session before the lock was acquired, so its
    reserved/issued/consumed/returned columns hold whatever this transaction saw
    at load time. Validating against those is validating against a stale
    snapshot: two concurrent callers would each read "0 consumed" and each decide
    their request fits. Refreshing after the lock is what makes the check honest.
    """
    level = _lock(db, material.item_id, location_id)
    db.flush()
    db.refresh(material)
    return level


# --------------------------------------------------------------- reservation


def reserve(
    db: Session,
    order: ProductionOrder,
    material_id: int,
    requested: Decimal | int | float | str,
    *,
    user_id: int | None = None,
    note: str | None = None,
) -> StockReservation:
    """Commit stock to this order without moving it.

    Writes no ledger row - nothing physically happened. Availability is
    recomputed under lock, so two orders racing for the last 10 m cannot both win.
    """
    if order.status not in RESERVABLE_STATUSES:
        raise MaterialFlowError(
            f"Material can only be reserved for a released order. This one is {order.status.value}."
        )

    material = _material(db, order, material_id)
    qty = q(requested)
    if qty <= 0:
        raise MaterialFlowError("Reservation quantity must be greater than zero")

    location_id = order.location_id

    # 1. lock, 2. recompute, 3. validate - all inside the caller's transaction.
    _lock_and_refresh(db, material, location_id)

    already = to_decimal(material.reserved_quantity)
    outstanding_need = to_decimal(material.planned_quantity) - already
    if qty > outstanding_need:
        raise MaterialFlowError(
            f"Cannot reserve {qty}: this order needs {material.planned_quantity} in total and "
            f"{already} is already reserved, leaving {outstanding_need}."
        )

    available = available_at_location(db, material.item_id, location_id)
    if qty > available:
        raise InsufficientStock(
            f"Cannot reserve {qty} - only {available} is available at this location "
            f"(some stock may already be committed to another production order). "
            f"Reserve {available} instead, or free up stock elsewhere."
        )

    reservation = StockReservation(
        production_order_id=order.id, production_order_material_id=material.id,
        item_id=material.item_id, location_id=location_id,
        quantity=qty, uom_id=material.uom_id,
        status=ReservationStatus.ACTIVE, created_by_id=user_id, note=note,
    )
    db.add(reservation)
    material.reserved_quantity = q(already + qty)
    db.flush()
    return reservation


def release_reservation(
    db: Session,
    reservation: StockReservation,
    *,
    user_id: int | None = None,
    reason: str | None = None,
) -> Decimal:
    """Give back the *unissued* portion. Already-issued material is never released.

    Returns how much was actually freed, which is the outstanding part - the
    issued part has physically gone and releasing it would invent stock.
    """
    if reservation.status not in HOLDING_STATUSES:
        raise MaterialFlowError(
            f"This reservation is already {reservation.status.value} and holds nothing to release"
        )

    _lock(db, reservation.item_id, reservation.location_id)
    db.flush()
    db.refresh(reservation)

    freed = reservation.outstanding
    material = db.get(ProductionOrderMaterial, reservation.production_order_material_id)

    # The issued portion stays recorded against the material; only the promise
    # is withdrawn.
    reservation.quantity = q(reservation.issued_quantity)
    reservation.status = ReservationStatus.RELEASED
    reservation.released_by_id = user_id
    reservation.released_at = datetime.now(timezone.utc)
    reservation.release_reason = reason

    if material:
        material.reserved_quantity = q(to_decimal(material.reserved_quantity) - freed)
    db.flush()
    return freed


def release_all_for_order(
    db: Session, order: ProductionOrder, *, user_id: int | None = None, reason: str | None = None
) -> Decimal:
    """Free every outstanding reservation on an order - used on cancel/close-short.

    This is Rule 8 made real. Issued material is untouched: it is already out of
    the store and comes back through a return, not a release.
    """
    total = Decimal("0")
    rows = (
        db.query(StockReservation)
        .filter(
            StockReservation.production_order_id == order.id,
            StockReservation.status.in_(HOLDING_STATUSES),
        )
        .all()
    )
    for r in rows:
        total += release_reservation(db, r, user_id=user_id, reason=reason)
    return total


# --------------------------------------------------------------------- issue


def issue(
    db: Session,
    order: ProductionOrder,
    material_id: int,
    requested: Decimal | int | float | str,
    *,
    user_id: int | None = None,
    allow_unreserved: bool = False,
    unreserved_reason: str | None = None,
    note: str | None = None,
) -> ProductionMaterialIssue:
    """Hand material to production: physical stock leaves, ledger row written.

    Draws down reservations first, so the promise and the movement stay
    consistent. Issuing more than was reserved requires an explicit permission
    and a reason - it is not silently allowed.
    """
    if order.status not in ISSUABLE_STATUSES:
        raise MaterialFlowError(
            f"Material can only be issued for a released or in-progress order. "
            f"This one is {order.status.value}."
        )

    material = _material(db, order, material_id)
    qty = q(requested)
    if qty <= 0:
        raise MaterialFlowError("Issue quantity must be greater than zero")

    location_id = order.location_id
    level = _lock_and_refresh(db, material, location_id)

    issued_so_far = to_decimal(material.issued_quantity)
    planned = to_decimal(material.planned_quantity)

    # No silent over-issue against the plan.
    if issued_so_far + qty > planned:
        raise MaterialFlowError(
            f"Cannot issue {qty}: this order plans {planned} and {issued_so_far} has already "
            f"been issued, leaving {planned - issued_so_far}."
        )

    reservations = (
        db.query(StockReservation)
        .filter(
            StockReservation.production_order_material_id == material.id,
            StockReservation.status.in_(HOLDING_STATUSES),
        )
        .order_by(StockReservation.id)
        .with_for_update()
        .all()
    )
    reserved_outstanding = sum((r.outstanding for r in reservations), Decimal("0"))

    if qty > reserved_outstanding and not allow_unreserved:
        raise MaterialFlowError(
            f"Cannot issue {qty} - only {reserved_outstanding} is reserved for this material. "
            f"Reserve it first, or issue with the unreserved-issue permission and a reason."
        )
    if qty > reserved_outstanding and not (unreserved_reason or "").strip():
        raise MaterialFlowError("Issuing more than is reserved requires a reason")

    # Physical stock must actually be there, regardless of what is reserved.
    on_hand = to_decimal(level.quantity)
    if qty > on_hand:
        raise InsufficientStock(
            f"Cannot issue {qty} - only {on_hand} is physically in stock at this location."
        )

    # Draw down reservations oldest-first.
    remaining = qty
    first_reservation_id = None
    for r in reservations:
        if remaining <= 0:
            break
        take = min(r.outstanding, remaining)
        if take <= 0:
            continue
        r.issued_quantity = q(to_decimal(r.issued_quantity) + take)
        r.status = (
            ReservationStatus.CONSUMED
            if r.issued_quantity >= r.quantity
            else ReservationStatus.PARTIALLY_ISSUED
        )
        first_reservation_id = first_reservation_id or r.id
        remaining -= take

    movement = apply_stock_delta(
        db,
        variant_id=material.item_id,
        outlet_id=location_id,
        quantity_delta=-qty,
        movement_type=MovementType.PRODUCTION_ISSUE,
        reference_type="production_order",
        reference_id=order.id,
        note=f"Issued to {order.po_number}",
        created_by_id=user_id,
    )

    record = ProductionMaterialIssue(
        production_order_id=order.id, production_order_material_id=material.id,
        reservation_id=first_reservation_id, item_id=material.item_id,
        location_id=location_id, quantity=qty, uom_id=material.uom_id,
        stock_movement_id=movement.id,
        unreserved_reason=unreserved_reason if remaining > 0 or qty > reserved_outstanding else None,
        note=note, issued_by_id=user_id,
    )
    db.add(record)
    material.issued_quantity = q(issued_so_far + qty)
    db.flush()
    return record


# --------------------------------------------------------------- consumption


def consume(
    db: Session,
    order: ProductionOrder,
    material_id: int,
    requested: Decimal | int | float | str,
    *,
    user_id: int | None = None,
    allow_over_consumption: bool = False,
    over_consumption_reason: str | None = None,
    note: str | None = None,
) -> ProductionMaterialConsumption:
    """Record material actually used up. **Moves no stock.**

    The material left inventory when it was issued. Deducting again here would
    double-count, which is the single easiest way to corrupt a manufacturing
    ledger.
    """
    material = _material(db, order, material_id)
    qty = q(requested)
    if qty <= 0:
        raise MaterialFlowError("Consumption quantity must be greater than zero")

    # Same lock as everything else, even though no stock moves: it serializes
    # concurrent consumption against the issued/returned position being read.
    _lock_and_refresh(db, material, order.location_id)

    issued = to_decimal(material.issued_quantity)
    consumed = to_decimal(material.consumed_quantity)
    accounted = to_decimal(material.accounted_quantity)

    # consumed + returned + wasted <= issued. You cannot use what never reached
    # you, and you cannot use what has already been scrapped.
    if accounted + qty > issued:
        raise MaterialFlowError(
            f"Cannot consume {qty}: {issued} was issued and {accounted} is already accounted "
            f"for (consumed, returned or wasted), leaving {issued - accounted} on the floor."
        )

    planned = to_decimal(material.planned_quantity)
    if consumed + qty > planned and not allow_over_consumption:
        raise MaterialFlowError(
            f"Consuming {qty} would take actual consumption to {consumed + qty}, above the "
            f"planned {planned}. Record it with an over-consumption reason to keep the variance."
        )
    if consumed + qty > planned and not (over_consumption_reason or "").strip():
        raise MaterialFlowError("Consuming more than planned requires a reason")

    record = ProductionMaterialConsumption(
        production_order_id=order.id, production_order_material_id=material.id,
        item_id=material.item_id, quantity=qty, uom_id=material.uom_id,
        over_consumption_reason=over_consumption_reason if consumed + qty > planned else None,
        note=note, recorded_by_id=user_id,
    )
    db.add(record)
    material.consumed_quantity = q(consumed + qty)
    db.flush()
    return record


# -------------------------------------------------------------------- return


def return_material(
    db: Session,
    order: ProductionOrder,
    material_id: int,
    requested: Decimal | int | float | str,
    *,
    user_id: int | None = None,
    reason: str | None = None,
    restock: bool = True,
) -> ProductionMaterialReturn:
    """Unused material comes back: a compensating ledger row, never an edit.

    The original issue stays exactly as written. The pair of movements - out at
    issue, back at return - is the audit trail.
    """
    material = _material(db, order, material_id)
    qty = q(requested)
    if qty <= 0:
        raise MaterialFlowError("Return quantity must be greater than zero")

    location_id = order.location_id
    _lock_and_refresh(db, material, location_id)

    issued = to_decimal(material.issued_quantity)
    returned = to_decimal(material.returned_quantity)
    returnable = to_decimal(material.returnable_quantity)

    if qty > returnable:
        raise MaterialFlowError(
            f"Cannot return {qty}: {issued} was issued and "
            f"{material.accounted_quantity} is already accounted for (consumed, returned or "
            f"wasted), so at most {returnable} can come back."
        )

    movement = None
    if restock:
        movement = apply_stock_delta(
            db,
            variant_id=material.item_id,
            outlet_id=location_id,
            quantity_delta=qty,
            movement_type=MovementType.PRODUCTION_RETURN,
            reference_type="production_order",
            reference_id=order.id,
            note=f"Returned from {order.po_number}",
            created_by_id=user_id,
        )

    record = ProductionMaterialReturn(
        production_order_id=order.id, production_order_material_id=material.id,
        item_id=material.item_id, location_id=location_id,
        quantity=qty, uom_id=material.uom_id,
        stock_movement_id=movement.id if movement else None,
        reason=reason, restock=restock, returned_by_id=user_id,
    )
    db.add(record)
    material.returned_quantity = q(returned + qty)
    db.flush()
    return record


# ------------------------------------------------------------- reconciliation


def material_position(db: Session, material: ProductionOrderMaterial) -> dict:
    """Everything a production manager needs about one material line."""
    return {
        "material_id": material.id,
        "item_id": material.item_id,
        "sku": material.item.sku if material.item else None,
        "name": material.item.resolved_name if material.item else None,
        "uom_id": material.uom_id,
        "uom_code": material.uom.code if material.uom else None,
        "planned": to_decimal(material.planned_quantity),
        "reserved": to_decimal(material.reserved_quantity),
        "issued": to_decimal(material.issued_quantity),
        "consumed": to_decimal(material.consumed_quantity),
        "returned": to_decimal(material.returned_quantity),
        "wasted": to_decimal(material.wasted_quantity),
        "remaining_to_reserve": material.remaining_to_reserve,
        "remaining_to_issue": material.remaining_to_issue,
        "returnable": material.returnable_quantity,
        "still_with_production": material.still_with_production,
        "on_hand": _on_hand(db, material.item_id, material.production_order.location_id),
        "available": available_at_location(
            db, material.item_id, material.production_order.location_id
        ),
    }


def _on_hand(db: Session, item_id: int, location_id: int) -> Decimal:
    level = (
        db.query(StockLevel)
        .filter(StockLevel.variant_id == item_id, StockLevel.outlet_id == location_id)
        .first()
    )
    return to_decimal(level.quantity) if level else Decimal("0")
