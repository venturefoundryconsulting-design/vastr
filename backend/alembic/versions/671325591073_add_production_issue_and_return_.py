"""add production issue and return movement types

Revision ID: 671325591073
Revises: 365d917819aa
Create Date: 2026-08-20

Phase 3D, step 1 of 2 - enum labels only.

Split from the table migration for the reason established in Phase 3A:
PostgreSQL refuses to *use* a new enum value inside the transaction that added
it, and Alembic runs all pending migrations in one transaction. The explicit
COMMIT below closes that transaction so the labels are durable and visible to the
next revision, letting a single `alembic upgrade head` still work as one deploy
step.

Do not merge this into debaf64667ce for tidiness - it will fail with
UnsafeNewEnumValueUsage the first time anyone issues material on a fresh database.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "671325591073"
down_revision: Union[str, None] = "365d917819aa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("COMMIT")
    op.execute("ALTER TYPE movementtype ADD VALUE IF NOT EXISTS 'PRODUCTION_ISSUE'")
    op.execute("ALTER TYPE movementtype ADD VALUE IF NOT EXISTS 'PRODUCTION_RETURN'")
    op.execute("COMMIT")


def downgrade() -> None:
    # PostgreSQL has no ALTER TYPE ... DROP VALUE. The labels are inert if no row
    # references them; the paired migration removes the rows that would.
    pass
