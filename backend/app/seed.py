"""Populates the database with demo data for local development / testing.

Run with: python -m app.seed
Safe to re-run - skips creation if the admin user already exists.
"""

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.core.tenant_context import tenant_scope
from app.models.customer import Customer
from app.models.inventory import StockLevel
from app.models.outlet import Outlet
from app.models.product import Category, Product, ProductVariant
from app.models.tenant import SubscriptionPlanName, SubscriptionStatus, Tenant
from app.models.user import User, UserRole
from app.models.vendor import Vendor, VendorProduct


def run() -> None:
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == "admin@tanisi.demo.com").first():
            print("Seed data already present, skipping.")
            return

        tenant = db.query(Tenant).filter(Tenant.slug == "tanisi").first()
        if not tenant:
            tenant = Tenant(
                company_name="Tanisi",
                slug="tanisi",
                subscription_plan=SubscriptionPlanName.ENTERPRISE,
                subscription_status=SubscriptionStatus.ACTIVE,
            )
            db.add(tenant)
            db.flush()

        # Every TenantMixin row created below is auto-stamped with tenant.id by
        # the before_flush listener (see app.core.tenant_context) once this
        # scope is active - no need to pass tenant_id to each constructor.
        with tenant_scope(tenant.id):
            _seed_tanisi_demo_data(db, tenant)
    finally:
        db.close()


def _seed_tanisi_demo_data(db, tenant: Tenant) -> None:
        warehouse = Outlet(name="Central Warehouse", code="WH-01", is_warehouse=True, address="Bangalore")
        store1 = Outlet(name="Tanisi - Indiranagar", code="ST-01", address="100ft Road, Indiranagar")
        store2 = Outlet(name="Tanisi - Koramangala", code="ST-02", address="80ft Road, Koramangala")
        db.add_all([warehouse, store1, store2])
        db.flush()

        admin = User(
            name="Admin",
            email="admin@tanisi.demo.com",
            hashed_password=hash_password("admin123"),
            role=UserRole.ADMIN,
            tenant_id=tenant.id,
        )
        manager = User(
            name="Store Manager",
            email="manager@tanisi.demo.com",
            hashed_password=hash_password("manager123"),
            role=UserRole.MANAGER,
            outlet_id=store1.id,
            tenant_id=tenant.id,
        )
        staff = User(
            name="Counter Staff",
            email="staff@tanisi.demo.com",
            hashed_password=hash_password("staff123"),
            role=UserRole.OUTLET_STAFF,
            outlet_id=store1.id,
            tenant_id=tenant.id,
        )
        db.add_all([admin, manager, staff])

        sarees = Category(name="Sarees")
        kurtis = Category(name="Kurtis")
        db.add_all([sarees, kurtis])
        db.flush()

        # whatsapp_number intentionally left blank in seed data: common "placeholder"
        # Indian mobile numbers (e.g. 98765xxxxx sequences) are often real, live WhatsApp
        # accounts. Add a vendor's real number via the Vendors page before testing
        # "Send via WhatsApp", so the pre-filled message goes to the right person.
        vendor1 = Vendor(
            name="Deepa Textiles",
            contact_person="Deepa Goyal",
            phone="9876543210",
            email="orders@deepatextiles.example",
            gstin="29ABCDE1234F1Z5",
            payment_terms="Net 15",
        )
        vendor2 = Vendor(
            name="Sunrise Fabrics",
            contact_person="Ramesh Kumar",
            phone="9876500000",
        )
        db.add_all([vendor1, vendor2])
        db.flush()

        product1 = Product(name="Banarasi Silk Saree", category_id=sarees.id, brand="Tanisi", tax_rate=5)
        product1.variants = [
            ProductVariant(sku="BSS-RED-FS", barcode="8901000000011", color="Red", size="Free Size",
                            cost_price=1800, selling_price=3200, mrp=3500, reorder_level=5),
            ProductVariant(sku="BSS-BLU-FS", barcode="8901000000028", color="Blue", size="Free Size",
                            cost_price=1800, selling_price=3200, mrp=3500, reorder_level=5),
        ]

        product2 = Product(name="Cotton Anarkali Kurti", category_id=kurtis.id, brand="Tanisi", tax_rate=5)
        product2.variants = [
            ProductVariant(sku="CAK-GRN-M", barcode="8901000000035", color="Green", size="M",
                            cost_price=650, selling_price=1200, mrp=1400, reorder_level=8),
            ProductVariant(sku="CAK-GRN-L", barcode="8901000000042", color="Green", size="L",
                            cost_price=650, selling_price=1200, mrp=1400, reorder_level=8),
        ]

        db.add_all([product1, product2])
        db.flush()

        for variant in product1.variants:
            db.add(VendorProduct(vendor_id=vendor1.id, variant_id=variant.id, cost_price=float(variant.cost_price)))
        for variant in product2.variants:
            db.add(VendorProduct(vendor_id=vendor2.id, variant_id=variant.id, cost_price=float(variant.cost_price)))

        # Seed low stock at store1 so a reorder suggestion shows up out of the box
        stock_seed = [
            (product1.variants[0], warehouse, 20),
            (product1.variants[0], store1, 2),
            (product1.variants[1], warehouse, 15),
            (product1.variants[1], store1, 6),
            (product2.variants[0], warehouse, 30),
            (product2.variants[0], store1, 3),
            (product2.variants[1], store2, 10),
        ]
        for variant, outlet, qty in stock_seed:
            db.add(StockLevel(variant_id=variant.id, outlet_id=outlet.id, quantity=qty))

        db.add_all([
            Customer(
                name="Riya Sharma",
                phone="9900011122",
                email="riya.sharma@example.com",
                tags=["VIP"],
                preferred_sizes=["M", "L"],
                preferred_colors=["Red", "Blue"],
                favorite_brands=["Tanisi"],
                credit_balance=500,
                loyalty_points=120,
            ),
            Customer(
                name="Priya Enterprises",
                phone="9900033344",
                email="orders@priyaenterprises.example",
                is_gst_customer=True,
                gstin="29PRIYA1234F1Z5",
                tags=["Wholesale"],
            ),
            Customer(
                name="Anjali Rao",
                phone="9900055566",
                tags=["Regular"],
                preferred_colors=["Green"],
            ),
        ])

        db.commit()
        print("Seed data created.")
        print("Login with admin@tanisi.demo.com / admin123")


if __name__ == "__main__":
    run()
