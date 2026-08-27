"""Material requirement planning.

Read-only aggregation, plus one explicit, never-automatic action for turning a
shortage into a draft purchase order.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.models.outlet import Outlet
from app.models.user import User
from app.services import mrp
from app.services.audit import log_activity

router = APIRouter(prefix="/api/mrp", tags=["mrp"])


class GeneratePoRequest(BaseModel):
    outlet_id: int
    item_ids: list[int] | None = None  # None = every shortage


@router.get("/requirements")
def get_requirements(
    db: Session = Depends(get_db), _: User = Depends(require_permission("mrp.view")),
    location_id: int | None = None,
):
    """Aggregated demand across every open production order, netted against
    on-hand minus reserved. Touches no inventory - safe to poll."""
    return mrp.requirements(db, location_id=location_id)


@router.post("/generate-purchase-orders")
def generate_purchase_orders(
    payload: GeneratePoRequest, db: Session = Depends(get_db),
    user: User = Depends(require_permission("mrp.generate_po")),
):
    """Draft purchase orders from current shortages, grouped by preferred vendor.

    The result is DRAFT and inert - nothing is sent to a vendor until a human
    reviews it. This never runs on its own; it only runs when explicitly called.
    """
    if not db.get(Outlet, payload.outlet_id):
        raise HTTPException(404, "Outlet not found")
    try:
        created = mrp.generate_draft_purchase_orders(
            db, outlet_id=payload.outlet_id, user_id=user.id, item_ids=payload.item_ids,
        )
    except mrp.MrpError as e:
        raise HTTPException(409, str(e)) from e

    log_activity(
        db, action="mrp.generate_po", tenant_id=user.tenant_id, user_id=user.id,
        entity_type="PurchaseOrder", entity_id=created[0].id if created else None,
        details={"purchase_orders": [po.po_number for po in created]},
    )
    db.commit()
    return [{"id": po.id, "po_number": po.po_number, "vendor_id": po.vendor_id,
             "status": po.status, "items": len(po.items)} for po in created]
