from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, get_db
from app.models.inventory import StockLevel
from app.models.outlet import Outlet
from app.models.product import Product, ProductVariant
from app.models.purchase import PurchaseOrder, PurchaseOrderItem, PurchaseOrderStatus
from app.models.sale import Sale
from app.models.transfer import StockTransfer, StockTransferItem, TransferStatus
from app.models.vendor import VendorProduct
from app.schemas.dashboard import DashboardSummary
from app.schemas.inventory import LowStockItem
from app.routers.purchase_orders import _to_out as po_to_out
from app.routers.transfers import _to_out as transfer_to_out

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def get_summary(db: Session = Depends(get_db), _=Depends(get_current_user)):
    low_stock_rows = (
        db.query(StockLevel)
        .join(ProductVariant, StockLevel.variant_id == ProductVariant.id)
        .options(joinedload(StockLevel.variant).joinedload(ProductVariant.product), joinedload(StockLevel.outlet))
        .filter(StockLevel.quantity <= ProductVariant.reorder_level)
        .limit(50)
        .all()
    )
    low_stock_items = []
    for level in low_stock_rows:
        preferred = (
            db.query(VendorProduct)
            .filter(VendorProduct.variant_id == level.variant_id)
            .order_by(VendorProduct.is_preferred.desc())
            .first()
        )
        low_stock_items.append(
            LowStockItem(
                variant_id=level.variant_id,
                sku=level.variant.sku,
                product_name=level.variant.product.name,
                size=level.variant.size,
                color=level.variant.color,
                outlet_id=level.outlet_id,
                outlet_name=level.outlet.name,
                quantity=level.quantity,
                reorder_level=level.variant.reorder_level,
                preferred_vendor_id=preferred.vendor_id if preferred else None,
                preferred_vendor_name=preferred.vendor.name if preferred else None,
            )
        )

    today = datetime.now(timezone.utc).date()
    sales_today = db.query(Sale).filter(func.date(Sale.created_at) == today).all()

    recent_pos = (
        db.query(PurchaseOrder)
        .options(
            joinedload(PurchaseOrder.items).joinedload(PurchaseOrderItem.variant),
            joinedload(PurchaseOrder.vendor),
            joinedload(PurchaseOrder.outlet),
        )
        .order_by(PurchaseOrder.created_at.desc())
        .limit(5)
        .all()
    )
    recent_transfers = (
        db.query(StockTransfer)
        .options(
            joinedload(StockTransfer.items).joinedload(StockTransferItem.variant),
            joinedload(StockTransfer.source_outlet),
            joinedload(StockTransfer.dest_outlet),
        )
        .order_by(StockTransfer.created_at.desc())
        .limit(5)
        .all()
    )

    return DashboardSummary(
        total_outlets=db.query(func.count(Outlet.id)).filter(Outlet.is_active.is_(True)).scalar(),
        total_products=db.query(func.count(Product.id)).filter(Product.is_active.is_(True)).scalar(),
        total_variants=db.query(func.count(ProductVariant.id)).filter(ProductVariant.is_active.is_(True)).scalar(),
        low_stock_count=len(low_stock_items),
        open_purchase_orders=db.query(func.count(PurchaseOrder.id))
        .filter(
            PurchaseOrder.status.in_(
                [PurchaseOrderStatus.DRAFT, PurchaseOrderStatus.SENT, PurchaseOrderStatus.CONFIRMED,
                 PurchaseOrderStatus.PARTIALLY_RECEIVED]
            )
        )
        .scalar(),
        in_transit_transfers=db.query(func.count(StockTransfer.id))
        .filter(StockTransfer.status == TransferStatus.DISPATCHED)
        .scalar(),
        sales_today_count=len(sales_today),
        sales_today_total=round(sum(s.total for s in sales_today), 2),
        low_stock_items=low_stock_items,
        recent_purchase_orders=[po_to_out(po) for po in recent_pos],
        recent_transfers=[transfer_to_out(t) for t in recent_transfers],
    )
