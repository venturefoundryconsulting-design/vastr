"""costing and report permissions

Revision ID: a7b6b501c16a
Revises: 5c2cf0b20b23
Create Date: 2026-08-20

Phase 3H - production costing and reports.

Permissions only. Costing is entirely derived from data that already exists -
the requirement snapshot, consumption, wastage and work orders - so there is
nothing new to store. Persisting a computed cost would mean two sources of truth
that drift the moment a rate or a consumption record changes.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7b6b501c16a"
down_revision: Union[str, None] = "5c2cf0b20b23"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_PERMISSIONS = [
    ("costing.view", "Manufacturing", "View production cost and variance"),
    ("production.reports", "Manufacturing", "View manufacturing reports"),
]

ROLE_GRANTS = {
    "TENANT_OWNER": [c for c, _, _ in NEW_PERMISSIONS],
    "ADMIN": [c for c, _, _ in NEW_PERMISSIONS],
    "MANAGER": [c for c, _, _ in NEW_PERMISSIONS],
    # Costing is commercially sensitive: an inventory clerk sees quantities, not
    # margins. Viewers get reports but not unit costs.
    "VIEWER": ["production.reports"],
}


def upgrade() -> None:
    bind = op.get_bind()
    permissions_t = sa.table(
        "permissions", sa.column("id", sa.Integer), sa.column("code", sa.String),
        sa.column("category", sa.String), sa.column("description", sa.String),
    )
    role_permissions_t = sa.table(
        "role_permissions", sa.column("role", sa.String), sa.column("permission_id", sa.Integer),
    )
    code_to_id = {}
    for code, category, description in NEW_PERMISSIONS:
        existing = bind.execute(
            sa.text("SELECT id FROM permissions WHERE code = :c"), {"c": code}
        ).scalar()
        code_to_id[code] = existing or bind.execute(
            permissions_t.insert()
            .values(code=code, category=category, description=description)
            .returning(permissions_t.c.id)
        ).scalar_one()

    grants = [
        {"role": r, "permission_id": code_to_id[c]}
        for r, codes in ROLE_GRANTS.items()
        for c in codes
        if not bind.execute(
            sa.text("SELECT 1 FROM role_permissions WHERE role = :r AND permission_id = :p"),
            {"r": r, "p": code_to_id[c]},
        ).scalar()
    ]
    if grants:
        bind.execute(role_permissions_t.insert(), grants)


def downgrade() -> None:
    bind = op.get_bind()
    codes = [c for c, _, _ in NEW_PERMISSIONS]
    bind.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE code = ANY(:c))"
        ),
        {"c": codes},
    )
    bind.execute(sa.text("DELETE FROM permissions WHERE code = ANY(:c)"), {"c": codes})
