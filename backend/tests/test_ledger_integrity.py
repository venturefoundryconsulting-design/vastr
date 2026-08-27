"""Phase 3A - the ledger integrity invariant.

This is a permanent guard, not a one-off check of the backfill. Everything the
manufacturing phase does - availability, reservation, consumption, costing -
reasons about what the ledger says happened. The moment a code path mutates
``stock_levels`` without writing a movement, that reasoning becomes wrong in a way
that is very hard to notice from the UI, because the cached number still looks
plausible.

The invariant:

    for every (variant, outlet):
        stock_levels.quantity == SUM(stock_movements.quantity_delta)

If a change to the codebase breaks a test in this file, the correct fix is almost
never to relax the assertion - it is to route the offending write through
``apply_stock_delta``.
"""

from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.models.inventory import MovementType, StockLevel
from app.services.inventory import apply_stock_delta
from tests.conftest import stock_of

RECONCILE_SQL = sa.text("""
    WITH replay AS (
        SELECT variant_id, outlet_id, SUM(quantity_delta) AS ledger
        FROM stock_movements
        GROUP BY variant_id, outlet_id
    )
    SELECT sl.variant_id, sl.outlet_id, sl.quantity AS cached,
           COALESCE(r.ledger, 0) AS ledger
    FROM stock_levels sl
    LEFT JOIN replay r ON r.variant_id = sl.variant_id AND r.outlet_id = sl.outlet_id
    WHERE sl.quantity <> COALESCE(r.ledger, 0)
""")


def assert_ledger_reconciles(db):
    """Shared assertion - call this at the end of any test that moves stock."""
    drift = db.execute(RECONCILE_SQL).fetchall()
    assert not drift, "ledger does not reconcile with cached stock: " + ", ".join(
        f"variant {d.variant_id}/outlet {d.outlet_id}: cached {d.cached} vs ledger {d.ledger}"
        for d in drift
    )


# ---------------------------------------------------------------- the invariant


def test_ledger_reconciles_on_a_clean_database(db, tenant):
    assert_ledger_reconciles(db)


def test_ledger_reconciles_after_mixed_movements(db, fabric, garment, outlet, warehouse):
    """Receipts, sales, transfers and adjustments, decimal and whole, must all
    leave the ledger and the cache agreeing."""
    moves = [
        (fabric, warehouse, Decimal("50.5"), MovementType.OPENING_STOCK),
        (fabric, warehouse, Decimal("25"), MovementType.PURCHASE_RECEIPT),
        (fabric, warehouse, Decimal("-4.5"), MovementType.ADJUSTMENT),
        (fabric, outlet, Decimal("10.25"), MovementType.TRANSFER_IN),
        (garment, outlet, Decimal("12"), MovementType.OPENING_STOCK),
        (garment, outlet, Decimal("-3"), MovementType.SALE),
        (garment, outlet, Decimal("1"), MovementType.RETURN),
    ]
    for item, loc, delta, kind in moves:
        apply_stock_delta(db, variant_id=item.id, outlet_id=loc.id,
                          quantity_delta=delta, movement_type=kind)
    db.flush()

    assert stock_of(db, fabric.id, warehouse.id) == Decimal("71.0000")
    assert stock_of(db, garment.id, outlet.id) == Decimal("10.0000")
    assert_ledger_reconciles(db)


def test_opening_stock_is_a_first_class_movement_type(db, fabric, warehouse):
    """The whole point of 3A: an opening balance is a ledger event."""
    apply_stock_delta(db, variant_id=fabric.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("100"), movement_type=MovementType.OPENING_STOCK,
                      reference_type="opening_balance")
    db.flush()
    row = db.execute(sa.text(
        "SELECT movement_type, quantity_delta FROM stock_movements "
        "WHERE variant_id = :v AND outlet_id = :o"
    ), {"v": fabric.id, "o": warehouse.id}).one()
    assert row.movement_type == "OPENING_STOCK"
    assert row.quantity_delta == Decimal("100.0000")
    assert_ledger_reconciles(db)


def test_a_direct_write_to_stock_levels_is_caught(db, fabric, warehouse):
    """Demonstrates what the invariant protects against.

    This deliberately does the wrong thing - bypassing apply_stock_delta - and
    asserts the guard notices. It is the regression test for the exact bug that
    seed.py had before Phase 3A.
    """
    db.add(StockLevel(variant_id=fabric.id, outlet_id=warehouse.id, quantity=Decimal("42")))
    db.flush()
    with pytest.raises(AssertionError, match="does not reconcile"):
        assert_ledger_reconciles(db)


def test_backfill_logic_is_idempotent(db, fabric, warehouse):
    """Re-running the migration's own drift query after it has been applied must
    find nothing left to write."""
    apply_stock_delta(db, variant_id=fabric.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("7.5"), movement_type=MovementType.OPENING_STOCK)
    db.flush()
    remaining = db.execute(sa.text("""
        WITH replay AS (
            SELECT variant_id, outlet_id, SUM(quantity_delta) AS ledger
            FROM stock_movements GROUP BY variant_id, outlet_id
        )
        SELECT count(*) FROM stock_levels sl
        LEFT JOIN replay r ON r.variant_id = sl.variant_id AND r.outlet_id = sl.outlet_id
        WHERE sl.quantity - COALESCE(r.ledger, 0) <> 0
    """)).scalar_one()
    assert remaining == 0


def test_movements_are_never_updated_in_place(db, fabric, warehouse):
    """Invariant 10 - history is immutable. Corrections are new rows.

    Checks the shape of the audit trail rather than trying to forbid UPDATE at
    the database level: two opposing movements, not one edited movement.
    """
    apply_stock_delta(db, variant_id=fabric.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("10"), movement_type=MovementType.PURCHASE_RECEIPT)
    apply_stock_delta(db, variant_id=fabric.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("-10"), movement_type=MovementType.ADJUSTMENT,
                      note="reversal of an over-receipt")
    db.flush()
    rows = db.execute(sa.text(
        "SELECT quantity_delta FROM stock_movements WHERE variant_id = :v ORDER BY id"
    ), {"v": fabric.id}).fetchall()
    assert [r.quantity_delta for r in rows] == [Decimal("10.0000"), Decimal("-10.0000")]
    assert stock_of(db, fabric.id, warehouse.id) == Decimal("0.0000")
    assert_ledger_reconciles(db)
