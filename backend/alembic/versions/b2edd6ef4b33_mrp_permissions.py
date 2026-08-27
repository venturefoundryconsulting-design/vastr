"""mrp permissions

Revision ID: b2edd6ef4b33
Revises: 7b08953711f7
Create Date: 2026-08-20

MRP itself is stateless - it computes requirements fresh from
production_order_materials, stock_levels and stock_reservations on every call,
so there is no MRP table to create. This migration only seeds its two
permission codes. `mrp.generate_po` is separate from `mrp.view` because viewing
shortages is harmless while drafting purchase orders commits paperwork, even as
a DRAFT.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2edd6ef4b33"
down_revision: Union[str, None] = "7b08953711f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_PERMISSIONS = [
    ("mrp.view", "Purchasing", "View material requirement planning"),
    ("mrp.generate_po", "Purchasing", "Draft purchase orders from MRP shortages"),
]
ALL_CODES = [c for c, _, _ in NEW_PERMISSIONS]
ROLE_GRANTS = {
    "TENANT_OWNER": ALL_CODES, "ADMIN": ALL_CODES, "MANAGER": ALL_CODES,
    "INVENTORY": ALL_CODES,
    "VIEWER": ["mrp.view"],
}


def upgrade() -> None:
    bind = op.get_bind()
    permissions_t = sa.table("permissions", sa.column("id", sa.Integer), sa.column("code", sa.String),
                             sa.column("category", sa.String), sa.column("description", sa.String))
    role_permissions_t = sa.table("role_permissions", sa.column("role", sa.String),
                                  sa.column("permission_id", sa.Integer))
    code_to_id = {}
    for code, category, description in NEW_PERMISSIONS:
        existing = bind.execute(sa.text("SELECT id FROM permissions WHERE code = :c"), {"c": code}).scalar()
        code_to_id[code] = existing or bind.execute(
            permissions_t.insert().values(code=code, category=category, description=description)
            .returning(permissions_t.c.id)).scalar_one()
    rows = [{"role": r, "permission_id": code_to_id[c]} for r, codes in ROLE_GRANTS.items() for c in codes
            if not bind.execute(sa.text("SELECT 1 FROM role_permissions WHERE role=:r AND permission_id=:p"),
                                {"r": r, "p": code_to_id[c]}).scalar()]
    if rows:
        bind.execute(role_permissions_t.insert(), rows)


def downgrade() -> None:
    bind = op.get_bind()
    codes = [c for c, _, _ in NEW_PERMISSIONS]
    bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id IN "
                         "(SELECT id FROM permissions WHERE code = ANY(:c))"), {"c": codes})
    bind.execute(sa.text("DELETE FROM permissions WHERE code = ANY(:c)"), {"c": codes})
