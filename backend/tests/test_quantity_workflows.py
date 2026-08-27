"""Phase 1 - the real workflows, driven through the routers.

These call the router functions directly with a live session rather than over
HTTP: the aim is to prove the POS/transfer/purchasing business logic behaves
with decimal quantities, and the auth layer is not what is under test here.
"""

import threading
from decimal import Decimal

import pytest
import sqlalchemy as sa
from fastapi import HTTPException

from app.models.inventory import MovementType, StockLevel
from app.models.transfer import TransferStatus
from app.routers import sales as sales_router
from app.routers import transfers as transfers_router
from app.schemas.sale import SaleCreate, SaleItemCreate
from app.schemas.transfer import (
    DispatchItem,
    DispatchRequest,
    ReceiveItem,
    ReceiveRequest,
    TransferCreate,
    TransferItemCreate,
)
from app.services.inventory import apply_stock_delta
from tests.conftest import stock_of


def seed_stock(db, variant, outlet, qty):
    apply_stock_delta(
        db,
        variant_id=variant.id,
        outlet_id=outlet.id,
        quantity_delta=Decimal(str(qty)),
        movement_type=MovementType.PURCHASE_RECEIPT,
    )
    db.flush()


# --------------------------------------------------------------------------
# POS with decimal quantities
# --------------------------------------------------------------------------


def test_pos_sells_a_decimal_quantity(db, fabric, outlet, user):
    """Sell 2.75 m of fabric over the counter."""
    seed_stock(db, fabric, outlet, "20")

    payload = SaleCreate(
        outlet_id=outlet.id,
        items=[
            SaleItemCreate(
                variant_id=fabric.id,
                quantity=Decimal("2.75"),
                unit_price=900.0,
                tax_rate=5.0,
            )
        ],
    )
    sale = sales_router.checkout(payload, db, user)

    assert stock_of(db, fabric.id, outlet.id) == Decimal("17.2500")
    # 2.75 m x 900 = 2475.00 exactly
    assert Decimal(str(sale.subtotal)) == Decimal("2475.00")


def test_pos_totals_are_exact_with_decimal_quantity(db, fabric, outlet, user):
    """0.1 x 3 x price must not drift the way float would."""
    seed_stock(db, fabric, outlet, "5")
    payload = SaleCreate(
        outlet_id=outlet.id,
        items=[
            SaleItemCreate(
                variant_id=fabric.id, quantity=Decimal("0.3"), unit_price=100.0, tax_rate=0
            )
        ],
    )
    sale = sales_router.checkout(payload, db, user)
    assert Decimal(str(sale.subtotal)) == Decimal("30.00")


def test_pos_still_sells_whole_garments(db, garment, outlet, user):
    """Backward compatibility: the ordinary integer path is untouched."""
    seed_stock(db, garment, outlet, 5)
    payload = SaleCreate(
        outlet_id=outlet.id,
        items=[
            SaleItemCreate(
                variant_id=garment.id, quantity=Decimal("2"), unit_price=15000.0, tax_rate=12.0
            )
        ],
    )
    sale = sales_router.checkout(payload, db, user)
    assert stock_of(db, garment.id, outlet.id) == 3
    assert Decimal(str(sale.subtotal)) == Decimal("30000.00")


# --------------------------------------------------------------------------
# insufficient-stock validation
# --------------------------------------------------------------------------


def test_pos_rejects_oversell_by_a_fraction(db, fabric, outlet, user):
    """4.5 on hand, asking for 4.6 - must be refused, not silently allowed."""
    seed_stock(db, fabric, outlet, "4.5")
    payload = SaleCreate(
        outlet_id=outlet.id,
        items=[
            SaleItemCreate(
                variant_id=fabric.id, quantity=Decimal("4.6"), unit_price=900.0
            )
        ],
    )
    with pytest.raises(HTTPException) as exc:
        sales_router.checkout(payload, db, user)
    assert exc.value.status_code == 400
    assert "Insufficient stock" in exc.value.detail
    assert stock_of(db, fabric.id, outlet.id) == Decimal("4.5000")


