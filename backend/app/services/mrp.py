"""Material requirement planning: aggregate demand, net against supply.

STATELESS BY DESIGN. Every earlier manufacturing table records something that
happened - a reservation, an issue, a receipt. MRP records nothing; it is a
computed answer to "what should we buy, and how much?", derived fresh from
production_order_materials, stock_levels, stock_reservations and vendor_items on
every call. There is no MRP table to go stale.

WHAT COUNTS AS DEMAND. Only material lines belonging to production orders that
are actually going to consume material - RELEASED, IN_PROGRESS or
PARTIALLY_COMPLETED - and only the *outstanding* portion, planned minus already
issued. A DRAFT order is a plan nobody has committed to yet; a COMPLETED,
CANCELLED or CLOSED_SHORT one needs nothing further. Sub-assembly lines are
excluded, exactly as in Phase 3C's availability calculation, because their own
raw materials are already itemised separately.

WHAT COUNTS AS SUPPLY. `on_hand - reserved`, aggregated per item across every
location a caller does not explicitly scope to one outlet - the same formula
Phase 3D established, extended from one order's reservations to all of them.

NEVER AUTOMATIC. `generate_draft_purchase_orders` is the one function that
writes anything, and what it writes is a DRAFT purchase order - inert until a
human reviews and sends it. Nothing in this module ever creates a SENT or
CONFIRMED order.
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.money import to_decimal
from app.models.inventory import StockLevel
from app.models.material_flow import HOLDING_STATUSES, StockReservation
from app.models.product import Item
from app.models.production import ProductionOrder, ProductionOrderMaterial, ProductionStatus
from app.models.purchase import PurchaseOrder, PurchaseOrderItem, PurchaseOrderStatus
from app.models.vendor import VendorItem
from app.services.numbering import next_document_number

# Orders that still intend to draw material. Matches ISSUABLE_STATUSES in
# material_flow plus PARTIALLY_COMPLETED's continuing need for the remainder.
OPEN_STATUSES = {
    ProductionStatus.RELEASED,
    ProductionStatus.IN_PROGRESS,
    ProductionStatus.PARTIALLY_COMPLETED,
}


class MrpError(ValueError):
    """An MRP action could not be completed. Message is user-facing."""


def requirements(db: Session, *, location_id: int | None = None) -> list[dict]:
    """Aggregate outstanding material demand across every open production order.

    Read-only: touches stock_levels and stock_reservations for their current
    values but writes nothing, the same guarantee Phase 3C's availability
    calculation makes.
    """
    lines = (
        db.query(ProductionOrderMaterial)
        .join(ProductionOrder, ProductionOrder.id == ProductionOrderMaterial.production_order_id)
        .filter(
            ProductionOrder.status.in_(OPEN_STATUSES),
            ProductionOrderMaterial.is_subassembly.is_(False),
        )
        .options(joinedload(ProductionOrderMaterial.item))
        .all()
    )
    if location_id:
        lines = [
            m for m in lines
            if db.get(ProductionOrder, m.production_order_id).location_id == location_id
        ]

    demand: dict[int, dict] = {}
    for m in lines:
        outstanding = to_decimal(m.planned_quantity) - to_decimal(m.issued_quantity)
        if outstanding <= 0:
            continue
        entry = demand.setdefault(m.item_id, {"item": m.item, "required": Decimal("0"), "orders": {}})
        entry["required"] += outstanding
        order = db.get(ProductionOrder, m.production_order_id)
        key = order.id
        if key not in entry["orders"]:
            entry["orders"][key] = {
                "production_order_id": order.id, "po_number": order.po_number, "quantity": Decimal("0"),
            }
        entry["orders"][key]["quantity"] += outstanding

    if not demand:
        return []

    item_ids = list(demand.keys())
    on_hand_q = db.query(StockLevel.variant_id, func.sum(StockLevel.quantity)).filter(
        StockLevel.variant_id.in_(item_ids)
    )
    if location_id:
        on_hand_q = on_hand_q.filter(StockLevel.outlet_id == location_id)
    on_hand = {vid: to_decimal(qty) for vid, qty in on_hand_q.group_by(StockLevel.variant_id).all()}

    reserved_q = (
        db.query(
            StockReservation.item_id,
            func.sum(StockReservation.quantity - StockReservation.issued_quantity),
        )
        .filter(StockReservation.item_id.in_(item_ids), StockReservation.status.in_(HOLDING_STATUSES))
    )
    if location_id:
        reserved_q = reserved_q.filter(StockReservation.location_id == location_id)
    reserved = {vid: to_decimal(qty) for vid, qty in reserved_q.group_by(StockReservation.item_id).all()}

    preferred = {
        v.variant_id: v
        for v in (
            db.query(VendorItem)
            .filter(VendorItem.variant_id.in_(item_ids), VendorItem.is_preferred.is_(True))
            .options(joinedload(VendorItem.vendor))
            .all()
        )
    }

    out = []
    for item_id, entry in demand.items():
        item = entry["item"]
        have = on_hand.get(item_id, Decimal("0"))
        held = reserved.get(item_id, Decimal("0"))
        available = have - held
        required = entry["required"]
        shortage = required - available
        shortage = shortage if shortage > 0 else Decimal("0")

        vendor_link = preferred.get(item_id)
        suggested = shortage
        if shortage > 0 and vendor_link and to_decimal(vendor_link.min_order_qty) > shortage:
            # Round up to the vendor's minimum order, never down past what is short.
            suggested = to_decimal(vendor_link.min_order_qty)

        out.append({
            "item_id": item_id,
            "sku": item.sku if item else None,
            "name": item.resolved_name if item else None,
            "uom_code": item.stock_uom.code if item and item.stock_uom else None,
            "required": required,
            "on_hand": have,
            "reserved": held,
            "available": available,
            "shortage": shortage,
            "suggested_purchase_qty": suggested,
            "preferred_vendor_id": vendor_link.vendor_id if vendor_link else None,
            "preferred_vendor_name": (
                vendor_link.vendor.name if vendor_link and vendor_link.vendor else None
            ),
            "min_order_qty": to_decimal(vendor_link.min_order_qty) if vendor_link else None,
            "lead_time_days": vendor_link.lead_time_days if vendor_link else None,
            "contributing_orders": sorted(
                entry["orders"].values(), key=lambda o: o["po_number"]
            ),
        })

    return sorted(out, key=lambda r: (r["shortage"] <= 0, r["sku"] or ""))


def generate_draft_purchase_orders(
    db: Session, *, outlet_id: int, user_id: int | None = None, item_ids: list[int] | None = None,
) -> list[PurchaseOrder]:
    """Turn shortages into DRAFT purchase orders, grouped by preferred vendor.

    A draft is inert: it requires a human to review quantities, approve and send
    it before it becomes a real commitment to a vendor. This is the closest thing
    to "generate purchase suggestions" that does not silently commit to
    procurement, which is the one thing MRP must never do on its own.
    """
    rows = [r for r in requirements(db) if r["shortage"] > 0]
    if item_ids:
        wanted = set(item_ids)
        rows = [r for r in rows if r["item_id"] in wanted]
    if not rows:
        raise MrpError("Nothing is currently short - there is nothing to draft a purchase order for")

    unassigned = [r for r in rows if not r["preferred_vendor_id"]]
    if unassigned:
        skus = ", ".join(r["sku"] for r in unassigned if r["sku"])
        raise MrpError(
            f"These items have no preferred vendor and were skipped: {skus}. "
            "Set a preferred vendor on each before generating a draft PO for them."
        )

    by_vendor: dict[int, list[dict]] = {}
    for r in rows:
        by_vendor.setdefault(r["preferred_vendor_id"], []).append(r)

    created: list[PurchaseOrder] = []
    for vendor_id, vendor_rows in by_vendor.items():
        po = PurchaseOrder(
            po_number=next_document_number(db, PurchaseOrder, PurchaseOrder.po_number, "PO"),
            vendor_id=vendor_id, outlet_id=outlet_id, status=PurchaseOrderStatus.DRAFT,
            order_date=datetime.now(timezone.utc),
            notes="Drafted from MRP - review quantities and pricing before sending.",
            created_by_id=user_id,
        )
        db.add(po)
        db.flush()
        for r in vendor_rows:
            db.add(PurchaseOrderItem(
                purchase_order_id=po.id, variant_id=r["item_id"],
                quantity_ordered=r["suggested_purchase_qty"],
                unit_cost=Decimal("0"),
            ))
        db.flush()
        created.append(po)

    return created
