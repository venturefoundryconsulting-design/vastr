"""phase 6 composite performance indexes

Revision ID: 02945bbc9a7d
Revises: 31a11fe886ba
Create Date: 2026-08-07 01:28:32.903107

Adds (tenant_id, X) composite indexes on the highest-traffic tables, per the
spec's explicit list: (tenant_id, created_at), (tenant_id, status),
(tenant_id, customer_id), (tenant_id, product_id). Every one of these tables
already has a plain index on tenant_id alone (added in the Phase 1
migration) - these composites specifically help the queries that filter by
tenant AND sort/filter by one of these columns in the same query (e.g.
"this tenant's sales, newest first", "this tenant's open purchase orders"),
which a single-column tenant_id index alone can't serve as efficiently.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '02945bbc9a7d'
down_revision: Union[str, None] = '31a11fe886ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, columns) - index name is derived as ix_{table}_tenant_{col...}
INDEXES: list[tuple[str, list[str]]] = [
    ("sales", ["tenant_id", "created_at"]),
    ("sales", ["tenant_id", "customer_id"]),
    ("purchase_orders", ["tenant_id", "status"]),
    ("purchase_orders", ["tenant_id", "created_at"]),
    ("stock_transfers", ["tenant_id", "status"]),
    ("stock_transfers", ["tenant_id", "created_at"]),
    ("stock_movements", ["tenant_id", "created_at"]),
    ("alterations", ["tenant_id", "status"]),
    ("alterations", ["tenant_id", "created_at"]),
    ("alterations", ["tenant_id", "customer_id"]),
    ("returns", ["tenant_id", "created_at"]),
    ("returns", ["tenant_id", "customer_id"]),
    ("campaigns", ["tenant_id", "created_at"]),
    ("product_variants", ["tenant_id", "product_id"]),
    ("discount_rules", ["tenant_id", "product_id"]),
]


def _index_name(table: str, columns: list[str]) -> str:
    return f"ix_{table}_" + "_".join(c.replace("tenant_id", "tenant") for c in columns)


def upgrade() -> None:
    for table, columns in INDEXES:
        op.create_index(_index_name(table, columns), table, columns)


def downgrade() -> None:
    for table, columns in INDEXES:
        op.drop_index(_index_name(table, columns), table_name=table)
