"""BOM explosion, costing and availability.

None of these functions mutate inventory. Availability in particular is a
read-only projection - it answers "could we build this?" and must never reserve,
consume or otherwise touch stock, because it is called on every screen refresh.

COSTING SOURCE: ``Item.cost_price`` (the item's standard cost), not the vendor
price. A BOM estimate has to be stable and supplier-independent - which of three
lace vendors gets the order is a procurement decision made later, and letting it
move the recipe's cost would make two people pricing the same garment disagree.
Actual cost is computed from real consumption in Phase 3D onward.
"""

from decimal import Decimal

from sqlalchemy.orm import Session, joinedload

from app.core.money import money, to_decimal
from app.models.bom import Bom, BomComponent, BomStatus, BomVersion
from app.models.inventory import StockLevel
from app.models.product import Item
from app.models.uom import UnitOfMeasure
from app.services.uom import UomConversionError, convert

# A BOM nested deeper than this is far more likely to be a data-entry mistake
# than a real garment. The visited-set already makes cycles impossible; this is
# a second belt against pathological trees.
MAX_BOM_DEPTH = 20


class BomError(ValueError):
    """A BOM rule was violated. Message is user-facing."""


class CircularBomError(BomError):
    pass


# --------------------------------------------------------------------- cycles


def _active_version_for_item(db: Session, item_id: int) -> BomVersion | None:
    return (
        db.query(BomVersion)
        .join(Bom, Bom.id == BomVersion.bom_id)
        .filter(Bom.item_id == item_id, BomVersion.status == BomStatus.ACTIVE)
        .first()
    )


def assert_no_cycle(db: Session, parent_item_id: int, component_item_id: int) -> None:
    """Refuse a component whose own BOM tree already contains the parent.

    Called before a component is added. Walks the candidate's subtree looking for
    the parent: if adding Blouse to Lehenga, and Blouse (directly or through its
    own components) requires Lehenga, that closes a loop and explosion would
    never terminate.
    """
    if parent_item_id == component_item_id:
        raise CircularBomError("An item cannot be a component of itself")

    seen: set[int] = set()
    stack = [component_item_id]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        if current == parent_item_id:
            raise CircularBomError(
                "That would create a circular bill of materials: the component "
                "already requires this item further down its own tree."
            )
        version = _active_version_for_item(db, current)
        if version:
            stack.extend(c.item_id for c in version.components)


# ------------------------------------------------------------------ explosion


def explode(
    db: Session,
    version: BomVersion,
    quantity: Decimal | int | float | str = Decimal("1"),
    *,
    _depth: int = 0,
    _path: tuple[int, ...] = (),
) -> list[dict]:
    """Flatten a BOM into leaf material requirements.

    Scaling: a component's requirement is

        component.quantity
          x (requested_quantity / version.output_quantity)
          x (1 + scrap_pct / 100)

    so a BOM whose batch yields 2 panels asks for half the material per panel.

    A component that is itself manufactured (has an ACTIVE BOM) is recursed into
    rather than being reported as a requirement, so the result is the raw
    materials actually drawn from stock. Semi-finished levels are reported too,
    flagged ``is_subassembly``, because production still wants to see them.
    """
    if _depth > MAX_BOM_DEPTH:
        raise CircularBomError(
            f"Bill of materials nests deeper than {MAX_BOM_DEPTH} levels - this is "
            "almost certainly a data-entry error."
        )

    requested = to_decimal(quantity)
    batch = to_decimal(version.output_quantity) or Decimal("1")
    scale = requested / batch

    rows: list[dict] = []
    for component in version.components:
        gross = component.quantity * (Decimal("1") + component.scrap_pct / Decimal("100"))
        required = gross * scale

        child = _active_version_for_item(db, component.item_id)
        if child and component.item_id not in _path:
            rows.append({
                "item_id": component.item_id,
                "item": component.item,
                "uom_id": component.uom_id,
                "quantity": required,
                "net_quantity": component.quantity * scale,
                "scrap_pct": component.scrap_pct,
                "is_optional": component.is_optional,
                "is_subassembly": True,
                "level": _depth,
            })
            rows.extend(
                explode(db, child, required, _depth=_depth + 1, _path=_path + (component.item_id,))
            )
        else:
            rows.append({
                "item_id": component.item_id,
                "item": component.item,
                "uom_id": component.uom_id,
                "quantity": required,
                "net_quantity": component.quantity * scale,
                "scrap_pct": component.scrap_pct,
                "is_optional": component.is_optional,
                "is_subassembly": False,
                "level": _depth,
            })
    return rows


