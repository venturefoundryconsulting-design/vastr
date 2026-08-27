"""backfill opening stock movements

Revision ID: 078d64dd5db5
Revises: 63a36eea9b05
Create Date: 2026-08-19

Phase 3A, step 2 of 2 - the ledger integrity fix.

THE PROBLEM
-----------
``app/seed.py`` (and any opening-balance import before this) wrote a starting
quantity straight onto ``stock_levels.quantity`` without a matching row in
``stock_movements``. Replaying the ledger therefore did not reproduce the cached
balance: on the development database, 7 of 8 stock levels disagreed, by exactly
the seeded opening amount (20, 2, 15, 6, 30, 3, 10).

That gap is tolerable for a retail app where stock_levels is treated as truth. It
is not tolerable for manufacturing, where reservations, consumption and costing
all reason about what the ledger says happened.

THE FIX
-------
For every stock level, compute

    drift = stock_levels.quantity - COALESCE(SUM(stock_movements.quantity_delta), 0)

and, where drift <> 0, write exactly one OPENING_STOCK movement for that drift.
By construction the ledger then replays to the cached balance.

WHY THIS CANNOT DOUBLE-COUNT
----------------------------
The drift is computed *after* summing the movements that already exist, so any
real historical movement is already netted off. A stock level whose ledger
already reconciles (drift = 0) gets no row at all - variant 2 / outlet 3 in the
dev data is exactly that case and is deliberately skipped.

IDEMPOTENT
----------
Re-running recomputes drift against the rows now present. After a successful run
every drift is 0, so a second run inserts nothing. Safe to re-apply, and safe to
run against a database that was already partially backfilled.

The movement is stamped at the stock level's own created_at, so it sorts before
the transactions that followed it in any chronological replay.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "078d64dd5db5"
down_revision: Union[str, None] = "63a36eea9b05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


BACKFILL_NOTE = "Opening balance reconstructed by migration 078d64dd5db5 (Phase 3A)"


def upgrade() -> None:
    conn = op.get_bind()

    inserted = conn.execute(sa.text(f"""
        WITH replay AS (
            SELECT variant_id, outlet_id, SUM(quantity_delta) AS ledger
            FROM stock_movements
            GROUP BY variant_id, outlet_id
        ),
        drift AS (
            SELECT sl.tenant_id,
                   sl.variant_id,
                   sl.outlet_id,
                   sl.created_at,
                   sl.quantity - COALESCE(r.ledger, 0) AS delta
            FROM stock_levels sl
            LEFT JOIN replay r
                   ON r.variant_id = sl.variant_id
                  AND r.outlet_id  = sl.outlet_id
        )
        INSERT INTO stock_movements
            (tenant_id, variant_id, outlet_id, movement_type, quantity_delta,
             reference_type, reference_id, note, created_by_id, created_at, updated_at)
        SELECT tenant_id, variant_id, outlet_id, 'OPENING_STOCK', delta,
               'opening_balance', NULL, :note, NULL, created_at, now()
        FROM drift
        WHERE delta <> 0
        RETURNING id
    """), {"note": BACKFILL_NOTE}).fetchall()

    # Prove the invariant here, inside the migration's own transaction: if the
    # backfill did not actually reconcile the ledger, roll back rather than
    # leave the database in a state the manufacturing phase would trust wrongly.
    remaining = conn.execute(sa.text("""
        WITH replay AS (
            SELECT variant_id, outlet_id, SUM(quantity_delta) AS ledger
            FROM stock_movements GROUP BY variant_id, outlet_id
        )
        SELECT count(*)
        FROM stock_levels sl
        LEFT JOIN replay r ON r.variant_id = sl.variant_id AND r.outlet_id = sl.outlet_id
        WHERE sl.quantity <> COALESCE(r.ledger, 0)
    """)).scalar_one()

    if remaining:
        raise RuntimeError(
            f"Opening-stock backfill did not reconcile: {remaining} stock level(s) still "
            "disagree with their ledger. Refusing to commit a half-corrected ledger."
        )

    print(f"[3A] wrote {len(inserted)} OPENING_STOCK movement(s); ledger reconciles")


def downgrade() -> None:
    """Remove only the rows this migration created.

    Matched on movement_type *and* the note, so a genuine OPENING_STOCK recorded
    by a user after the migration ran is left alone - reverting the backfill must
    not delete real business data.
    """
    op.execute(
        sa.text(
            "DELETE FROM stock_movements "
            "WHERE movement_type = 'OPENING_STOCK' AND note = :note"
        ).bindparams(note=BACKFILL_NOTE)
    )
