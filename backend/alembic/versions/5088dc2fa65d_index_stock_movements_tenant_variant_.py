"""index stock movements tenant variant outlet

Revision ID: 5088dc2fa65d
Revises: b2edd6ef4b33
Create Date: 2026-08-27 22:17:20.521069

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5088dc2fa65d'
down_revision: Union[str, None] = 'b2edd6ef4b33'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_stock_movements_tenant_variant_outlet",
        "stock_movements",
        ["tenant_id", "variant_id", "outlet_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_stock_movements_tenant_variant_outlet", table_name="stock_movements")
