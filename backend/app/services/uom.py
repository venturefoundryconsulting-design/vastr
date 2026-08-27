"""Unit conversion.

Resolution order when converting a quantity for an item, most specific first:

  1. an item conversion for this item AND this vendor  ("vendor A's roll is 25 m")
  2. an item conversion for this item, any vendor       ("our rolls are 25 m")
  3. the standard factor, if both units share a category (m -> cm)

If none apply, the conversion is refused. Refusing is the point: piece -> meter
is meaningless in general, and silently guessing a factor would corrupt stock.
"""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.money import to_decimal
from app.models.uom import ItemUomConversion, UnitOfMeasure


class UomConversionError(ValueError):
    """Raised when a conversion is not defined. Carries a message intended to be
    shown to a user, not just logged - see the routers' 400 handling."""


def _find_item_conversion(
    db: Session, item_id: int, from_uom_id: int, to_uom_id: int, vendor_id: int | None
) -> Decimal | None:
    """Item-specific factor, or its reciprocal if only the reverse is defined.

    Storing "1 roll = 25 m" implies "1 m = 0.04 roll"; making the caller define
    both directions would be a data-entry trap where the two could disagree.
    """
    q = db.query(ItemUomConversion).filter(
        ItemUomConversion.item_id == item_id,
        ItemUomConversion.is_active.is_(True),
    )
    rows = q.all()

    def pick(vendor):
        forward = [
            r for r in rows
            if r.from_uom_id == from_uom_id and r.to_uom_id == to_uom_id and r.vendor_id == vendor
        ]
        if forward:
            return to_decimal(forward[0].factor)
        reverse = [
            r for r in rows
            if r.from_uom_id == to_uom_id and r.to_uom_id == from_uom_id and r.vendor_id == vendor
        ]
        if reverse and to_decimal(reverse[0].factor) != 0:
            return Decimal("1") / to_decimal(reverse[0].factor)
        return None

    if vendor_id is not None:
        found = pick(vendor_id)
        if found is not None:
            return found
    return pick(None)


def convert(
    db: Session,
    quantity: Decimal | int | float | str,
    from_uom: UnitOfMeasure,
    to_uom: UnitOfMeasure,
    *,
    item_id: int | None = None,
    vendor_id: int | None = None,
) -> Decimal:
    """Convert ``quantity`` from one unit to another. Raises UomConversionError
    if no rule applies."""
    qty = to_decimal(quantity)

    if from_uom.id == to_uom.id:
        return qty

    if item_id is not None:
        factor = _find_item_conversion(db, item_id, from_uom.id, to_uom.id, vendor_id)
        if factor is not None:
            return qty * factor

    if from_uom.category_id == to_uom.category_id:
        # Both are anchored to the same base unit, so the factor is the ratio.
        return qty * to_decimal(from_uom.factor_to_base) / to_decimal(to_uom.factor_to_base)

    raise UomConversionError(
        f"Cannot convert {from_uom.code} to {to_uom.code}: they measure different things "
        f"({from_uom.category.name if from_uom.category else '?'} vs "
        f"{to_uom.category.name if to_uom.category else '?'}). "
        f"Define a conversion on the item itself if this is a packaging rule "
        f"(for example 1 {from_uom.code} = 25 {to_uom.code})."
    )


def to_stock_uom(
    db: Session, item, quantity: Decimal | int | float | str, from_uom: UnitOfMeasure,
    *, vendor_id: int | None = None,
) -> Decimal:
    """Convert a purchase/sales quantity into the item's stock unit.

    This is the function purchasing calls on receipt: a PO for 2 ROLL against an
    item stocked in M becomes 50 M in the ledger, so the ledger only ever holds
    one unit per item.
    """
    if item.stock_uom_id is None:
        # Pre-Phase-2 items with no UoM assigned behave exactly as before.
        return to_decimal(quantity)
    if from_uom is None or from_uom.id == item.stock_uom_id:
        return to_decimal(quantity)
    stock_uom = db.get(UnitOfMeasure, item.stock_uom_id)
    return convert(db, quantity, from_uom, stock_uom, item_id=item.id, vendor_id=vendor_id)


def validate_conversion_pair(from_uom: UnitOfMeasure, to_uom: UnitOfMeasure) -> None:
    """Guard for the admin UI when defining a *standard* conversion.

    Item-level packaging rules deliberately may cross categories, so this is not
    applied to them - only to same-dimension rules like m -> cm.
    """
    if from_uom.category_id != to_uom.category_id:
        raise UomConversionError(
            f"{from_uom.code} and {to_uom.code} measure different things and cannot have a "
            "general conversion. Add it as an item-specific packaging rule instead."
        )
