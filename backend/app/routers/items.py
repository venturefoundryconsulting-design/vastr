"""Item master and units of measure.

Mounted at /api/items and /api/uom. The pre-existing /api/products endpoints are
left untouched and continue to serve the POS - see `products.py`. This router is
the superset view: every item type, including the raw materials POS never shows.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, get_db, require_manager_up
from app.models.inventory import StockLevel
from app.models.product import Item, ItemType
from app.models.uom import ItemUomConversion, UnitOfMeasure, UomCategory
from app.models.user import User
from app.models.vendor import Vendor, VendorItem
from app.schemas.item import (
    ConvertRequest,
    ConvertResult,
    ItemCreate,
    ItemOut,
    ItemUomConversionCreate,
    ItemUomConversionOut,
    ItemUpdate,
    UomCategoryCreate,
    UomCategoryOut,
    UomCreate,
    UomOut,
    UomUpdate,
    VendorItemCreate,
    VendorItemOut,
)
from app.services.audit import log_activity
from app.services.uom import UomConversionError, convert, validate_conversion_pair

router = APIRouter(prefix="/api/items", tags=["items"])
uom_router = APIRouter(prefix="/api/uom", tags=["uom"])


# ------------------------------------------------------------------ helpers


def _stock_by_item(db: Session) -> dict[int, Decimal]:
    rows = db.query(StockLevel.variant_id, func.sum(StockLevel.quantity)).group_by(
        StockLevel.variant_id
    ).all()
    return {vid: qty or Decimal("0") for vid, qty in rows}


def _to_out(item: Item, total_stock: Decimal | None = None) -> ItemOut:
    return ItemOut(
        **{k: getattr(item, k) for k in ItemCreate.model_fields if hasattr(item, k)},
        id=item.id,
        product_name=item.product.name if item.product else None,
        category_name=item.category.name if item.category else None,
        stock_uom_code=item.stock_uom.code if item.stock_uom else None,
        purchase_uom_code=item.purchase_uom.code if item.purchase_uom else None,
        sales_uom_code=item.sales_uom.code if item.sales_uom else None,
        display_name=item.display_name,
        total_stock=total_stock if total_stock is not None else Decimal("0"),
    )


def _get_or_404(db: Session, item_id: int) -> Item:
    item = (
        db.query(Item)
        .options(
            joinedload(Item.product), joinedload(Item.category),
            joinedload(Item.stock_uom), joinedload(Item.purchase_uom), joinedload(Item.sales_uom),
        )
        .filter(Item.id == item_id)
        .first()
    )
    if not item:
        raise HTTPException(404, "Item not found")
    return item


# -------------------------------------------------------------------- items


@router.get("", response_model=list[ItemOut])
def list_items(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    item_type: ItemType | None = None,
    category_id: int | None = None,
    is_active: bool | None = None,
    low_stock: bool = False,
    q: str | None = Query(None, description="Matches SKU, barcode, or name"),
):
    query = db.query(Item).options(
        joinedload(Item.product), joinedload(Item.category),
        joinedload(Item.stock_uom), joinedload(Item.purchase_uom), joinedload(Item.sales_uom),
    )
    if item_type:
        query = query.filter(Item.item_type == item_type)
    if category_id:
        query = query.filter(Item.category_id == category_id)
    if is_active is not None:
        query = query.filter(Item.is_active.is_(is_active))
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            (Item.sku.ilike(like)) | (Item.barcode.ilike(like)) | (Item.name.ilike(like))
        )

    items = query.order_by(Item.sku).all()
    stock = _stock_by_item(db)

    out = [_to_out(i, stock.get(i.id, Decimal("0"))) for i in items]
    if low_stock:
        # Filtered here rather than in SQL: an item with no stock row at all is
        # the most low-stock case there is, and an inner join would hide it.
        out = [o for o in out if o.is_stocked and o.total_stock <= o.reorder_level]
    return out


@router.get("/{item_id}", response_model=ItemOut)
def get_item(item_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    item = _get_or_404(db, item_id)
    return _to_out(item, _stock_by_item(db).get(item.id, Decimal("0")))


@router.post("", response_model=ItemOut, status_code=201)
def create_item(
    payload: ItemCreate, db: Session = Depends(get_db), user: User = Depends(require_manager_up)
):
    if db.query(Item).filter(Item.sku == payload.sku).first():
        raise HTTPException(409, f"SKU '{payload.sku}' is already in use")
    if payload.barcode and db.query(Item).filter(Item.barcode == payload.barcode).first():
        raise HTTPException(409, f"Barcode '{payload.barcode}' is already in use")

    item = Item(**payload.model_dump())
    db.add(item)
    db.flush()
    log_activity(
        db, action="item.create", tenant_id=user.tenant_id, user_id=user.id,
        entity_type="Item", entity_id=item.id,
        details={"sku": item.sku, "item_type": item.item_type.value},
    )
    db.commit()
    return _to_out(_get_or_404(db, item.id), Decimal("0"))


@router.patch("/{item_id}", response_model=ItemOut)
def update_item(
    item_id: int, payload: ItemUpdate,
    db: Session = Depends(get_db), user: User = Depends(require_manager_up),
):
    item = _get_or_404(db, item_id)
    changes = payload.model_dump(exclude_unset=True)

    new_barcode = changes.get("barcode")
    if new_barcode and new_barcode != item.barcode:
        clash = db.query(Item).filter(Item.barcode == new_barcode, Item.id != item_id).first()
        if clash:
            raise HTTPException(409, f"Barcode '{new_barcode}' is already in use")

    for field, value in changes.items():
        setattr(item, field, value)
    db.flush()
    log_activity(
        db, action="item.update", tenant_id=user.tenant_id, user_id=user.id,
        entity_type="Item", entity_id=item.id, details={"fields": sorted(changes)},
    )
    db.commit()
    return _to_out(_get_or_404(db, item_id), _stock_by_item(db).get(item_id, Decimal("0")))


# ------------------------------------------------------- item conversions


@router.get("/{item_id}/conversions", response_model=list[ItemUomConversionOut])
def list_item_conversions(
    item_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    _get_or_404(db, item_id)
    rows = db.query(ItemUomConversion).filter(ItemUomConversion.item_id == item_id).all()
    return [
        ItemUomConversionOut(
            **{k: getattr(r, k) for k in
               ("id", "item_id", "from_uom_id", "to_uom_id", "factor", "vendor_id", "is_active")},
            from_uom_code=r.from_uom.code if r.from_uom else None,
            to_uom_code=r.to_uom.code if r.to_uom else None,
            vendor_name=(db.get(Vendor, r.vendor_id).name if r.vendor_id else None),
        )
        for r in rows
    ]


@router.post("/{item_id}/conversions", response_model=ItemUomConversionOut, status_code=201)
def add_item_conversion(
    item_id: int, payload: ItemUomConversionCreate,
    db: Session = Depends(get_db), user: User = Depends(require_manager_up),
):
    """Packaging rules deliberately may cross dimensions - "1 roll = 25 m" is the
    whole point - so no same-category check here, unlike the standard UoM table."""
    _get_or_404(db, item_id)
    if payload.from_uom_id == payload.to_uom_id:
        raise HTTPException(400, "A conversion needs two different units")

    row = ItemUomConversion(item_id=item_id, **payload.model_dump())
    db.add(row)
    db.flush()
    log_activity(
        db, action="item.conversion.create", tenant_id=user.tenant_id, user_id=user.id,
        entity_type="Item", entity_id=item_id, details={"factor": payload.factor},
    )
    db.commit()
    db.refresh(row)
    return ItemUomConversionOut(
        **{k: getattr(row, k) for k in
           ("id", "item_id", "from_uom_id", "to_uom_id", "factor", "vendor_id", "is_active")},
        from_uom_code=row.from_uom.code if row.from_uom else None,
        to_uom_code=row.to_uom.code if row.to_uom else None,
    )


# ------------------------------------------------------------ vendor items


@router.get("/{item_id}/vendors", response_model=list[VendorItemOut])
def list_item_vendors(
    item_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    _get_or_404(db, item_id)
    rows = (
        db.query(VendorItem)
        .options(joinedload(VendorItem.vendor), joinedload(VendorItem.purchase_uom))
        .filter(VendorItem.variant_id == item_id)
        .all()
    )
    return [
        VendorItemOut(
            **{k: getattr(r, k) for k in
               ("id", "vendor_id", "variant_id", "vendor_sku", "cost_price",
                "purchase_uom_id", "min_order_qty", "lead_time_days", "is_preferred", "is_active")},
            vendor_name=r.vendor.name if r.vendor else None,
            purchase_uom_code=r.purchase_uom.code if r.purchase_uom else None,
        )
        for r in rows
    ]


@router.post("/{item_id}/vendors", response_model=VendorItemOut, status_code=201)
def add_item_vendor(
    item_id: int, payload: VendorItemCreate,
    db: Session = Depends(get_db), user: User = Depends(require_manager_up),
):
    _get_or_404(db, item_id)
    if not db.get(Vendor, payload.vendor_id):
        raise HTTPException(404, "Vendor not found")

    if payload.is_preferred:
        # Exactly one preferred vendor per item, or reorder suggestions become
        # ambiguous. Setting a new one demotes the incumbent.
        db.query(VendorItem).filter(
            VendorItem.variant_id == item_id, VendorItem.is_preferred.is_(True)
        ).update({"is_preferred": False})

    row = VendorItem(variant_id=item_id, **payload.model_dump())
    db.add(row)
    db.flush()
    log_activity(
        db, action="item.vendor.link", tenant_id=user.tenant_id, user_id=user.id,
        entity_type="Item", entity_id=item_id, details={"vendor_id": payload.vendor_id},
    )
    db.commit()
    db.refresh(row)
    return VendorItemOut(
        **{k: getattr(row, k) for k in
           ("id", "vendor_id", "variant_id", "vendor_sku", "cost_price",
            "purchase_uom_id", "min_order_qty", "lead_time_days", "is_preferred", "is_active")},
        vendor_name=row.vendor.name if row.vendor else None,
        purchase_uom_code=row.purchase_uom.code if row.purchase_uom else None,
    )


# ---------------------------------------------------------------------- UoM


@uom_router.get("/categories", response_model=list[UomCategoryOut])
def list_uom_categories(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(UomCategory).order_by(UomCategory.code).all()


@uom_router.post("/categories", response_model=UomCategoryOut, status_code=201)
def create_uom_category(
    payload: UomCategoryCreate, db: Session = Depends(get_db), _: User = Depends(require_manager_up)
):
    if db.query(UomCategory).filter(UomCategory.code == payload.code).first():
        raise HTTPException(409, f"A category with code '{payload.code}' already exists")
    cat = UomCategory(**payload.model_dump())
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


@uom_router.get("", response_model=list[UomOut])
def list_uoms(
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
    category_id: int | None = None, is_active: bool | None = None,
):
    query = db.query(UnitOfMeasure).options(joinedload(UnitOfMeasure.category))
    if category_id:
        query = query.filter(UnitOfMeasure.category_id == category_id)
    if is_active is not None:
        query = query.filter(UnitOfMeasure.is_active.is_(is_active))
    return [
        UomOut(
            **{k: getattr(u, k) for k in
               ("id", "code", "name", "symbol", "category_id", "factor_to_base",
                "is_base", "decimal_precision", "is_active")},
            category_code=u.category.code if u.category else None,
        )
        for u in query.order_by(UnitOfMeasure.category_id, UnitOfMeasure.code).all()
    ]


@uom_router.post("", response_model=UomOut, status_code=201)
def create_uom(
    payload: UomCreate, db: Session = Depends(get_db), _: User = Depends(require_manager_up)
):
    if db.query(UnitOfMeasure).filter(UnitOfMeasure.code == payload.code).first():
        raise HTTPException(409, f"A unit with code '{payload.code}' already exists")
    if not db.get(UomCategory, payload.category_id):
        raise HTTPException(404, "Unit category not found")
    if payload.is_base:
        existing = db.query(UnitOfMeasure).filter(
            UnitOfMeasure.category_id == payload.category_id, UnitOfMeasure.is_base.is_(True)
        ).first()
        if existing:
            raise HTTPException(
                409,
                f"'{existing.code}' is already the base unit for this category. "
                "A category has exactly one base unit - every other factor is relative to it.",
            )

    unit = UnitOfMeasure(**payload.model_dump())
    db.add(unit)
    db.commit()
    db.refresh(unit)
    return UomOut(
        **{k: getattr(unit, k) for k in
           ("id", "code", "name", "symbol", "category_id", "factor_to_base",
            "is_base", "decimal_precision", "is_active")},
        category_code=unit.category.code if unit.category else None,
    )


@uom_router.patch("/{uom_id}", response_model=UomOut)
def update_uom(
    uom_id: int, payload: UomUpdate,
    db: Session = Depends(get_db), _: User = Depends(require_manager_up),
):
    unit = db.get(UnitOfMeasure, uom_id)
    if not unit:
        raise HTTPException(404, "Unit not found")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("is_active") is False and unit.is_base:
        raise HTTPException(
            400,
            f"'{unit.code}' is the base unit for its category and cannot be deactivated - "
            "every other unit's factor is defined relative to it.",
        )
    for field, value in changes.items():
        setattr(unit, field, value)
    db.commit()
    db.refresh(unit)
    return UomOut(
        **{k: getattr(unit, k) for k in
           ("id", "code", "name", "symbol", "category_id", "factor_to_base",
            "is_base", "decimal_precision", "is_active")},
        category_code=unit.category.code if unit.category else None,
    )


@uom_router.post("/convert", response_model=ConvertResult)
def convert_quantity(
    payload: ConvertRequest, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    frm = db.get(UnitOfMeasure, payload.from_uom_id)
    to = db.get(UnitOfMeasure, payload.to_uom_id)
    if not frm or not to:
        raise HTTPException(404, "Unit not found")
    try:
        result = convert(
            db, payload.quantity, frm, to,
            item_id=payload.item_id, vendor_id=payload.vendor_id,
        )
    except UomConversionError as e:
        raise HTTPException(400, str(e)) from e
    return ConvertResult(quantity=result, from_uom=frm.code, to_uom=to.code)


@uom_router.post("/validate-pair")
def validate_pair(
    from_uom_id: int, to_uom_id: int,
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    """Used by the admin UI before saving a standard conversion rule."""
    frm = db.get(UnitOfMeasure, from_uom_id)
    to = db.get(UnitOfMeasure, to_uom_id)
    if not frm or not to:
        raise HTTPException(404, "Unit not found")
    try:
        validate_conversion_pair(frm, to)
    except UomConversionError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True}
