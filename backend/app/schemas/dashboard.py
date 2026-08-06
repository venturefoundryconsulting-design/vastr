from pydantic import BaseModel

from app.schemas.inventory import LowStockItem
from app.schemas.purchase import PurchaseOrderOut
from app.schemas.transfer import TransferOut


class DashboardSummary(BaseModel):
    total_outlets: int
    total_products: int
    total_variants: int
    low_stock_count: int
    open_purchase_orders: int
    in_transit_transfers: int
    sales_today_count: int
    sales_today_total: float
    low_stock_items: list[LowStockItem]
    recent_purchase_orders: list[PurchaseOrderOut]
    recent_transfers: list[TransferOut]
