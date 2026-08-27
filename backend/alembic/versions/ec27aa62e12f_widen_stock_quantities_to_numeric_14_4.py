"""widen stock quantities to Numeric(14,4)

Revision ID: ec27aa62e12f
Revises: d351fa12ad6c
Create Date: 2026-08-19 22:21:47.935844

Phase 1 of the manufacturing programme (see MANUFACTURING_ARCHITECTURE.md).

Widens every *stock* quantity column from INTEGER to NUMERIC(14,4) so the system
can express 4.5 m of fabric, 0.125 kg of beads, 200.75 g of thread. Nothing else
changes in this migration by design - it touches the inventory ledger, POS,
returns, purchasing and transfers at once and wants its own deploy and rollback.

Deliberately NOT widened:
  * discount_rules.buy_quantity / get_quantity - a "buy 2 get 1 free" rule counts
    whole units by definition, and the BOGO code uses // and range().
  * label print counts - whole labels.

NOTE ON AUTOGENERATE: `alembic revision --autogenerate` also proposed dropping 12
composite indexes created by 02945bbc9a7d (phase 6 performance indexes). Those
indexes are real and wanted; they only look "removed" because they are declared in
that migration rather than on the models. Those drops were removed by hand. Do not
regenerate this file without re-checking for them.

LOCKING: INTEGER -> NUMERIC changes the on-disk representation, so PostgreSQL
rewrites each table under an ACCESS EXCLUSIVE lock. Writes and reads to these
tables block for the duration. At boutique data volumes this is seconds, but it is
not a non-blocking migration - run it in a maintenance window with the app stopped.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'ec27aa62e12f'
down_revision: Union[str, None] = 'd351fa12ad6c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


QUANTITY = sa.Numeric(precision=14, scale=4)

# (table, column) for every stock quantity in the system.
COLUMNS: list[tuple[str, str]] = [
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


def upgrade() -> None:
    """INTEGER -> NUMERIC(14,4).

    Lossless in both value and meaning: PostgreSQL's integer->numeric cast is
    implicit and exact, so an existing row holding 7 becomes 7.0000, which is the
    same quantity. No backfill or data migration is required.
    """
    for table, column in COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.INTEGER(),
            type_=QUANTITY,
            existing_nullable=False,
            postgresql_using=f"{column}::numeric(14,4)",
        )


def downgrade() -> None:
    """NUMERIC(14,4) -> INTEGER, but only while that is still lossless.

    Once any real decimal quantity has been recorded, going back would silently
    round 4.5 m to 5 m (or 0.125 kg to 0) and corrupt the ledger, so this refuses
    rather than destroying data. Immediately after an upgrade - the case that
    actually matters for a rollback - nothing is fractional and it downgrades
    cleanly.

    To force it anyway, round the offending rows to whole numbers yourself first;
    that makes the loss an explicit, auditable decision instead of a silent one.
    """
    conn = op.get_bind()
    offenders: list[str] = []
    for table, column in COLUMNS:
        fractional = conn.execute(
            sa.text(
                f"SELECT count(*) FROM {table} "  # noqa: S608 - names are from the fixed list above
                f"WHERE {column} IS NOT NULL AND {column} <> trunc({column})"
            )
        ).scalar_one()
        if fractional:
            offenders.append(f"{table}.{column} ({fractional} row(s))")

    if offenders:
        raise RuntimeError(
            "Cannot downgrade: fractional stock quantities exist and would be "
            "rounded away by reverting to INTEGER.\n  "
            + "\n  ".join(offenders)
            + "\nRound these to whole numbers explicitly, then re-run the downgrade."
        )

    for table, column in reversed(COLUMNS):
        op.alter_column(
            table,
            column,
            existing_type=QUANTITY,
            type_=sa.INTEGER(),
            existing_nullable=False,
            postgresql_using=f"{column}::integer",
        )
