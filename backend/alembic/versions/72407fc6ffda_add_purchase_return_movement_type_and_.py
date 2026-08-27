"""add purchase return movement type and ledger unit cost

Revision ID: 72407fc6ffda
Revises: a6a0ec63719a
Create Date: 2026-08-20

Phase 5, step 1 of 2 - enum label plus one additive column.

Split for the reason established in Phase 3A: PostgreSQL refuses to *use* a new
enum value in the transaction that added it, and Alembic runs pending migrations
in one transaction. Do not merge this into the goods-receipts table migration.

``unit_cost`` on stock_movements is nullable and additive - every existing row
keeps meaning exactly what it did. It gets populated going forward by receipts
and returns; nothing backfills it for history that predates this column, because
no historical cost is recoverable that was not already recorded.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "72407fc6ffda"
down_revision: Union[str, None] = "a6a0ec63719a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "stock_movements",
        sa.Column("unit_cost", sa.Numeric(12, 4), nullable=True),
    )
    op.execute("COMMIT")
    op.execute("ALTER TYPE movementtype ADD VALUE IF NOT EXISTS 'PURCHASE_RETURN'")
    op.execute("COMMIT")


def downgrade() -> None:
    op.drop_column("stock_movements", "unit_cost")
    # PostgreSQL has no ALTER TYPE ... DROP VALUE; the label is inert if unused.
