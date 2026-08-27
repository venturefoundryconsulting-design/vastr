"""Test fixtures for the quantity-migration suite.

Builds a throwaway database (tanisi_erp_test) and brings it up with the real
Alembic migrations rather than ``Base.metadata.create_all``. That matters here:
the whole point of Phase 1 is a migration, so the tests must exercise what the
migration actually produced - including the NUMERIC(14,4) column types - not a
schema conjured straight from the models.

Each test runs inside a transaction that is rolled back afterwards, so tests
neither see nor disturb one another.
"""

import os

# Must be set before anything imports app.core.config, which reads it at import
# time to build the engine.
TEST_DB_NAME = "tanisi_erp_test"
_ADMIN_URL = os.environ.get(
    "TEST_ADMIN_DATABASE_URL", "postgresql+psycopg2://tanisi:tanisi@localhost:5433/postgres"
)
_TEST_URL = os.environ.get(
    "TEST_DATABASE_URL", f"postgresql+psycopg2://tanisi:tanisi@localhost:5433/{TEST_DB_NAME}"
)
os.environ["DATABASE_URL"] = _TEST_URL

from decimal import Decimal  # noqa: E402

import pytest  # noqa: E402
import sqlalchemy as sa  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.tenant_context import register_tenant_isolation, tenant_scope  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.inventory import StockLevel  # noqa: E402
from app.models.outlet import Outlet  # noqa: E402
from app.models.product import Category, Product, ProductVariant  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402

# app.main does this at startup; tests bypass app.main, so wire the tenant
# filter/stamp events here or every insert lands with tenant_id NULL.
register_tenant_isolation()


@pytest.fixture(scope="session")
def _database():
    """Drop, recreate, and migrate the test database once per test session."""
    admin = sa.create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(
            sa.text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :n AND pid <> pg_backend_pid()"
            ),
            {"n": TEST_DB_NAME},
        )
        conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}"'))
        conn.execute(sa.text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    admin.dispose()

    from alembic import command
    from alembic.config import Config

    cfg = Config(os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", _TEST_URL)
    cfg.set_main_option(
        "script_location", os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic")
    )
    command.upgrade(cfg, "head")

    engine = sa.create_engine(_TEST_URL)
    yield engine
    engine.dispose()


@pytest.fixture()
def db(_database) -> Session:
    """A session wrapped in a transaction that is rolled back after each test.

    ``join_transaction_mode="create_savepoint"`` is what makes this hold even
    though the router functions under test call ``session.commit()``: their
    commits release a SAVEPOINT instead of ending the outer transaction, so the
    final rollback still undoes everything. Without it the first committing test
    leaks its rows into every later one.
    """
    connection = _database.connect()
    trans = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        with tenant_scope(1):
            yield session
    finally:
        session.close()
        if trans.is_active:
            trans.rollback()
        connection.close()


@pytest.fixture()
def tenant(db) -> Tenant:
    """Tenant 1, which the multi-tenant foundation migration (b0ec8901d716)
    already creates to own pre-existing rows - so this reuses it rather than
    colliding with it."""
    existing = db.get(Tenant, 1)
    if existing:
        return existing
    t = Tenant(id=1, company_name="Test Boutique", slug="test-boutique")
    db.add(t)
    db.flush()
    return t


@pytest.fixture()
def outlet(db, tenant) -> Outlet:
    o = Outlet(name="Main Store", code="MAIN")
    db.add(o)
    db.flush()
    return o


@pytest.fixture()
def warehouse(db, tenant) -> Outlet:
    w = Outlet(name="Fabric Room", code="FAB", is_warehouse=True)
    db.add(w)
    db.flush()
    return w


@pytest.fixture()
def user(db, tenant, outlet) -> User:
    u = User(
        tenant_id=tenant.id,
        name="Test Admin",
        email="test-admin@example.test",
        hashed_password="x",
        role=UserRole.ADMIN,
        outlet_id=outlet.id,
    )
    db.add(u)
    db.flush()
    return u


@pytest.fixture()
def customer(db, tenant) -> Customer:
    c = Customer(name="Riya Sharma", phone="9000000001")
    db.add(c)
    db.flush()
    return c


@pytest.fixture()
def fabric(db, tenant) -> ProductVariant:
    """A variant standing in for a raw material sold by the metre."""
    cat = Category(name="Fabric")
    db.add(cat)
    db.flush()
    p = Product(name="Silk Fabric", category_id=cat.id)
    db.add(p)
    db.flush()
    v = ProductVariant(
        product_id=p.id,
        sku="FAB-SLK-RED-001",
        color="Red",
        cost_price=Decimal("450.00"),
        selling_price=Decimal("900.00"),
        mrp=Decimal("1000.00"),
        reorder_level=5,
    )
    db.add(v)
    db.flush()
    return v


@pytest.fixture()
def garment(db, tenant) -> ProductVariant:
    """A whole-unit finished good, for the integer-compatibility cases."""
    p = Product(name="Designer Lehenga")
    db.add(p)
    db.flush()
    v = ProductVariant(
        product_id=p.id,
        sku="GAR-LHNG-001",
        size="M",
        cost_price=Decimal("8000.00"),
        selling_price=Decimal("15000.00"),
        mrp=Decimal("18000.00"),
    )
    db.add(v)
    db.flush()
    return v


def stock_of(db: Session, variant_id: int, outlet_id: int) -> Decimal:
    level = (
        db.query(StockLevel)
        .filter(StockLevel.variant_id == variant_id, StockLevel.outlet_id == outlet_id)
        .first()
    )
    return level.quantity if level else Decimal("0")
