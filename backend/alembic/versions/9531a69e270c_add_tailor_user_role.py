"""add tailor user role

Revision ID: 9531a69e270c
Revises: 2a381270b1ed
Create Date: 2026-08-20

Phase 3F, step 1 of 2 - enum label only.

TAILOR is a new value on the existing userrole enum, so it needs the same split
treatment as every other ADD VALUE since Phase 3A. Do not merge into
08d4b540a2c4: that migration grants permissions to the role, which uses the label.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "9531a69e270c"
down_revision: Union[str, None] = "2a381270b1ed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("COMMIT")
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'TAILOR'")
    op.execute("COMMIT")


def downgrade() -> None:
    # PostgreSQL has no ALTER TYPE ... DROP VALUE. Inert while unused.
    pass