# -------------------------------------------------------------------- costing


def _unit_cost_in(db: Session, item: Item, uom_id: int) -> Decimal:
    """Item standard cost, expressed per unit of `uom_id`.

    ``cost_price`` is per the item's stock UoM, so a BOM line in centimetres has
    to be costed at the per-centimetre rate, not the per-metre one.
    """
    cost = to_decimal(item.cost_price)
    if not item.stock_uom_id or item.stock_uom_id == uom_id:
        return cost
    stock_uom = db.get(UnitOfMeasure, item.stock_uom_id)
    line_uom = db.get(UnitOfMeasure, uom_id)
    if not stock_uom or not line_uom:
        return cost
    try:
        # One line-unit is this many stock-units; cost scales the same way.
        per_line_unit = convert(db, Decimal("1"), line_uom, stock_uom, item_id=item.id)
    except UomConversionError:
        return cost
    return cost * per_line_unit


def cost_version(
    db: Session, version: BomVersion, quantity: Decimal | int | float | str = Decimal("1")
) -> dict:
    """Estimated material cost, all in Decimal - no float anywhere."""
    lines = []
    total = Decimal("0")
    for row in explode(db, version, quantity):
        if row["is_subassembly"]:
            # Its own components are already in the list; costing it too would
            # double-count.
            continue
        item = row["item"]
        unit_cost = _unit_cost_in(db, item, row["uom_id"])
        line_total = money(unit_cost * row["quantity"])
        total += line_total
        lines.append({
            "item_id": row["item_id"],
            "sku": item.sku,
            "name": item.resolved_name,
            "quantity": row["quantity"],
            "uom_id": row["uom_id"],
            "unit_cost": money(unit_cost),
            "line_cost": line_total,
            "is_optional": row["is_optional"],
        })
    return {"lines": lines, "total_cost": money(total)}


# --------------------------------------------------------------- availability


def availability(
    db: Session,
    version: BomVersion,
    quantity: Decimal | int | float | str = Decimal("1"),
    *,
    outlet_id: int | None = None,
) -> list[dict]:
    """Required vs on-hand per material. Read-only - touches no inventory.

    ``reserved`` is reported as 0 for now: reservations arrive in Phase 3D. The
    field exists here so the shape of this response does not change when they do,
    and so the frontend can already render the column.
    """
    stock_q = db.query(StockLevel.variant_id, StockLevel.quantity)
    if outlet_id:
        stock_q = stock_q.filter(StockLevel.outlet_id == outlet_id)
    on_hand: dict[int, Decimal] = {}
    for variant_id, qty in stock_q.all():
        on_hand[variant_id] = on_hand.get(variant_id, Decimal("0")) + to_decimal(qty)

    # Several BOM lines can reference the same material; aggregate before
    # comparing to stock, or each line looks satisfiable on its own while the
    # order as a whole is short.
    needed: dict[int, dict] = {}
    for row in explode(db, version, quantity):
        if row["is_subassembly"]:
            continue
        entry = needed.setdefault(row["item_id"], {
            "item": row["item"], "uom_id": row["uom_id"],
            "required": Decimal("0"), "is_optional": row["is_optional"],
        })
        entry["required"] += row["quantity"]

    out = []
    for item_id, entry in needed.items():
        item = entry["item"]
        required = entry["required"]

        # Stock is held in the item's stock UoM; the BOM line may not be.
        required_in_stock_uom = required
        if item.stock_uom_id and item.stock_uom_id != entry["uom_id"]:
            line_uom = db.get(UnitOfMeasure, entry["uom_id"])
            stock_uom = db.get(UnitOfMeasure, item.stock_uom_id)
            if line_uom and stock_uom:
                try:
                    required_in_stock_uom = convert(
                        db, required, line_uom, stock_uom, item_id=item_id
                    )
                except UomConversionError:
                    required_in_stock_uom = required

        have = on_hand.get(item_id, Decimal("0"))
        reserved = Decimal("0")  # Phase 3D
        available = have - reserved
        shortage = required_in_stock_uom - available
        out.append({
            "item_id": item_id,
            "sku": item.sku,
            "name": item.resolved_name,
            "required": required_in_stock_uom,
            "uom_id": item.stock_uom_id or entry["uom_id"],
            "on_hand": have,
            "reserved": reserved,
            "available": available,
            "shortage": shortage if shortage > 0 else Decimal("0"),
            "suggested_purchase_qty": shortage if shortage > 0 else Decimal("0"),
            "is_available": shortage <= 0,
            "is_optional": entry["is_optional"],
        })
    return sorted(out, key=lambda r: (r["is_available"], r["sku"]))


