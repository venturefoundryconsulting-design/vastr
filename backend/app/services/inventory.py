from sqlalchemy.orm import Session

from app.models.inventory import MovementType, StockLevel, StockMovement


def get_or_create_stock_level(db: Session, variant_id: int, outlet_id: int) -> StockLevel:
    level = (
        db.query(StockLevel)
        .filter(StockLevel.variant_id == variant_id, StockLevel.outlet_id == outlet_id)
        .with_for_update()
        .first()
    )
    if not level:
        level = StockLevel(variant_id=variant_id, outlet_id=outlet_id, quantity=0)
        db.add(level)
        db.flush()
    return level


def apply_stock_delta(
    db: Session,
    *,
    variant_id: int,
    outlet_id: int,
    quantity_delta: int,
    movement_type: MovementType,
    reference_type: str | None = None,
    reference_id: int | None = None,
    note: str | None = None,
    created_by_id: int | None = None,
) -> StockMovement:
    """Adjusts on-hand quantity for a variant at an outlet and writes an audit movement.

    Positive quantity_delta = stock in, negative = stock out. Callers are
    responsible for committing the surrounding transaction.
    """
    level = get_or_create_stock_level(db, variant_id, outlet_id)
    level.quantity += quantity_delta

    movement = StockMovement(
        variant_id=variant_id,
        outlet_id=outlet_id,
        movement_type=movement_type,
        quantity_delta=quantity_delta,
        reference_type=reference_type,
        reference_id=reference_id,
        note=note,
        created_by_id=created_by_id,
    )
    db.add(movement)
    db.flush()
    return movement