def test_pos_allows_selling_exactly_what_is_on_hand(db, fabric, outlet, user):
    """The boundary case: 4.5 requested against 4.5 available must succeed."""
    seed_stock(db, fabric, outlet, "4.5")
    payload = SaleCreate(
        outlet_id=outlet.id,
        items=[
            SaleItemCreate(variant_id=fabric.id, quantity=Decimal("4.5"), unit_price=900.0)
        ],
    )
    sales_router.checkout(payload, db, user)
    assert stock_of(db, fabric.id, outlet.id) == Decimal("0.0000")


def test_oversell_leaves_no_partial_ledger_rows(db, fabric, garment, outlet, user):
    """A rejected multi-line cart must not have decremented the first line."""
    seed_stock(db, fabric, outlet, "10")
    seed_stock(db, garment, outlet, 1)
    payload = SaleCreate(
        outlet_id=outlet.id,
        items=[
            SaleItemCreate(variant_id=fabric.id, quantity=Decimal("2.5"), unit_price=900.0),
            SaleItemCreate(variant_id=garment.id, quantity=Decimal("99"), unit_price=15000.0),
        ],
    )
    with pytest.raises(HTTPException):
        sales_router.checkout(payload, db, user)
    assert stock_of(db, fabric.id, outlet.id) == Decimal("10.0000")


# --------------------------------------------------------------------------
# transfers with decimal quantities
# --------------------------------------------------------------------------


def test_transfer_moves_decimal_quantity_between_outlets(db, fabric, outlet, warehouse, user):
    seed_stock(db, fabric, warehouse, "25.5")

    transfer = transfers_router.create_transfer(
        TransferCreate(
            source_outlet_id=warehouse.id,
            dest_outlet_id=outlet.id,
            items=[TransferItemCreate(variant_id=fabric.id, quantity_requested=Decimal("4.5"))],
        ),
        db,
        user,
    )
    item_id = transfer.items[0].id

    transfers_router.dispatch_transfer(
        transfer.id,
        DispatchRequest(items=[DispatchItem(item_id=item_id, quantity_sent=Decimal("4.5"))]),
        db,
        user,
    )
    assert stock_of(db, fabric.id, warehouse.id) == Decimal("21.0000")
    assert stock_of(db, fabric.id, outlet.id) == Decimal("0")

    transfers_router.receive_transfer(
        transfer.id,
        ReceiveRequest(items=[ReceiveItem(item_id=item_id, quantity_received=Decimal("4.5"))]),
        db,
        user,
    )
    assert stock_of(db, fabric.id, outlet.id) == Decimal("4.5000")
    # nothing evaporated in transit
    assert stock_of(db, fabric.id, warehouse.id) + stock_of(db, fabric.id, outlet.id) == Decimal(
        "25.5000"
    )


def test_transfer_rejects_dispatch_beyond_available(db, fabric, outlet, warehouse, user):
    seed_stock(db, fabric, warehouse, "2.5")
    transfer = transfers_router.create_transfer(
        TransferCreate(
            source_outlet_id=warehouse.id,
            dest_outlet_id=outlet.id,
            items=[TransferItemCreate(variant_id=fabric.id, quantity_requested=Decimal("5"))],
        ),
        db,
        user,
    )
    with pytest.raises(HTTPException) as exc:
        transfers_router.dispatch_transfer(
            transfer.id,
            DispatchRequest(
                items=[DispatchItem(item_id=transfer.items[0].id, quantity_sent=Decimal("2.6"))]
            ),
            db,
            user,
        )
    assert exc.value.status_code == 400
    assert stock_of(db, fabric.id, warehouse.id) == Decimal("2.5000")


