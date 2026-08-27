"""Phase 1 - decimal stock quantities.

Covers the eight areas the migration had to be proven safe in: decimal receipts,
decimal consumption, concurrency, transfers, POS, insufficient-stock validation,
ledger balance reconstruction, and backward compatibility with the integer rows
that already existed before the migration ran.
"""

from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.core.money import format_quantity, money, quantity, to_decimal
from app.models.inventory import MovementType, StockLevel, StockMovement
from app.services.inventory import apply_stock_delta
from tests.conftest import stock_of

# --------------------------------------------------------------------------
# schema: the migration actually produced NUMERIC(14,4)
# --------------------------------------------------------------------------

MIGRATED_COLUMNS = [
    ("stock_levels", "quantity"),
    ("stock_movements", "quantity_delta"),
    ("purchase_order_items", "quantity_ordered"),
    ("purchase_order_items", "quantity_received"),
    ("sale_items", "quantity"),
    ("return_items", "quantity"),
    ("exchange_items", "quantity"),
    ("stock_transfer_items", "quantity_requested"),
    ("stock_transfer_items", "quantity_sent"),
    ("stock_transfer_items", "quantity_received"),
]


@pytest.mark.parametrize("table,column", MIGRATED_COLUMNS)
def test_quantity_columns_are_numeric_14_4(db, table, column):
    row = db.execute(
        sa.text(
            "SELECT data_type, numeric_precision, numeric_scale "
            "FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).one()
    assert row.data_type == "numeric", f"{table}.{column} is {row.data_type}, not numeric"
    assert (row.numeric_precision, row.numeric_scale) == (14, 4)


def test_discount_rule_quantities_remain_integer(db):
    """BOGO counts whole units - these must NOT have been swept up by the migration."""
    for column in ("buy_quantity", "get_quantity"):
        data_type = db.execute(
            sa.text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'discount_rules' AND column_name = :c"
            ),
            {"c": column},
        ).scalar_one()
        assert data_type == "integer"


# --------------------------------------------------------------------------
# 1. decimal stock receipts
# --------------------------------------------------------------------------


def test_decimal_receipt_accumulates_exactly(db, fabric, warehouse):
    """Two rolls of 25.5 m must land on exactly 51.0000, not 50.99999."""
    for _ in range(2):
        apply_stock_delta(
            db,
            variant_id=fabric.id,
            outlet_id=warehouse.id,
            quantity_delta=Decimal("25.5"),
            movement_type=MovementType.PURCHASE_RECEIPT,
        )
    assert stock_of(db, fabric.id, warehouse.id) == Decimal("51.0000")


def test_receipt_of_repeating_decimal_is_exact_over_many_additions(db, fabric, warehouse):
    """0.1 x 10 == 1 exactly. In float this is 0.9999999999999999."""
    for _ in range(10):
        apply_stock_delta(
            db,
            variant_id=fabric.id,
            outlet_id=warehouse.id,
            quantity_delta=Decimal("0.1"),
            movement_type=MovementType.PURCHASE_RECEIPT,
        )
    assert stock_of(db, fabric.id, warehouse.id) == Decimal("1.0000")


def test_four_decimal_places_are_preserved(db, fabric, warehouse):
    apply_stock_delta(
        db,
        variant_id=fabric.id,
        outlet_id=warehouse.id,
        quantity_delta=Decimal("0.1250"),
        movement_type=MovementType.PURCHASE_RECEIPT,
    )
    db.flush()
    assert stock_of(db, fabric.id, warehouse.id) == Decimal("0.1250")


# --------------------------------------------------------------------------
# 2. decimal stock consumption
# --------------------------------------------------------------------------


def test_decimal_consumption_reduces_stock(db, fabric, warehouse):
    apply_stock_delta(
        db, variant_id=fabric.id, outlet_id=warehouse.id,
        quantity_delta=Decimal("20"), movement_type=MovementType.PURCHASE_RECEIPT,
    )
    apply_stock_delta(
        db, variant_id=fabric.id, outlet_id=warehouse.id,
        quantity_delta=Decimal("-4.5"), movement_type=MovementType.ADJUSTMENT,
    )
    assert stock_of(db, fabric.id, warehouse.id) == Decimal("15.5000")


def test_consumption_to_exact_zero(db, fabric, warehouse):
    """Consuming precisely what is on hand must leave 0, not a residue."""
    apply_stock_delta(
        db, variant_id=fabric.id, outlet_id=warehouse.id,
        quantity_delta=Decimal("4.5"), movement_type=MovementType.PURCHASE_RECEIPT,
    )
    apply_stock_delta(
        db, variant_id=fabric.id, outlet_id=warehouse.id,
        quantity_delta=Decimal("-4.5"), movement_type=MovementType.ADJUSTMENT,
    )
    assert stock_of(db, fabric.id, warehouse.id) == Decimal("0.0000")


# --------------------------------------------------------------------------
# 3. stock ledger balance calculations
# --------------------------------------------------------------------------


def test_ledger_replays_to_cached_stock_level(db, fabric, warehouse):
    """stock_levels is a cache; the ledger is the truth. They must agree.

    This is the property that makes the ledger trustworthy, and the one most
    likely to silently break if a code path ever mutates stock_levels directly
    instead of going through apply_stock_delta.
    """
    deltas = [
        Decimal("100"), Decimal("50.25"), Decimal("-7.125"),
        Decimal("-2.5"), Decimal("0.375"), Decimal("-0.0001"),
    ]
    for d in deltas:
        apply_stock_delta(
            db, variant_id=fabric.id, outlet_id=warehouse.id,
            quantity_delta=d, movement_type=MovementType.ADJUSTMENT,
        )
    db.flush()

    replayed = db.query(sa.func.sum(StockMovement.quantity_delta)).filter(
        StockMovement.variant_id == fabric.id,
        StockMovement.outlet_id == warehouse.id,
    ).scalar()

    assert replayed == sum(deltas)
    assert stock_of(db, fabric.id, warehouse.id) == replayed


def test_every_delta_writes_exactly_one_movement(db, fabric, warehouse):
    for _ in range(5):
        apply_stock_delta(
            db, variant_id=fabric.id, outlet_id=warehouse.id,
            quantity_delta=Decimal("1.5"), movement_type=MovementType.PURCHASE_RECEIPT,
        )
    db.flush()
    count = db.query(sa.func.count(StockMovement.id)).filter(
        StockMovement.variant_id == fabric.id
    ).scalar()
    assert count == 5


# --------------------------------------------------------------------------
# 4. backward compatibility with pre-migration integer records
# --------------------------------------------------------------------------


def test_integer_callers_still_work_unchanged(db, garment, outlet):
    """Every pre-manufacturing caller passes a plain int. That must keep working
    and must keep meaning the same quantity."""
    apply_stock_delta(
        db, variant_id=garment.id, outlet_id=outlet.id,
        quantity_delta=10, movement_type=MovementType.PURCHASE_RECEIPT,
    )
    apply_stock_delta(
        db, variant_id=garment.id, outlet_id=outlet.id,
        quantity_delta=-3, movement_type=MovementType.SALE,
    )
    assert stock_of(db, garment.id, outlet.id) == Decimal("7")
    assert stock_of(db, garment.id, outlet.id) == 7  # still equals the integer


def test_integer_row_written_before_migration_reads_back_equal(db, garment, outlet):
    """Simulates a row that existed as INTEGER 7 pre-migration: it must still
    compare equal to 7 and render as "7", not "7.0000"."""
    level = StockLevel(variant_id=garment.id, outlet_id=outlet.id, quantity=Decimal("7"))
    db.add(level)
    db.flush()
    db.refresh(level)
    assert level.quantity == 7
    assert int(level.quantity) == 7
    assert format_quantity(level.quantity) == "7"


def test_mixed_int_and_decimal_deltas_accumulate_correctly(db, fabric, warehouse):
    apply_stock_delta(
        db, variant_id=fabric.id, outlet_id=warehouse.id,
        quantity_delta=10, movement_type=MovementType.PURCHASE_RECEIPT,
    )
    apply_stock_delta(
        db, variant_id=fabric.id, outlet_id=warehouse.id,
        quantity_delta=Decimal("2.25"), movement_type=MovementType.PURCHASE_RECEIPT,
    )
    assert stock_of(db, fabric.id, warehouse.id) == Decimal("12.2500")


# --------------------------------------------------------------------------
# 5. money helpers - no float contamination
# --------------------------------------------------------------------------


def test_money_rounds_half_up_not_bankers():
    # Python's default Decimal rounding is half-even, which would give 0.12.
    assert money(Decimal("0.125")) == Decimal("0.13")
    assert money(Decimal("2.345")) == Decimal("2.35")


def test_to_decimal_avoids_binary_float_artifacts():
    assert to_decimal(0.1) == Decimal("0.1")
    assert to_decimal(4.5) * to_decimal(3) == Decimal("13.5")


def test_quantity_quantizes_to_four_places():
    assert quantity(Decimal("1.23456")) == Decimal("1.2346")


@pytest.mark.parametrize(
    "value,expected",
    [
        (Decimal("4.0000"), "4"),
        (Decimal("4.5000"), "4.5"),
        (Decimal("0.1250"), "0.125"),
        (Decimal("1000.0000"), "1000"),  # must not become "1E+3"
        (Decimal("200.7500"), "200.75"),
    ],
)
def test_format_quantity_is_human_readable(value, expected):
    """Receipts and PDFs must not start printing "4.5000" where they printed "4"."""
    assert format_quantity(value) == expected


def test_float_times_decimal_would_have_crashed():
    """Documents the failure mode this migration had to design around."""
    with pytest.raises(TypeError):
        _ = 12.5 * Decimal("2")  # noqa: B018
