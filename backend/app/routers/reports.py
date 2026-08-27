from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, get_db, require_manager_up
from app.core.money import money, to_decimal
from app.models.inventory import MovementType, StockLevel, StockMovement
from app.models.outlet import Outlet
from app.models.product import Product, ProductVariant
from app.models.sale import Sale
from app.schemas.reports import PaymentModeBreakdownItem, SalesTrendPoint, StockAgingItem
from app.services.export import ExportFormat, build_export_response

router = APIRouter(prefix="/api/reports", tags=["reports"])

_STOCK_AGING_COLUMNS = [
    ("sku", "SKU"),
    ("product_name", "Product"),
    ("color", "Color"),
    ("size", "Size"),
    ("outlet_name", "Outlet"),
    ("quantity", "Quantity"),
    ("stock_value", "Stock Value"),
    ("days_since_last_sale", "Days Idle"),
]


def _stock_with_last_sale(db: Session, outlet_id: int | None) -> list[StockAgingItem]:
    last_sale_subq = (
        db.query(
            StockMovement.variant_id.label("variant_id"),
            StockMovement.outlet_id.label("outlet_id"),
            func.max(StockMovement.created_at).label("last_sold_at"),
        )
        .filter(StockMovement.movement_type == MovementType.SALE)
        .group_by(StockMovement.variant_id, StockMovement.outlet_id)
        .subquery()
    )

    query = (
        db.query(StockLevel, ProductVariant, Product, Outlet, last_sale_subq.c.last_sold_at)
        .join(ProductVariant, StockLevel.variant_id == ProductVariant.id)
        .join(Product, ProductVariant.product_id == Product.id)
        .join(Outlet, StockLevel.outlet_id == Outlet.id)
        .outerjoin(
            last_sale_subq,
            (last_sale_subq.c.variant_id == StockLevel.variant_id)
            & (last_sale_subq.c.outlet_id == StockLevel.outlet_id),
        )
        .filter(StockLevel.quantity > 0)
    )
    if outlet_id:
        query = query.filter(StockLevel.outlet_id == outlet_id)

    now = datetime.now(timezone.utc)
    items = []
    for stock, variant, product, outlet, last_sold_at in query.all():
        reference = last_sold_at or variant.created_at
        days = (now - reference).days if reference else 0
        # Decimal, not float: stock.quantity is Decimal now and float * Decimal
        # raises TypeError (see app.core.money).
        cost_price = to_decimal(variant.cost_price)
        items.append(
            StockAgingItem(
                variant_id=variant.id,
                product_id=product.id,
                sku=variant.sku,
                product_name=product.name,
                color=variant.color,
                size=variant.size,
                outlet_id=outlet.id,
                outlet_name=outlet.name,
                quantity=stock.quantity,
                cost_price=cost_price,
                stock_value=money(cost_price * stock.quantity),
                last_sold_at=last_sold_at,
                days_since_last_sale=max(days, 0),
            )
        )
    return items


@router.get("/stock-aging", response_model=list[StockAgingItem], dependencies=[Depends(require_manager_up)])
def stock_aging(outlet_id: int | None = None, db: Session = Depends(get_db)):
    items = _stock_with_last_sale(db, outlet_id)
    items.sort(key=lambda i: i.days_since_last_sale, reverse=True)
    return items


@router.get("/dead-stock", response_model=list[StockAgingItem], dependencies=[Depends(require_manager_up)])
def dead_stock(
    outlet_id: int | None = None,
    days: int = 90,
    db: Session = Depends(get_db),
):
    items = _stock_with_last_sale(db, outlet_id)
    dead = [i for i in items if i.days_since_last_sale >= days]
    dead.sort(key=lambda i: i.stock_value, reverse=True)
    return dead


@router.get("/stock-aging/export", dependencies=[Depends(require_manager_up)])
def export_stock_aging(outlet_id: int | None = None, format: ExportFormat = "xlsx", db: Session = Depends(get_db)):
    items = _stock_with_last_sale(db, outlet_id)
    items.sort(key=lambda i: i.days_since_last_sale, reverse=True)
    rows = [i.model_dump() for i in items]
    return build_export_response(rows, _STOCK_AGING_COLUMNS, "Stock Aging", format)


@router.get("/dead-stock/export", dependencies=[Depends(require_manager_up)])
def export_dead_stock(
    outlet_id: int | None = None, days: int = 90, format: ExportFormat = "xlsx", db: Session = Depends(get_db)
):
    items = _stock_with_last_sale(db, outlet_id)
    dead = [i for i in items if i.days_since_last_sale >= days]
    dead.sort(key=lambda i: i.stock_value, reverse=True)
    rows = [i.model_dump() for i in dead]
    return build_export_response(rows, _STOCK_AGING_COLUMNS, "Dead Stock", format)


def _sales_in_range(db: Session, start: date, outlet_id: int | None) -> list[Sale]:
    query = db.query(Sale).options(joinedload(Sale.items)).filter(Sale.created_at >= start)
    if outlet_id:
        query = query.filter(Sale.outlet_id == outlet_id)
    return query.all()


@router.get("/sales-trend", response_model=list[SalesTrendPoint])
def sales_trend(
    days: int = 30, outlet_id: int | None = None, db: Session = Depends(get_db), _=Depends(get_current_user)
):
    end = date.today()
    start = end - timedelta(days=days - 1)
    sales = _sales_in_range(db, start, outlet_id)

    buckets = {start + timedelta(days=i): {"total": to_decimal(0), "count": 0} for i in range(days)}
    for sale in sales:
        day = sale.created_at.date()
        bucket = buckets.get(day)
        if bucket:
            bucket["total"] += sale.total
            bucket["count"] += 1

    return [
        SalesTrendPoint(date=d.isoformat(), total=money(v["total"]), count=v["count"])
        for d, v in sorted(buckets.items())
    ]


@router.get("/payment-mode-breakdown", response_model=list[PaymentModeBreakdownItem])
def payment_mode_breakdown(
    days: int = 30, outlet_id: int | None = None, db: Session = Depends(get_db), _=Depends(get_current_user)
):
    start = date.today() - timedelta(days=days - 1)
    sales = _sales_in_range(db, start, outlet_id)

    breakdown: dict[str, dict] = {}
    for sale in sales:
        key = sale.payment_mode.value
        entry = breakdown.setdefault(key, {"total": to_decimal(0), "count": 0})
        entry["total"] += sale.total
        entry["count"] += 1

    return [
        PaymentModeBreakdownItem(payment_mode=k, total=money(v["total"]), count=v["count"])
        for k, v in sorted(breakdown.items())
    ]
