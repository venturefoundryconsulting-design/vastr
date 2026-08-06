import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, get_db, require_manager_up
from app.core.config import settings
from app.models.inventory import StockLevel
from app.models.product import Category, ImageAngle, Product, ProductImage, ProductVariant
from app.schemas.product import (
    BulkImportResult,
    CategoryCreate,
    CategoryOut,
    LabelPrintRequest,
    ProductCreate,
    ProductImageOut,
    ProductImageUpdate,
    ProductOut,
    ProductUpdate,
    VariantCreate,
    VariantOut,
    VariantUpdate,
    VariantWithStock,
)
from app.services.bulk_import import build_template_xlsx, import_rows, parse_rows
from app.services.export import ExportFormat, build_export_response
from app.services.labels_pdf import LabelItem, render_labels_pdf

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

router = APIRouter(prefix="/api/products", tags=["products"])
categories_router = APIRouter(prefix="/api/categories", tags=["products"])


@categories_router.get("", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(Category).order_by(Category.name).all()


@categories_router.post("", response_model=CategoryOut)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    category = Category(**payload.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.get("", response_model=list[ProductOut])
def list_products(
    search: str | None = None,
    category_id: int | None = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    query = db.query(Product).options(joinedload(Product.variants)).filter(Product.is_active.is_(True))
    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))
    if category_id:
        query = query.filter(Product.category_id == category_id)
    return query.order_by(Product.name).all()


@router.get("/export")
def export_products(
    search: str | None = None,
    category_id: int | None = None,
    format: ExportFormat = "xlsx",
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    query = db.query(Product).options(joinedload(Product.variants)).filter(Product.is_active.is_(True))
    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))
    if category_id:
        query = query.filter(Product.category_id == category_id)
    products = query.order_by(Product.name).all()

    rows = [
        {
            "product_name": p.name,
            "brand": p.brand,
            "category": p.category.name if p.category else None,
            "hsn_code": p.hsn_code,
            "tax_rate": float(p.tax_rate),
            "sku": v.sku,
            "barcode": v.barcode,
            "size": v.size,
            "color": v.color,
            "cost_price": float(v.cost_price),
            "selling_price": float(v.selling_price),
            "mrp": float(v.mrp),
            "reorder_level": v.reorder_level,
            "active": "Yes" if v.is_active else "No",
        }
        for p in products
        for v in (p.variants or [None])
        if v is not None
    ]
    columns = [
        ("product_name", "Product"),
        ("brand", "Brand"),
        ("category", "Category"),
        ("sku", "SKU"),
        ("barcode", "Barcode"),
        ("size", "Size"),
        ("color", "Color"),
        ("cost_price", "Cost Price"),
        ("selling_price", "Selling Price"),
        ("mrp", "MRP"),
        ("reorder_level", "Reorder Level"),
        ("active", "Active"),
    ]
    return build_export_response(rows, columns, "Products", format)


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    return product


@router.post("", response_model=ProductOut)
def create_product(payload: ProductCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    data = payload.model_dump(exclude={"variants"})
    product = Product(**data)
    for variant_data in payload.variants:
        if db.query(ProductVariant).filter(ProductVariant.sku == variant_data.sku).first():
            raise HTTPException(400, f"SKU '{variant_data.sku}' already exists")
        product.variants.append(ProductVariant(**variant_data.model_dump()))
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


@router.get("/bulk-import/template")
def bulk_import_template():
    content = build_template_xlsx()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="product_import_template.xlsx"'},
    )


@router.post(
    "/bulk-import", response_model=BulkImportResult, dependencies=[Depends(require_manager_up)]
)
async def bulk_import_products(file: UploadFile = File(...), db: Session = Depends(get_db)):
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(400, "File must be under 5MB")
    try:
        rows = parse_rows(file.filename or "", contents)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not rows:
        raise HTTPException(400, "The file has no data rows")
    result = import_rows(db, rows)
    db.commit()
    return result


@router.post("/{product_id}/variants", response_model=VariantOut)
def add_variant(
    product_id: int, payload: VariantCreate, db: Session = Depends(get_db), _=Depends(get_current_user)
):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    if db.query(ProductVariant).filter(ProductVariant.sku == payload.sku).first():
        raise HTTPException(400, f"SKU '{payload.sku}' already exists")
    variant = ProductVariant(product_id=product_id, **payload.model_dump())
    db.add(variant)
    db.commit()
    db.refresh(variant)
    return variant