# ------------------------------------------------------------------ lifecycle


def validate_component_uom(db: Session, item: Item, uom_id: int) -> None:
    """A BOM line's unit must be reconcilable with how the item is stocked."""
    if not item.stock_uom_id or item.stock_uom_id == uom_id:
        return
    line_uom = db.get(UnitOfMeasure, uom_id)
    stock_uom = db.get(UnitOfMeasure, item.stock_uom_id)
    if not line_uom or not stock_uom:
        raise BomError("Unit of measure not found")
    try:
        convert(db, Decimal("1"), line_uom, stock_uom, item_id=item.id)
    except UomConversionError as e:
        raise BomError(str(e)) from e


def find_duplicate_components(components: list[BomComponent]) -> list[dict]:
    """Same item listed more than once. Reported, never auto-merged.

    Two lines for the same lace may be deliberate - different notes, different
    substitutes, different stages of the garment - so this warns and lets the
    user decide rather than silently summing them.
    """
    by_item: dict[tuple[int, int], list[BomComponent]] = {}
    for c in components:
        by_item.setdefault((c.item_id, c.uom_id), []).append(c)
    return [
        {
            "item_id": item_id,
            "uom_id": uom_id,
            "count": len(rows),
            "total_quantity": sum((r.quantity for r in rows), Decimal("0")),
            "component_ids": [r.id for r in rows],
        }
        for (item_id, uom_id), rows in by_item.items()
        if len(rows) > 1
    ]


def assert_editable(version: BomVersion) -> None:
    if version.is_locked:
        raise BomError(
            f"Version {version.version_no} has been used by production and can never be "
            "changed. Create a new version instead."
        )
    if version.status != BomStatus.DRAFT:
        raise BomError(
            f"Version {version.version_no} is {version.status.value} and cannot be edited. "
            "Create a new version to make changes."
        )


def next_version_no(db: Session, bom_id: int) -> int:
    highest = (
        db.query(BomVersion.version_no)
        .filter(BomVersion.bom_id == bom_id)
        .order_by(BomVersion.version_no.desc())
        .first()
    )
    return (highest[0] + 1) if highest else 1


def copy_components(db: Session, source: BomVersion, target: BomVersion) -> None:
    """Carry a version's lines forward into a new draft, substitutes included.

    This is what makes "edit an active BOM" safe: the user gets an editable copy
    and the original stays exactly as production saw it.
    """
    from app.models.bom import BomComponentSubstitute

    for component in source.components:
        clone = BomComponent(
            bom_version_id=target.id,
            item_id=component.item_id,
            quantity=component.quantity,
            uom_id=component.uom_id,
            scrap_pct=component.scrap_pct,
            is_optional=component.is_optional,
            sequence=component.sequence,
            notes=component.notes,
        )
        db.add(clone)
        db.flush()
        for sub in component.substitutes:
            db.add(BomComponentSubstitute(
                bom_component_id=clone.id, item_id=sub.item_id,
                priority=sub.priority, notes=sub.notes,
            ))


def activate(db: Session, version: BomVersion) -> None:
    """Promote a draft to ACTIVE, archiving whichever version it replaces."""
    if version.status == BomStatus.ACTIVE:
        return
    if version.status == BomStatus.ARCHIVED:
        raise BomError(
            f"Version {version.version_no} is archived. Copy it to a new draft to reuse it."
        )
    if not version.components:
        raise BomError("A bill of materials needs at least one component before it can be activated")

    current = (
        db.query(BomVersion)
        .filter(BomVersion.bom_id == version.bom_id, BomVersion.status == BomStatus.ACTIVE)
        .first()
    )
    if current:
        current.status = BomStatus.ARCHIVED
        db.flush()  # release the partial unique index before claiming it
    version.status = BomStatus.ACTIVE
    db.flush()
