"""add production output movement type

Revision ID: a55cf911332c
Revises: debaf64667ce
Create Date: 2026-08-20

Phase 3E, step 1 of 2 - enum label only.

Split for the reason established in Phase 3A and repeated in 3D: PostgreSQL will
not let a new enum value be *used* in the transaction that added it, and Alembic
runs pending migrations in one transaction. Do not merge this into 2a381270b1ed.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "a55cf911332c"
down_revision: Union[str, None] = "debaf64667ce"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("COMMIT")
    op.execute("ALTER TYPE movementtype ADD VALUE IF NOT EXISTS 'PRODUCTION_OUTPUT'")
    op.execute("COMMIT")


def downgrade() -> None:
    # PostgreSQL has no ALTER TYPE ... DROP VALUE; the label is inert unused.
    pass
