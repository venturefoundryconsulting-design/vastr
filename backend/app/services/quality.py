"""Quality control, rework and wastage.

MOVES NO INVENTORY. A failed inspection does not un-make a garment, and wastage
does not deduct stock a second time - the material left when it was issued. What
these records add is *why*: which fault, whose work, which reason code. Phase 3H
turns that into cost.
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.money import money, to_decimal
from app.models.production import ProductionOrder, ProductionOrderMaterial
from app.models.quality import (
    DefectCategory,
    ProductionWastage,
    QcResult,
    QualityCheck,
    QualityDefect,
    ReworkOrder,
    ReworkStatus,
)
from app.models.workforce import WorkOrder, WorkOrderStatus


class QualityError(ValueError):
    """A QC or wastage rule was violated. Message is user-facing."""


# ------------------------------------------------------------ quality checks


def record_check(
    db: Session,
    order: ProductionOrder,
    *,
    result: QcResult,
    checked_quantity: Decimal | int | float | str,
    failed_quantity: Decimal | int | float | str = 0,
    work_order_id: int | None = None,
    notes: str | None = None,
    photo_path: str | None = None,
    defects: list[dict] | None = None,
    inspector_id: int | None = None,
) -> QualityCheck:
    """Record an inspection.

    The pass/fail split is stored explicitly rather than inferred from the
    result, because a PARTIAL check is the common case in a boutique - 8 of 10
    fine, 2 to redo - and "how many failed" is what drives rework.
    """
    checked = to_decimal(checked_quantity)
    failed = to_decimal(failed_quantity)

    if checked <= 0:
        raise QualityError("Checked quantity must be greater than zero")
    if failed < 0:
        raise QualityError("Failed quantity cannot be negative")
    if failed > checked:
        raise QualityError(
            f"Cannot fail {failed} of {checked} checked - failures cannot exceed what was inspected."
        )
    if result == QcResult.PASS and failed > 0:
        raise QualityError("A passing check cannot have failures. Record it as partial or fail.")
    if result == QcResult.FAIL and failed <= 0:
        raise QualityError("A failing check must say how many pieces failed.")

    check = QualityCheck(
        production_order_id=order.id, work_order_id=work_order_id, result=result,
        checked_quantity=checked, passed_quantity=checked - failed, failed_quantity=failed,
        notes=notes, photo_path=photo_path, inspector_id=inspector_id,
        checked_at=datetime.now(timezone.utc),
    )
    db.add(check)
    db.flush()

    for d in defects or []:
        category = db.get(DefectCategory, d["defect_category_id"])
        if not category:
            raise QualityError(f"Defect category {d['defect_category_id']} not found")
        db.add(QualityDefect(
            quality_check_id=check.id, defect_category_id=category.id,
            quantity=to_decimal(d.get("quantity", 0)), notes=d.get("notes"),
        ))
    db.flush()
    return check


# -------------------------------------------------------------------- rework


def raise_rework(
    db: Session,
    order: ProductionOrder,
    *,
    quantity: Decimal | int | float | str,
    reason: str,
    quality_check_id: int | None = None,
    work_order_id: int | None = None,
    assigned_tailor_id: int | None = None,
    user_id: int | None = None,
    number: str | None = None,
) -> ReworkOrder:
    """Open corrective work against the original production order.

    Deliberately not a new production order: the fault stays linked to the run
    that caused it, and the boutique's output is not counted twice. If a work
    order is named, it is re-opened into REWORK so the tailor sees it back in
    their queue.
    """
    if not (reason or "").strip():
        raise QualityError("A reason is required to raise rework")
    qty = to_decimal(quantity)
    if qty <= 0:
        raise QualityError("Rework quantity must be greater than zero")

    rework = ReworkOrder(
        rework_number=number or f"RW-{order.id}-{int(datetime.now(timezone.utc).timestamp())}",
        production_order_id=order.id, quality_check_id=quality_check_id,
        work_order_id=work_order_id, assigned_tailor_id=assigned_tailor_id,
        quantity=qty, reason=reason.strip(), status=ReworkStatus.OPEN, created_by_id=user_id,
    )
    db.add(rework)

    if work_order_id:
        from app.services import workforce as wf

        wo = db.get(WorkOrder, work_order_id)
        if wo and wo.status == WorkOrderStatus.COMPLETED:
            wf.send_to_rework(db, wo, reason.strip())
    db.flush()
    return rework


def resolve_rework(db: Session, rework: ReworkOrder) -> None:
    if rework.status in (ReworkStatus.RESOLVED, ReworkStatus.CANCELLED):
        raise QualityError(f"This rework is already {rework.status.value}")
    rework.status = ReworkStatus.RESOLVED
    rework.resolved_at = datetime.now(timezone.utc)
    db.flush()


# ------------------------------------------------------------------ wastage


def record_wastage(
    db: Session,
    order: ProductionOrder,
    material_id: int,
    quantity: Decimal | int | float | str,
    *,
    reason_id: int | None = None,
    work_order_id: int | None = None,
    tailor_id: int | None = None,
    notes: str | None = None,
    user_id: int | None = None,
) -> ProductionWastage:
    """Record material that was issued and will never become product.

    Writes **no** ledger row: the stock left at issue time, and deducting again
    would double-count. What this adds is the reason and the attribution.

    Bounded by the same accounting as consumption and return - you cannot waste
    material that never reached the floor, or that has already been used or sent
    back.
    """
    material = db.get(ProductionOrderMaterial, material_id)
    if not material or material.production_order_id != order.id:
        raise QualityError("That material line does not belong to this production order")

    qty = to_decimal(quantity)
    if qty <= 0:
        raise QualityError("Wastage quantity must be greater than zero")

    # Same lock-then-refresh discipline as material flow: the aggregates were
    # loaded before any lock, so validating against them unrefreshed would let
    # two concurrent records both fit.
    from app.services.inventory import get_or_create_stock_level

    get_or_create_stock_level(db, material.item_id, order.location_id)
    db.flush()
    db.refresh(material)

    issued = to_decimal(material.issued_quantity)
    accounted = to_decimal(material.accounted_quantity)
    if accounted + qty > issued:
        raise QualityError(
            f"Cannot record {qty} as wasted: {issued} was issued and {accounted} is already "
            f"accounted for (consumed, returned or wasted), leaving {issued - accounted}."
        )

    record = ProductionWastage(
        production_order_id=order.id, production_order_material_id=material.id,
        item_id=material.item_id, work_order_id=work_order_id, tailor_id=tailor_id,
        quantity=qty, uom_id=material.uom_id, reason_id=reason_id, notes=notes,
        recorded_by_id=user_id,
    )
    db.add(record)
    material.wasted_quantity = to_decimal(material.wasted_quantity) + qty
    db.flush()
    return record


def wastage_cost(db: Session, order: ProductionOrder) -> Decimal:
    """What the wasted material cost, at the item's standard cost.

    Same costing source as the BOM estimate (Item.cost_price), so a boutique
    comparing planned material cost with actual waste is comparing like with like.
    """
    from app.models.product import Item

    rows = (
        db.query(ProductionWastage.item_id, func.sum(ProductionWastage.quantity))
        .filter(ProductionWastage.production_order_id == order.id)
        .group_by(ProductionWastage.item_id)
        .all()
    )
    if not rows:
        return Decimal("0.00")
    items = {
        i.id: i for i in db.query(Item).filter(Item.id.in_([r[0] for r in rows])).all()
    }
    total = sum(
        (to_decimal(items[item_id].cost_price) * to_decimal(qty)
         for item_id, qty in rows if item_id in items),
        Decimal("0"),
    )
    return money(total)


def wastage_summary(db: Session, order: ProductionOrder) -> list[dict]:
    """Wastage grouped by material, for the production order screen."""
    from app.models.product import Item

    rows = (
        db.query(
            ProductionWastage.item_id,
            func.sum(ProductionWastage.quantity),
            func.count(ProductionWastage.id),
        )
        .filter(ProductionWastage.production_order_id == order.id)
        .group_by(ProductionWastage.item_id)
        .all()
    )
    if not rows:
        return []
    items = {i.id: i for i in db.query(Item).filter(Item.id.in_([r[0] for r in rows])).all()}
    out = []
    for item_id, qty, count in rows:
        item = items.get(item_id)
        out.append({
            "item_id": item_id,
            "sku": item.sku if item else None,
            "name": item.resolved_name if item else None,
            "quantity": to_decimal(qty),
            "entries": count,
            "cost": money(to_decimal(item.cost_price) * to_decimal(qty)) if item else Decimal("0.00"),
        })
    return sorted(out, key=lambda r: r["cost"], reverse=True)
