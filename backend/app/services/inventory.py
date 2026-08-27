from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.money import quantity as q
from app.models.inventory import MovementType, StockLevel, StockMovement


def get_or_create_stock_level(db: Session, variant_id: int, outlet_id: int) -> StockLevel:
    level = (
        db.query(StockLevel)
        .filter(StockLevel.variant_id == variant_id, StockLevel.outlet_id == outlet_id)
        .with_for_update()
        .first()
    )
    if level:
        return level

    # FOR UPDATE locks an existing row - it locks nothing when there isn't one
    # yet, so two concurrent first-touches of the same (item, outlet) can both
    # reach here and both try to INSERT. Whichever commits first wins; the
    # other's INSERT raises IntegrityError on the unique constraint rather than
    # blocking. The fix is to treat that as "someone else just created it": roll
    # back to the savepoint and re-select FOR UPDATE, which now blocks on the
    # winner's still-open transaction exactly as a normal lock would, and
    # returns its row once the winner commits.
    savepoint = db.begin_nested()
    try:
        level = StockLevel(variant_id=variant_id, outlet_id=outlet_id, quantity=Decimal("0"))
        db.add(level)
        db.flush()
        savepoint.commit()
        return level
    except IntegrityError:
        savepoint.rollback()
        return (
            db.query(StockLevel)
            .filter(StockLevel.variant_id == variant_id, StockLevel.outlet_id == outlet_id)
            .with_for_update()
            .one()
        )


def apply_stock_delta(
    db: Session,
    *,
    variant_id: int,
    outlet_id: int,
    quantity_delta: Decimal | int | float | str,
    movement_type: MovementType,
    reference_type: str | None = None,
    reference_id: int | None = None,
    note: str | None = None,
    created_by_id: int | None = None,
) -> StockMovement:
    """Adjusts on-hand quantity for a variant at an outlet and writes an audit movement.

    Positive quantity_delta = stock in, negative = stock out. Callers are
    responsible for committing the surrounding transaction.

    quantity_delta is normalized to 4 dp Decimal on the way in, so callers may
    still pass plain ints (every pre-manufacturing caller does) without the
    stored value drifting from what they meant. The ``with_for_update()`` lock
    taken by get_or_create_stock_level above is what serializes concurrent
    adjustments to the same variant/outlet - it is deliberately unchanged.
    """
    delta = q(quantity_delta)
    level = get_or_create_stock_level(db, variant_id, outlet_id)
    level.quantity = q(level.quantity + delta)

    movement = StockMovement(
        variant_id=variant_id,
        outlet_id=outlet_id,
        movement_type=movement_type,
        quantity_delta=delta,
        reference_type=reference_type,
        reference_id=reference_id,
        note=note,
        created_by_id=created_by_id,
    )
    db.add(movement)
    db.flush()
    return movement