@router.patch("/variants/{variant_id}", response_model=VariantOut)
def update_variant(
    variant_id: int, payload: VariantUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)
):
    variant = db.get(ProductVariant, variant_id)
    if not variant:
        raise HTTPException(404, "Variant not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(variant, field, value)
    db.commit()
    db.refresh(variant)
    return variant


@router.get("/variants/search", response_model=list[VariantWithStock])
def search_variants(q: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Used by POS / PO screens to find a variant by SKU, barcode or product name."""
    variants = (
        db.query(ProductVariant)
        .join(Product)
        .options(joinedload(ProductVariant.product))
        .filter(
            ProductVariant.is_active.is_(True),
            (ProductVariant.sku.ilike(f"%{q}%"))
            | (ProductVariant.barcode.ilike(f"%{q}%"))
            | (Product.name.ilike(f"%{q}%")),
        )
        .limit(25)
        .all()
    )
    results = []
    for v in variants:
        total = (
            db.query(StockLevel)
            .filter(StockLevel.variant_id == v.id)
            .with_entities(StockLevel.quantity)
            .all()
        )
        results.append(
            VariantWithStock(
                **VariantOut.model_validate(v).model_dump(),
                product_name=v.product.name,
                total_stock=sum(q[0] for q in total),
            )
        )
    return results


@router.post("/labels/pdf")
def print_labels(payload: LabelPrintRequest, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if not payload.items:
        raise HTTPException(400, "Select at least one item to print labels for")

    label_items = []
    for req_item in payload.items:
        if req_item.quantity < 1:
            continue
        variant = (
            db.query(ProductVariant)
            .options(joinedload(ProductVariant.product))
            .filter(ProductVariant.id == req_item.variant_id)
            .first()
        )
        if not variant:
            raise HTTPException(404, f"Product variant {req_item.variant_id} not found")
        label_items.append(
            LabelItem(
                sku=variant.sku,
                barcode=variant.barcode,
                product_name=variant.product.name,
                size=variant.size,
                color=variant.color,
                mrp=float(variant.mrp),
                quantity=req_item.quantity,
            )
        )

    if not label_items:
        raise HTTPException(400, "Select at least one item to print labels for")

    pdf_bytes = render_labels_pdf(label_items, payload.layout)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="labels.pdf"'},
    )


@router.post("/{product_id}/images", response_model=ProductImageOut)
async def upload_product_image(
    product_id: int,
    file: UploadFile = File(...),
    color: str | None = Form(None),
    angle: ImageAngle = Form(ImageAngle.OTHER),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")

    ext = ALLOWED_IMAGE_TYPES.get(file.content_type)
    if not ext:
        raise HTTPException(400, "Only JPEG, PNG or WebP images are allowed")

    product_dir = settings.UPLOAD_DIR / "products" / str(product_id)
    product_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = product_dir / filename
    contents = await file.read()
    if len(contents) > 8 * 1024 * 1024:
        raise HTTPException(400, "Image must be under 8MB")
    dest.write_bytes(contents)

    is_first = not db.query(ProductImage).filter(ProductImage.product_id == product_id).first()
    image = ProductImage(
        product_id=product_id,
        color=color or None,
        angle=angle,
        file_path=f"products/{product_id}/{filename}",
        is_primary=is_first,
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return image


@router.patch("/images/{image_id}", response_model=ProductImageOut)
def update_product_image(
    image_id: int, payload: ProductImageUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)
):
    image = db.get(ProductImage, image_id)
    if not image:
        raise HTTPException(404, "Image not found")
    data = payload.model_dump(exclude_unset=True)
    if data.get("is_primary"):
        db.query(ProductImage).filter(
            ProductImage.product_id == image.product_id, ProductImage.id != image_id
        ).update({"is_primary": False})
    for field, value in data.items():
        setattr(image, field, value)
    db.commit()
    db.refresh(image)
    return image


@router.delete("/images/{image_id}", status_code=204)
def delete_product_image(image_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    image = db.get(ProductImage, image_id)
    if not image:
        raise HTTPException(404, "Image not found")
    file_path = settings.UPLOAD_DIR / image.file_path
    was_primary = image.is_primary
    product_id = image.product_id
    db.delete(image)
    db.commit()
    if file_path.exists():
        try:
            Path(file_path).unlink()
        except OSError:
            pass
    if was_primary:
        next_image = (
            db.query(ProductImage)
            .filter(ProductImage.product_id == product_id)
            .order_by(ProductImage.sort_order)
            .first()
        )
        if next_image:
            next_image.is_primary = True
            db.commit()
