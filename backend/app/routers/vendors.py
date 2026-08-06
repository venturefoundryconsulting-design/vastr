from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, require_manager_up
from app.models.vendor import Vendor, VendorProduct
from app.schemas.vendor import (
    VendorCreate,
    VendorOut,
    VendorProductCreate,
    VendorProductOut,
    VendorUpdate,
)
from app.services.export import ExportFormat, build_export_response

router = APIRouter(prefix="/api/vendors", tags=["vendors"], dependencies=[Depends(require_manager_up)])


def _link_to_out(link: VendorProduct) -> VendorProductOut:
    return VendorProductOut(
        id=link.id,
        vendor_id=link.vendor_id,
        variant_id=link.variant_id,
        vendor_sku=link.vendor_sku,
        cost_price=float(link.cost_price),
        is_preferred=link.is_preferred,
        sku=link.variant.sku,
        product_name=link.variant.display_name,
    )


@router.get("", response_model=list[VendorOut])
def list_vendors(db: Session = Depends(get_db)):
    return db.query(Vendor).filter(Vendor.is_active.is_(True)).order_by(Vendor.name).all()


@router.get("/export")
def export_vendors(format: ExportFormat = "xlsx", db: Session = Depends(get_db)):
    vendors = db.query(Vendor).filter(Vendor.is_active.is_(True)).order_by(Vendor.name).all()
    rows = [
        {
            "name": v.name,
            "contact_person": v.contact_person,
            "whatsapp_number": v.whatsapp_number,
            "phone": v.phone,
            "email": v.email,
            "gstin": v.gstin,
            "payment_terms": v.payment_terms,
        }
        for v in vendors
    ]
    columns = [
        ("name", "Vendor"),
        ("contact_person", "Contact"),
        ("whatsapp_number", "WhatsApp"),
        ("phone", "Phone"),
        ("email", "Email"),
        ("gstin", "GSTIN"),
        ("payment_terms", "Payment Terms"),
    ]
    return build_export_response(rows, columns, "Vendors", format)


@router.get("/{vendor_id}", response_model=VendorOut)
def get_vendor(vendor_id: int, db: Session = Depends(get_db)):
    vendor = db.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(404, "Vendor not found")
    return vendor


@router.post("", response_model=VendorOut)
def create_vendor(payload: VendorCreate, db: Session = Depends(get_db)):
    vendor = Vendor(**payload.model_dump())
    db.add(vendor)
    db.commit()
    db.refresh(vendor)
    return vendor


@router.patch("/{vendor_id}", response_model=VendorOut)
def update_vendor(vendor_id: int, payload: VendorUpdate, db: Session = Depends(get_db)):
    vendor = db.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(404, "Vendor not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(vendor, field, value)
    db.commit()
    db.refresh(vendor)
    return vendor


@router.post("/products", response_model=VendorProductOut)
def link_vendor_product(payload: VendorProductCreate, db: Session = Depends(get_db)):
    link = VendorProduct(**payload.model_dump())
    db.add(link)
    db.commit()
    db.refresh(link)
    return _link_to_out(link)


@router.get("/{vendor_id}/products", response_model=list[VendorProductOut])
def list_vendor_products(vendor_id: int, db: Session = Depends(get_db)):
    links = (
        db.query(VendorProduct)
        .options(joinedload(VendorProduct.variant))
        .filter(VendorProduct.vendor_id == vendor_id)
        .all()
    )
    return [_link_to_out(link) for link in links]


@router.delete("/products/{link_id}")
def unlink_vendor_product(link_id: int, db: Session = Depends(get_db)):
    link = db.get(VendorProduct, link_id)
    if not link:
        raise HTTPException(404, "Link not found")
    db.delete(link)
    db.commit()
    return {"ok": True}
