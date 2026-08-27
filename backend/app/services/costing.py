"""Production costing and manufacturing reports.

    Material cost + Labour cost + Wastage cost = Production cost

ESTIMATED vs ACTUAL, kept apart:

  * **Estimated** is the plan: BOM requirement x standard cost, computed the same
    way Phase 3B costs a BOM, so the two never disagree.
  * **Actual** is what happened: material genuinely consumed, labour genuinely
    booked on completed work orders, material genuinely scrapped.

The variance between them is the number that tells a boutique whether its BOM is
honest, so neither figure is ever back-filled from the other.

COST SOURCE is ``Item.cost_price`` - the item's standard cost - exactly as in
Phase 3B. Vendor prices vary by supplier and are a procurement decision; letting
them move a production cost would make two people costing the same run disagree.
Moving-average costing would be a deliberate future change, applied to both
halves at once.

READ-ONLY. Nothing here writes anything.
"""

from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.money import money, to_decimal
from app.models.material_flow import ProductionMaterialConsumption
from app.models.product import Item
from app.models.production import ProductionOrder, ProductionOrderMaterial, ProductionStatus
from app.models.quality import ProductionWastage, QcResult, QualityCheck, ReworkOrder
from app.models.workforce import WorkOrder, WorkOrderStatus


def _item_costs(db: Session, item_ids: set[int]) -> dict[int, Decimal]:
    """Standard cost per item, batch-loaded."""
    if not item_ids:
        return {}
    return {
        i.id: to_decimal(i.cost_price)
        for i in db.query(Item).filter(Item.id.in_(item_ids)).all()
    }


def order_cost(db: Session, order: ProductionOrder) -> dict:
    """Full cost breakdown for one production order.

    Batch-loads everything: one query for materials, one for consumption, one for
    wastage, one for work orders, one for item costs. A 500-material order costs
    the same handful of round trips as a five-material one.
    """
    materials = [m for m in order.materials if not m.is_subassembly]
    material_ids = {m.id for m in materials}
    item_ids = {m.item_id for m in materials}

    consumed_by_material: dict[int, Decimal] = {}
    if material_ids:
        rows = (
            db.query(
                ProductionMaterialConsumption.production_order_material_id,
                func.sum(ProductionMaterialConsumption.quantity),
            )
            .filter(ProductionMaterialConsumption.production_order_material_id.in_(material_ids))
            .group_by(ProductionMaterialConsumption.production_order_material_id)
            .all()
        )
        consumed_by_material = {mid: to_decimal(q) for mid, q in rows}

    wasted_by_material: dict[int, Decimal] = {}
    if material_ids:
        rows = (
            db.query(
                ProductionWastage.production_order_material_id,
                func.sum(ProductionWastage.quantity),
            )
            .filter(ProductionWastage.production_order_material_id.in_(material_ids))
            .group_by(ProductionWastage.production_order_material_id)
            .all()
        )
        wasted_by_material = {mid: to_decimal(q) for mid, q in rows}

    costs = _item_costs(db, item_ids)

    lines = []
    estimated_material = Decimal("0")
    actual_material = Decimal("0")
    wastage_total = Decimal("0")

    for m in materials:
        unit = costs.get(m.item_id, Decimal("0"))
        planned = to_decimal(m.planned_quantity)
        consumed = consumed_by_material.get(m.id, Decimal("0"))
        wasted = wasted_by_material.get(m.id, Decimal("0"))

        est = money(unit * planned)
        act = money(unit * consumed)
        waste_cost = money(unit * wasted)

        estimated_material += est
        actual_material += act
        wastage_total += waste_cost

        lines.append({
            "material_id": m.id,
            "item_id": m.item_id,
            "sku": m.item.sku if m.item else None,
            "name": m.item.resolved_name if m.item else None,
            "unit_cost": money(unit),
            "planned_quantity": planned,
            "consumed_quantity": consumed,
            "wasted_quantity": wasted,
            "estimated_cost": est,
            "actual_cost": act,
            "wastage_cost": waste_cost,
            "variance": money(act - est),
        })

    # ---- labour ---------------------------------------------------------
    work_orders = db.query(WorkOrder).filter(WorkOrder.production_order_id == order.id).all()
    labour_lines = []
    actual_labour = Decimal("0")
    estimated_labour = Decimal("0")
    for wo in work_orders:
        # Estimated labour prices the whole work order at its frozen rate;
        # actual prices only what was completed. An unstarted stage therefore
        # shows as planned cost with nothing actual against it yet.
        est = money(to_decimal(wo.rate) * to_decimal(wo.quantity))
        act = money(wo.labour_cost)
        if wo.status != WorkOrderStatus.CANCELLED:
            estimated_labour += est
            actual_labour += act
        labour_lines.append({
            "work_order_id": wo.id,
            "wo_number": wo.wo_number,
            "stage_name": wo.stage.name if wo.stage else None,
            "tailor_name": wo.tailor.name if wo.tailor else None,
            "status": wo.status,
            "pay_model": wo.pay_model,
            "rate": money(wo.rate),
            "quantity": to_decimal(wo.quantity),
            "completed_quantity": to_decimal(wo.completed_quantity),
            "hours": to_decimal(wo.hours),
            "estimated_cost": est,
            "actual_cost": act,
        })

    estimated_total = money(estimated_material + estimated_labour)
    actual_total = money(actual_material + actual_labour + wastage_total)

    produced = to_decimal(order.produced_quantity)
    planned_qty = to_decimal(order.planned_quantity)

    return {
        "production_order_id": order.id,
        "po_number": order.po_number,
        "status": order.status,
        "planned_quantity": planned_qty,
        "produced_quantity": produced,
        "estimated_material_cost": money(estimated_material),
        "actual_material_cost": money(actual_material),
        "wastage_cost": money(wastage_total),
        "estimated_labour_cost": money(estimated_labour),
        "actual_labour_cost": money(actual_labour),
        "estimated_total_cost": estimated_total,
        "actual_total_cost": actual_total,
        "variance": money(actual_total - estimated_total),
        # Unit cost is only meaningful once something exists to divide by;
        # reporting "cost per unit" on a run that made nothing would be a
        # division by zero dressed up as a number.
        "estimated_unit_cost": money(estimated_total / planned_qty) if planned_qty else None,
        "actual_unit_cost": money(actual_total / produced) if produced else None,
        "material_lines": lines,
        "labour_lines": labour_lines,
    }