def test_partial_decimal_transfer_receipt(db, fabric, outlet, warehouse, user):
    """Send 10.5, receive 6.25 now and 4.25 later."""
    seed_stock(db, fabric, warehouse, "20")
    transfer = transfers_router.create_transfer(
        TransferCreate(
            source_outlet_id=warehouse.id,
            dest_outlet_id=outlet.id,
            items=[TransferItemCreate(variant_id=fabric.id, quantity_requested=Decimal("10.5"))],
        ),
        db,
        user,
    )
    item_id = transfer.items[0].id
    transfers_router.dispatch_transfer(
        transfer.id,
        DispatchRequest(items=[DispatchItem(item_id=item_id, quantity_sent=Decimal("10.5"))]),
        db, user,
    )
    transfers_router.receive_transfer(
        transfer.id,
        ReceiveRequest(items=[ReceiveItem(item_id=item_id, quantity_received=Decimal("6.25"))]),
        db, user,
    )
    assert stock_of(db, fabric.id, outlet.id) == Decimal("6.2500")

    out = transfers_router.receive_transfer(
        transfer.id,
        ReceiveRequest(items=[ReceiveItem(item_id=item_id, quantity_received=Decimal("4.25"))]),
        db, user,
    )
    assert stock_of(db, fabric.id, outlet.id) == Decimal("10.5000")
    assert out.status == TransferStatus.RECEIVED


# --------------------------------------------------------------------------
# concurrency - the SELECT ... FOR UPDATE lock must still serialize writers
# --------------------------------------------------------------------------


def test_concurrent_decimal_adjustments_do_not_lose_updates(_database, db, fabric, warehouse):
    """Two connections adjusting the same stock row must serialize.

    Uses real threads on real connections, because the row lock only exists at
    the database level - a single-session test would prove nothing. The outer
    `db` fixture is only used to create the seed rows, which are committed here
    so the worker connections can see them.
    """
    from sqlalchemy.orm import sessionmaker

    from app.core.tenant_context import tenant_scope
    from app.models.outlet import Outlet
    from app.models.product import Product, ProductVariant
    from app.models.tenant import Tenant

    # Committed seed data, so the worker connections can actually see it. Built
    # through the ORM so column defaults (timezone, currency, plan...) apply.
    seed_conn = _database.connect()
    s = sessionmaker(bind=seed_conn)()
    with tenant_scope(9001):
        s.add(Tenant(id=9001, company_name="Concurrency Co", slug="concurrency-co"))
        s.flush()
        s.add(Outlet(id=9001, name="CC Warehouse", code="CCW", is_warehouse=True))
        s.add(Product(id=9001, name="CC Fabric"))
        s.flush()
        s.add(ProductVariant(id=9001, product_id=9001, sku="CC-FAB-001"))
        s.flush()
        s.add(StockLevel(variant_id=9001, outlet_id=9001, quantity=Decimal("0")))
        s.commit()
    s.close()

    iterations = 20
    delta = Decimal("0.25")
    errors: list[Exception] = []

    def worker():
        session = sessionmaker(bind=_database)()
        try:
            with tenant_scope(9001):
                for _ in range(iterations):
                    apply_stock_delta(
                        session,
                        variant_id=9001,
                        outlet_id=9001,
                        quantity_delta=delta,
                        movement_type=MovementType.ADJUSTMENT,
                    )
                    session.commit()
        except Exception as e:  # noqa: BLE001 - surfaced via the errors list
            errors.append(e)
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"worker(s) raised: {errors}"

    verify = sessionmaker(bind=_database)()
    try:
        with tenant_scope(9001):
            final = (
                verify.query(StockLevel.quantity)
                .filter(StockLevel.variant_id == 9001, StockLevel.outlet_id == 9001)
                .scalar()
            )
            ledger = verify.execute(
                sa.text(
                    "SELECT coalesce(sum(quantity_delta), 0) FROM stock_movements "
                    "WHERE variant_id = 9001 AND outlet_id = 9001"
                )
            ).scalar_one()
        expected = delta * iterations * len(threads)  # 0.25 * 20 * 4 = 20
        assert final == expected, f"lost update: expected {expected}, got {final}"
        assert ledger == expected, "ledger and cached balance disagree"
    finally:
        # Clean up the committed rows - they live outside the test transaction.
        with tenant_scope(None):
            for stmt in (
                "DELETE FROM stock_movements WHERE variant_id = 9001",
                "DELETE FROM stock_levels WHERE variant_id = 9001",
                "DELETE FROM product_variants WHERE id = 9001",
                "DELETE FROM products WHERE id = 9001",
                "DELETE FROM outlets WHERE id = 9001",
                "DELETE FROM tenants WHERE id = 9001",
            ):
                verify.execute(sa.text(stmt))
            verify.commit()
        verify.close()
        seed_conn.close()
