"""phase 4 invoice prefix

Revision ID: 5dfe79ab8137
Revises: 02945bbc9a7d
Create Date: 2026-08-07 01:52:19.810271

Adds AppSettings.invoice_prefix (Settings > Business Profile), defaulting
existing rows to "INV" (the literal every sale used before this field
existed) via a server_default, so no existing tenant's invoice numbering
changes.

Note: autogenerate also proposed dropping every Phase 6 composite index
(ix_*_tenant_created_at, _tenant_status, etc.) - those are real, intentional
indexes (see PERFORMANCE_REPORT.md), just not mirrored in any model's
__table_args__ since they were added via raw op.create_index() rather than
a SQLAlchemy Index() declaration. Autogenerate diffs against model metadata,
so it doesn't know they're supposed to exist and proposes removing them.
Stripped those out by hand - only the invoice_prefix column is a real change
here.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5dfe79ab8137'
down_revision: Union[str, None] = '02945bbc9a7d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'app_settings',
        sa.Column('invoice_prefix', sa.String(length=10), nullable=False, server_default='INV'),
    )
    op.alter_column('app_settings', 'invoice_prefix', server_default=None)


def downgrade() -> None:
    op.drop_column('app_settings', 'invoice_prefix')
