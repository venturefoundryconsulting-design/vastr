from sqlalchemy.orm import Session, joinedload

from app.models.inventory import StockLevel
from app.models.product import ProductVariant
from app.models.vendor import VendorProduct
from app.schemas.purchase import ReorderSuggestion, ReorderSuggestionItem


def build_reorder_suggestions(
    db: Session, outlet_id: int | None = None, vendor_id: int | None = None
) -> list[ReorderSuggestion]:
    """Finds variants below reorder level and groups restock suggestions by preferred vendor."""
    query = (
        db.query(StockLevel)
        .join(ProductVariant, StockLevel.variant_id == ProductVariant.id)
        .options(joinedload(StockLevel.variant), joinedload(StockLevel.outlet))
        .filter(StockLevel.quantity <= ProductVariant.reorder_level)
    )
    if outlet_id:
        query = query.filter(StockLevel.outlet_id == outlet_id)
    low_stock_levels = query.all()

    by_vendor: dict[int, ReorderSuggestion] = {}
    for level in low_stock_levels:
        preferred_link = (
            db.query(VendorProduct)
            .filter(VendorProduct.variant_id == level.variant_id)
            .order_by(VendorProduct.is_preferred.desc())
            .first()
        )
        if not preferred_link:
            continue
        if vendor_id and preferred_link.vendor_id != vendor_id:
            continue

        target = max(level.variant.reorder_level * 2 - level.quantity, level.variant.reorder_level)
        suggestion_item = ReorderSuggestionItem(
            variant_id=level.variant_id,
            sku=level.variant.sku,
            product_name=level.variant.product.name,
            size=level.variant.size,
            color=level.variant.color,
            outlet_id=level.outlet_id,
            outlet_name=level.outlet.name,
            current_quantity=level.quantity,
            reorder_level=level.variant.reorder_level,
            suggested_quantity=max(target, 1),
            cost_price=float(preferred_link.cost_price or level.variant.cost_price),
        )

        if preferred_link.vendor_id not in by_vendor:
            by_vendor[preferred_link.vendor_id] = ReorderSuggestion(
                vendor_id=preferred_link.vendor_id,
                vendor_name=preferred_link.vendor.name,
                items=[],
            )
        by_vendor[preferred_link.vendor_id].items.append(suggestion_item)

    return list(by_vendor.values())
