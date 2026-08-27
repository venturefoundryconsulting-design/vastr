"""Production order planning and output: requirements, availability, state machine.

INVENTORY BOUNDARY. Everything up to and including ``availability`` is read-only
with respect to stock - that was the Phase 3C guarantee and it still holds, which
is what ``test_inventory_is_never_touched`` asserts across the planning
lifecycle. Phase 3E added exactly one writer at the bottom of this module:
``record_output``, which puts manufactured goods into stock through
``apply_stock_delta``. Material reservation and issue live in
``app.services.material_flow``.

If you add a function here, it belongs above the output section and must not
touch stock.

PERFORMANCE: the naive approach - re-running app.services.bom.explode and then
resolving each row's item, stock and unit one at a time - is O(n) queries per
component, which on a 500-line BOM is thousands of round trips. Everything here
batch-loads instead: one query for the whole BOM tree, one for every item, one
for stock, one for units.
"""

from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.money import to_decimal
from app.models.bom import Bom, BomComponent, BomStatus, BomVersion
from app.models.inventory import StockLevel
from app.models.product import Item
from app.models.production import (
    ALLOWED_TRANSITIONS,
    RECALCULABLE,
    MaterialAvailability,
    OrderAvailability,
    ProductionOrder,
    ProductionOrderMaterial,
    ProductionStatus,
)
from app.models.uom import UnitOfMeasure
from app.services.bom import MAX_BOM_DEPTH, CircularBomError
from app.services.uom import UomConversionError, convert


class ProductionError(ValueError):
    """A production rule was violated. Message is user-facing."""


class InvalidTransition(ProductionError):
    pass


# --------------------------------------------------------------- state machine


