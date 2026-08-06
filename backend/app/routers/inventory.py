from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.inventory import MovementType, StockLevel, StockMovement
from app.models.outlet import Outlet
from app.models.product import Product, ProductVariant
from app.models.user import User
from app.schemas.inventory import (
    StockAdjustment,
    StockLevelDetail,
    StockMovementOut,
)
from app.services.audit import log_activity
from app.services.export import ExportFormat, build_export_response
from app.services.inventory import apply_stock_delta

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


@router.get("/stock", response_model=list[StockLevelDetail])
def list_stock(
    outlet_id: int | None = None,
    variant_id: int | None = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    query = (
        db.query(StockLevel)
        .join(ProductVariant)
        .join(Product)
        .join(Outlet, StockLevel.outlet_id == Outlet.id)
    )
    if outlet_id:
        query = query.filter(StockLevel.outlet_id == outlet_id)
    if variant_id:
        query = query.filter(StockLevel.variant_id == variant_id)
    rows = query.all()
    return [
        StockLevelDetail(
            id=s.id,
            variant_id=s.variant_id,
            outlet_id=s.outlet_id,
            quantity=s.quantity,
            sku=s.variant.sku,
            product_name=s.variant.product.name,
            size=s.variant.size,
            color=s.variant.color,
            outlet_name=s.outlet.name,
            reorder_level=s.variant.reorder_level,
        )
        for s in rows
    ]


@router.get("/export")
def export_stock(
    outlet_id: int | None = None,
    variant_id: int | None = None,
    format: ExportFormat = "xlsx",
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    query = (
        db.query(StockLevel)
        .join(ProductVariant)
        .join(Product)
        .join(Outlet, StockLevel.outlet_id == Outlet.id)
    )
    if outlet_id:
        query = query.filter(StockLevel.outlet_id == outlet_id)
    if variant_id:
        query = query.filter(StockLevel.variant_id == variant_id)
    rows_data = query.all()
    rows = [
        {
            "sku": s.variant.sku,
            "product_name": s.variant.product.name,
            "size": s.variant.size,
            "color": s.variant.color,
            "outlet": s.outlet.name,
            "quantity": s.quantity,
            "reorder_level": s.variant.reorder_level,
        }
        for s in rows_data
    ]
    columns = [
        ("sku", "SKU"),
        ("product_name", "Product"),
        ("size", "Size"),
        ("color", "Color"),
        ("outlet", "Outlet"),
        ("quantity", "Quantity"),
        ("reorder_level", "Reorder Level"),
    ]
    return build_export_response(rows, columns, "Inventory", format)


@router.post("/adjust", response_model=StockMovementOut)
def adjust_stock(
    payload: StockAdjustment, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    movement = apply_stock_delta(
        db,
        variant_id=payload.variant_id,
        outlet_id=payload.outlet_id,
        quantity_delta=payload.quantity_delta,
        movement_type=MovementType.ADJUSTMENT,
        note=payload.note,
        created_by_id=user.id,
    )
    db.flush()
    log_activity(
        db, action="inventory.adjust", tenant_id=user.tenant_id, user_id=user.id,
        entity_type="StockMovement", entity_id=movement.id,
        details={"variant_id": payload.variant_id, "outlet_id": payload.outlet_id, "delta": payload.quantity_delta},
    )
    db.commit()
    db.refresh(movement)
    return movement


@router.get("/movements", response_model=list[StockMovementOut])
def list_movements(
    variant_id: int | None = None,
    outlet_id: int | None = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    query = db.query(StockMovement)
    if variant_id:
        query = query.filter(StockMovement.variant_id == variant_id)
    if outlet_id:
        query = query.filter(StockMovement.outlet_id == outlet_id)
    return query.order_by(StockMovement.created_at.desc()).limit(200).all()
