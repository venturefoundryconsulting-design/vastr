"""add OPENING_STOCK movement type

Revision ID: 63a36eea9b05
Revises: a335a21c1c40
Create Date: 2026-08-19

Phase 3A, step 1 of 2.

Adds only the enum label. The backfill that *uses* it is a separate migration
(3ff1c0d8b2e4) because PostgreSQL refuses to use an enum value inside the same
transaction that added it - the value is not visible to the plan until commit.
Splitting it also means the label lands even if the backfill later needs rerunning.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "63a36eea9b05"
down_revision: Union[str, None] = "a335a21c1c40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Alembic runs every pending migration inside one transaction, so simply
    # putting the backfill in a separate revision is not enough - PostgreSQL
    # still sees the label as uncommitted and raises UnsafeNewEnumValueUsage.
    # Committing here closes that transaction so the label is durable and
    # visible to the next revision, letting a single `alembic upgrade head`
    # work as a deploy step. DDL up to this point is already complete, so the
    # early commit does not split a partial change.
    op.execute("COMMIT")
    op.execute("ALTER TYPE movementtype ADD VALUE IF NOT EXISTS 'OPENING_STOCK'")
    op.execute("COMMIT")


def downgrade() -> None:
    # PostgreSQL has no ALTER TYPE ... DROP VALUE. The label is harmless if
    # unused; the paired backfill migration removes the rows that reference it.
    pass