def can_transition(current: ProductionStatus, target: ProductionStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


def assert_transition(current: ProductionStatus, target: ProductionStatus) -> None:
    if current == target:
        raise InvalidTransition(f"This production order is already {target.value}")
    if not can_transition(current, target):
        allowed = ALLOWED_TRANSITIONS.get(current, set())
        if not allowed:
            raise InvalidTransition(
                f"A {current.value} production order is final and cannot change state."
            )
        raise InvalidTransition(
            f"Cannot go from {current.value} to {target.value}. "
            f"From {current.value} you can move to: {', '.join(sorted(s.value for s in allowed))}."
        )


# ------------------------------------------------------------ BOM explosion


class _BomTree:
    """Every active BOM version and its components, loaded in two queries.

    Built once per calculation and walked in memory. The alternative - asking
    the database for each component's own BOM as the walk descends - is the N+1
    this class exists to avoid.
    """

    def __init__(self, db: Session):
        versions = (
            db.query(BomVersion)
            .join(Bom, Bom.id == BomVersion.bom_id)
            .filter(BomVersion.status == BomStatus.ACTIVE)
            .options(joinedload(BomVersion.bom))
            .all()
        )
        self.version_by_item: dict[int, BomVersion] = {v.bom.item_id: v for v in versions}
        version_ids = [v.id for v in versions]
        components = (
            db.query(BomComponent)
            .filter(BomComponent.bom_version_id.in_(version_ids))
            .order_by(BomComponent.sequence)
            .all()
            if version_ids
            else []
        )
        self.components_by_version: dict[int, list[BomComponent]] = {}
        for c in components:
            self.components_by_version.setdefault(c.bom_version_id, []).append(c)

    def components_of(self, version: BomVersion) -> list[BomComponent]:
        # A version being explicitly explored may not be the ACTIVE one (a
        # production order can hold an older, archived version), so fall back to
        # its own loaded collection rather than assuming the cache has it.
        if version.id in self.components_by_version:
            return self.components_by_version[version.id]
        return list(version.components)

    def active_for_item(self, item_id: int) -> BomVersion | None:
        return self.version_by_item.get(item_id)


def explode_requirements(
    db: Session,
    version: BomVersion,
    quantity: Decimal,
    *,
    tree: _BomTree | None = None,
) -> list[dict]:
    """Flatten a BOM version into requirement rows, recursing into sub-assemblies.

    Returns rows carrying base (net), planned (net + wastage), the per-unit
    figure, depth and parent - enough to answer "why do I need 45 m of silk?"
    without re-deriving anything.

    Sub-assembly rows are included but marked, because their own components are
    also in the list: counting both would double-count. 10 lehengas needing 1
    blouse each, where a blouse needs 2 m of fabric, yields 10 blouses and 20 m
    of fabric - not 30 of anything.
    """
    tree = tree or _BomTree(db)
    rows: list[dict] = []

    def walk(v: BomVersion, qty: Decimal, depth: int, parent_item_id: int | None,
             path: tuple[int, ...]) -> None:
        if depth > MAX_BOM_DEPTH:
            raise CircularBomError(
                f"Bill of materials nests deeper than {MAX_BOM_DEPTH} levels."
            )
        batch = to_decimal(v.output_quantity) or Decimal("1")
        scale = qty / batch

        for component in tree.components_of(v):
            per_unit = to_decimal(component.quantity)
            base = per_unit * scale
            planned = base * (Decimal("1") + to_decimal(component.scrap_pct) / Decimal("100"))

            child = tree.active_for_item(component.item_id)
            is_sub = bool(child) and component.item_id not in path

            rows.append({
                "item_id": component.item_id,
                "bom_component_id": component.id,
                "quantity_per_unit": per_unit,
                "base_quantity": base,
                "scrap_pct": to_decimal(component.scrap_pct),
                "planned_quantity": planned,
                "uom_id": component.uom_id,
                "level": depth,
                "parent_item_id": parent_item_id,
                "is_optional": component.is_optional,
                "is_subassembly": is_sub,
            })

            if is_sub:
                # The sub-assembly's own children scale off its planned quantity,
                # so expected wastage at the parent level pulls through.
                walk(child, planned, depth + 1, component.item_id, path + (component.item_id,))

    walk(version, to_decimal(quantity), 0, None, ())
    return rows


# ------------------------------------------------------------ snapshot build


def rebuild_materials(db: Session, order: ProductionOrder) -> None:
    """Re-derive the requirement snapshot from the BOM. DRAFT/PLANNED only.

    Refused once released, because the snapshot is what the shop floor was told
    to pull and Phase 3D will already be tracking issue against these rows.
    """
    if order.status not in RECALCULABLE:
        raise ProductionError(
            f"Material requirements are fixed once a production order is "
            f"{order.status.value}. Cancel it and create a new one to change the plan."
        )
    if not order.bom_version_id:
        return

    version = db.get(BomVersion, order.bom_version_id)
    if not version:
        raise ProductionError("The bill of materials version for this order no longer exists")

    for existing in list(order.materials):
        db.delete(existing)
    db.flush()

    rows = explode_requirements(db, version, to_decimal(order.planned_quantity))
    for i, r in enumerate(rows):
        db.add(ProductionOrderMaterial(
            production_order_id=order.id, sequence=i,
            item_id=r["item_id"], bom_component_id=r["bom_component_id"],
            quantity_per_unit=r["quantity_per_unit"], base_quantity=r["base_quantity"],
            scrap_pct=r["scrap_pct"], planned_quantity=r["planned_quantity"],
            uom_id=r["uom_id"], level=r["level"], parent_item_id=r["parent_item_id"],
            is_optional=r["is_optional"], is_subassembly=r["is_subassembly"],
        ))
    db.flush()


# ------------------------------------------------------------- availability


def _reserved_by_item(db: Session, location_id: int | None) -> dict[int, Decimal]:
    """Quantities already committed to other production orders.

    Phase 3D introduces stock_reservations; until then nothing is reserved and
    this is uniformly zero. It exists as a seam so that `available = on_hand -
    reserved` is written correctly *now* and 3D only has to fill in the query -
    rather than 3D having to hunt down every place that assumed on_hand.
    """
    return {}


def availability(
    db: Session, order: ProductionOrder, *, location_id: int | None = None
) -> dict:
    """Required vs available per material. Touches no inventory.

    Batch-loads items, stock and units, so cost is a handful of queries
    regardless of how many components the order has.
    """
    materials = list(order.materials)
    loc = location_id if location_id is not None else order.location_id

    real = [m for m in materials if not m.is_subassembly]
    item_ids = {m.item_id for m in materials} | {
        m.parent_item_id for m in materials if m.parent_item_id
    }
    uom_ids = {m.uom_id for m in materials}

    items: dict[int, Item] = {}
    if item_ids:
        for it in db.query(Item).filter(Item.id.in_(item_ids)).all():
            items[it.id] = it
            if it.stock_uom_id:
                uom_ids.add(it.stock_uom_id)

    uoms: dict[int, UnitOfMeasure] = {}
    if uom_ids:
        uoms = {u.id: u for u in db.query(UnitOfMeasure).filter(UnitOfMeasure.id.in_(uom_ids)).all()}

    on_hand: dict[int, Decimal] = {}
    if item_ids:
        q = db.query(StockLevel.variant_id, func.sum(StockLevel.quantity)).filter(
            StockLevel.variant_id.in_(item_ids)
        )
        if loc:
            q = q.filter(StockLevel.outlet_id == loc)
        for variant_id, qty in q.group_by(StockLevel.variant_id).all():
            on_hand[variant_id] = to_decimal(qty)

    reserved_map = _reserved_by_item(db, loc)

    # The same material can be pulled in by several BOM lines (and at several
    # levels). Aggregate before comparing to stock, or each line looks
    # satisfiable while the order as a whole is short.
    agg: dict[int, dict] = {}
    for m in real:
        entry = agg.setdefault(m.item_id, {
            "item_id": m.item_id, "uom_id": m.uom_id,
            "base": Decimal("0"), "planned": Decimal("0"),
            "is_optional": m.is_optional, "lines": [],
        })
        entry["base"] += to_decimal(m.base_quantity)
        entry["planned"] += to_decimal(m.planned_quantity)
        entry["is_optional"] = entry["is_optional"] and m.is_optional
        entry["lines"].append(m)

    out = []
    for item_id, entry in agg.items():
        item = items.get(item_id)
        line_uom = uoms.get(entry["uom_id"])
        stock_uom = uoms.get(item.stock_uom_id) if item and item.stock_uom_id else None

        status = MaterialAvailability.AVAILABLE
        note = None
        required = entry["planned"]

        if not item:
            status, note = MaterialAvailability.INVALID, "Item no longer exists"
        elif not item.is_stocked:
            status, note = MaterialAvailability.NOT_STOCKED, "Not tracked in inventory"
        elif stock_uom and line_uom and stock_uom.id != line_uom.id:
            # Requirements are expressed in the BOM's unit; stock is held in the
            # item's. Compare like with like or the numbers are nonsense.
            try:
                required = convert(db, entry["planned"], line_uom, stock_uom, item_id=item_id)
            except UomConversionError as e:
                status, note = MaterialAvailability.INVALID, str(e)

        have = on_hand.get(item_id, Decimal("0"))
        reserved = reserved_map.get(item_id, Decimal("0"))
        available = have - reserved
        shortage = required - available

        if status == MaterialAvailability.AVAILABLE:
            if available >= required:
                status = MaterialAvailability.AVAILABLE
            elif available > 0:
                status = MaterialAvailability.PARTIAL
            else:
                status = MaterialAvailability.SHORT

        out.append({
            "item_id": item_id,
            "sku": item.sku if item else "?",
            "name": item.resolved_name if item else "(missing item)",
            "base_quantity": entry["base"],
            "expected_wastage": entry["planned"] - entry["base"],
            "planned_quantity": entry["planned"],
            "required": required,
            "uom_id": (stock_uom.id if stock_uom else entry["uom_id"]),
            "uom_code": (stock_uom.code if stock_uom else (line_uom.code if line_uom else None)),
            "on_hand": have,
            "reserved": reserved,
            "available": available,
            "shortage": shortage if shortage > 0 else Decimal("0"),
            "suggested_purchase_qty": shortage if shortage > 0 else Decimal("0"),
            "status": status,
            "note": note,
            "is_optional": entry["is_optional"],
        })

    out.sort(key=lambda r: (r["status"] == MaterialAvailability.AVAILABLE, r["sku"]))

    required_lines = [r for r in out if not r["is_optional"]]
    if any(r["status"] == MaterialAvailability.INVALID for r in required_lines):
        overall = OrderAvailability.INVALID_MATERIAL
    elif any(r["status"] == MaterialAvailability.SHORT for r in required_lines):
        overall = OrderAvailability.MATERIAL_SHORTAGE
    elif any(r["status"] == MaterialAvailability.PARTIAL for r in required_lines):
        overall = OrderAvailability.PARTIAL_MATERIAL
    else:
        overall = OrderAvailability.READY

    return {"overall": overall, "lines": out}


def trace(db: Session, order: ProductionOrder, item_id: int) -> list[dict]:
    """Explain where a requirement came from, level by level.

    "45 m of silk" becomes: 10 lehengas -> BOM V2 -> 4.5 m per unit -> 45 m. For
    multi-level orders the chain walks back up through each parent.
    """
    items = {
        i.id: i for i in db.query(Item).filter(
            Item.id.in_({m.item_id for m in order.materials}
                        | {m.parent_item_id for m in order.materials if m.parent_item_id}
                        | {order.item_id})
        ).all()
    }
    steps = []
    for m in order.materials:
        if m.item_id != item_id:
            continue
        chain = []
        cursor = m
        guard = 0
        while cursor is not None and guard < MAX_BOM_DEPTH:
            guard += 1
            parent = items.get(cursor.parent_item_id) if cursor.parent_item_id else items.get(order.item_id)
            chain.append({
                "level": cursor.level,
                "parent_sku": parent.sku if parent else None,
                "parent_name": parent.resolved_name if parent else None,
                "quantity_per_unit": cursor.quantity_per_unit,
                "base_quantity": cursor.base_quantity,
                "scrap_pct": cursor.scrap_pct,
                "planned_quantity": cursor.planned_quantity,
            })
            if not cursor.parent_item_id:
                break
            cursor = next(
                (x for x in order.materials
                 if x.item_id == cursor.parent_item_id and x.level == cursor.level - 1),
                None,
            )
        steps.append(list(reversed(chain)))
    return steps


# ------------------------------------------------------------------- output


def record_output(
    db: Session,
    order: ProductionOrder,
    quantity: Decimal | int | float | str,
    *,
    user_id: int | None = None,
    location_id: int | None = None,
    note: str | None = None,
):
    """Put manufactured goods into stock and advance the order's progress.

    The mirror of material issue: writes one PRODUCTION_OUTPUT ledger row through
    the same chokepoint, so finished stock is as explainable as the material that
    made it.

    Status handling deliberately distinguishes two cases:

      * produced < planned  -> PARTIALLY_COMPLETED, and it *stays* there. Stopping
        short is a decision someone must make explicitly via close-short, which
        records who and why.
      * produced == planned -> COMPLETED. Nothing is being abandoned, so there is
        no judgement to record; auto-completing loses no information. The rule
        being protected is "never silently close *short*".
    """
    from app.models.inventory import MovementType
    from app.models.production_output import ProductionOutput
    from app.services.inventory import apply_stock_delta, get_or_create_stock_level

    if order.status not in {
        ProductionStatus.IN_PROGRESS,
        ProductionStatus.PARTIALLY_COMPLETED,
        ProductionStatus.RELEASED,
    }:
        raise ProductionError(
            f"Output can only be recorded for a released or in-progress order. "
            f"This one is {order.status.value}."
        )

    qty = to_decimal(quantity)
    if qty <= 0:
        raise ProductionError("Output quantity must be greater than zero")

    loc = location_id or order.location_id

    # Same lock discipline as material flow: take the stock row lock, then
    # re-read the order's progress under it rather than trusting the in-session
    # copy, which was loaded before the lock.
    get_or_create_stock_level(db, order.item_id, loc)
    db.flush()
    db.refresh(order)

    produced = to_decimal(order.produced_quantity)
    cancelled = to_decimal(order.cancelled_quantity)
    planned = to_decimal(order.planned_quantity)

    if produced + cancelled + qty > planned:
        remaining = planned - produced - cancelled
        raise ProductionError(
            f"Cannot record {qty}: this order plans {planned}, {produced} is already produced "
            f"and {cancelled} cancelled, leaving {remaining}."
        )

    movement = apply_stock_delta(
        db,
        variant_id=order.item_id,
        outlet_id=loc,
        quantity_delta=qty,
        movement_type=MovementType.PRODUCTION_OUTPUT,
        reference_type="production_order",
        reference_id=order.id,
        note=f"Output from {order.po_number}",
        created_by_id=user_id,
    )

    record = ProductionOutput(
        production_order_id=order.id, item_id=order.item_id, location_id=loc,
        quantity=qty, uom_id=order.uom_id, stock_movement_id=movement.id,
        note=note, produced_by_id=user_id,
    )
    db.add(record)

    order.produced_quantity = produced + qty
    if order.actual_start is None:
        from datetime import datetime, timezone
        order.actual_start = datetime.now(timezone.utc)

    if order.produced_quantity >= planned:
        order.status = ProductionStatus.COMPLETED
        from datetime import datetime, timezone
        order.actual_completion = datetime.now(timezone.utc)
    else:
        order.status = ProductionStatus.PARTIALLY_COMPLETED

    db.flush()
    return record


def complete_order(db: Session, order: ProductionOrder) -> None:
    """Explicitly close an order that has met its planned quantity.

    Refuses below plan: stopping short is close-short, which demands a reason.
    """
    produced = to_decimal(order.produced_quantity)
    planned = to_decimal(order.planned_quantity)
    if produced < planned:
        raise ProductionError(
            f"Only {produced} of {planned} has been produced. Record the remaining output, "
            f"or close the order short with a reason for the {planned - produced} not made."
        )
    assert_transition(order.status, ProductionStatus.COMPLETED)
    order.status = ProductionStatus.COMPLETED