# ------------------------------------------------------------------ reports


def production_summary(db: Session) -> dict:
    """Counts for the manufacturing dashboard, in one grouped query each."""
    by_status = dict(
        db.query(ProductionOrder.status, func.count(ProductionOrder.id))
        .group_by(ProductionOrder.status)
        .all()
    )
    wo_by_status = dict(
        db.query(WorkOrder.status, func.count(WorkOrder.id)).group_by(WorkOrder.status).all()
    )
    open_rework = (
        db.query(func.count(ReworkOrder.id))
        .filter(ReworkOrder.status.in_(["OPEN", "IN_PROGRESS"]))
        .scalar()
    )
    failed_checks = (
        db.query(func.count(QualityCheck.id))
        .filter(QualityCheck.result.in_([QcResult.FAIL, QcResult.PARTIAL]))
        .scalar()
    )
    return {
        "orders_by_status": {
            (s.value if hasattr(s, "value") else str(s)): c for s, c in by_status.items()
        },
        "work_orders_by_status": {
            (s.value if hasattr(s, "value") else str(s)): c for s, c in wo_by_status.items()
        },
        "open_rework": int(open_rework or 0),
        "failed_quality_checks": int(failed_checks or 0),
        "active_orders": sum(
            c for s, c in by_status.items()
            if s in (ProductionStatus.RELEASED, ProductionStatus.IN_PROGRESS,
                     ProductionStatus.PARTIALLY_COMPLETED)
        ),
    }


def wastage_report(db: Session, *, limit: int = 50) -> list[dict]:
    """Wastage by material across all orders - what the boutique keeps losing."""
    rows = (
        db.query(
            ProductionWastage.item_id,
            func.sum(ProductionWastage.quantity),
            func.count(ProductionWastage.id),
        )
        .group_by(ProductionWastage.item_id)
        .all()
    )
    if not rows:
        return []
    costs = _item_costs(db, {r[0] for r in rows})
    items = {i.id: i for i in db.query(Item).filter(Item.id.in_(costs)).all()}
    out = [
        {
            "item_id": item_id,
            "sku": items[item_id].sku if item_id in items else None,
            "name": items[item_id].resolved_name if item_id in items else None,
            "quantity": to_decimal(qty),
            "entries": count,
            "cost": money(costs.get(item_id, Decimal("0")) * to_decimal(qty)),
        }
        for item_id, qty, count in rows
    ]
    return sorted(out, key=lambda r: r["cost"], reverse=True)[:limit]


def tailor_productivity(db: Session) -> list[dict]:
    """Completed work and earnings per tailor.

    Earnings are computed from the rates frozen on each work order, so this
    report does not move when someone's rate changes.
    """
    from app.models.workforce import Tailor

    rows = (
        db.query(WorkOrder)
        .filter(WorkOrder.tailor_id.isnot(None), WorkOrder.status == WorkOrderStatus.COMPLETED)
        .all()
    )
    tailors = {t.id: t for t in db.query(Tailor).all()}
    agg: dict[int, dict] = {}
    for wo in rows:
        entry = agg.setdefault(wo.tailor_id, {
            "tailor_id": wo.tailor_id,
            "name": tailors[wo.tailor_id].name if wo.tailor_id in tailors else None,
            "completed_work_orders": 0,
            "completed_quantity": Decimal("0"),
            "hours": Decimal("0"),
            "earnings": Decimal("0"),
        })
        entry["completed_work_orders"] += 1
        entry["completed_quantity"] += to_decimal(wo.completed_quantity)
        entry["hours"] += to_decimal(wo.hours)
        entry["earnings"] += wo.labour_cost

    for e in agg.values():
        e["earnings"] = money(e["earnings"])
    return sorted(agg.values(), key=lambda r: r["earnings"], reverse=True)


def planned_vs_actual(db: Session, order: ProductionOrder) -> list[dict]:
    """Per-material planned/consumed/wasted variance for one order.

    The BOM is never rewritten from this - the variance *is* the signal, and
    quietly adjusting the recipe to match reality would destroy it.
    """
    cost = order_cost(db, order)
    return [
        {
            "sku": line["sku"],
            "name": line["name"],
            "planned": line["planned_quantity"],
            "consumed": line["consumed_quantity"],
            "wasted": line["wasted_quantity"],
            "quantity_variance": line["consumed_quantity"] - line["planned_quantity"],
            "cost_variance": line["variance"],
        }
        for line in cost["material_lines"]
    ]
