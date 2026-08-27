"""production outputs table

Revision ID: 2a381270b1ed
Revises: a55cf911332c
Create Date: 2026-08-20

Phase 3E - production output and partial completion.

One table plus two permission codes. Additive; nothing existing changes.
The produced/cancelled quantity columns it drives already exist on
production_orders from Phase 3C.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "2a381270b1ed"
down_revision: Union[str, None] = "a55cf911332c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

QUANTITY = sa.Numeric(14, 4)

NEW_PERMISSIONS = [
    ("production.output", "Manufacturing", "Record finished output from a production order"),
    ("production.complete", "Manufacturing", "Complete a production order"),
]
ROLE_GRANTS = {
    "TENANT_OWNER": [c for c, _, _ in NEW_PERMISSIONS],
    "ADMIN": [c for c, _, _ in NEW_PERMISSIONS],
    "MANAGER": [c for c, _, _ in NEW_PERMISSIONS],
}


def upgrade() -> None:
    bind = op.get_bind()
    op.create_table(
        "production_outputs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("production_order_id", sa.Integer(), sa.ForeignKey("production_orders.id"),
                  nullable=False, index=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False, index=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("outlets.id"), nullable=False),
        sa.Column("quantity", QUANTITY, nullable=False),
        sa.Column("uom_id", sa.Integer(), sa.ForeignKey("units_of_measure.id"), nullable=True),
        sa.Column("stock_movement_id", sa.Integer(), sa.ForeignKey("stock_movements.id"), nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("produced_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_production_output_qty_positive"),
    )
    op.create_index("ix_production_outputs_order", "production_outputs", ["production_order_id"])
    op.create_index("ix_production_outputs_item", "production_outputs", ["item_id"])

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
    # Outputs created finished stock. Dropping them would orphan real inventory.
    produced = bind.execute(sa.text("SELECT count(*) FROM production_outputs")).scalar_one()
    if produced:
        raise RuntimeError(
            f"Cannot downgrade: {produced} production output(s) have already created finished "
            "stock. Dropping this table would orphan those inventory movements."
        )
    codes = [c for c, _, _ in NEW_PERMISSIONS]
    bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id IN "
                         "(SELECT id FROM permissions WHERE code = ANY(:c))"), {"c": codes})
    bind.execute(sa.text("DELETE FROM permissions WHERE code = ANY(:c)"), {"c": codes})
    op.drop_index("ix_production_outputs_item", table_name="production_outputs")
    op.drop_index("ix_production_outputs_order", table_name="production_outputs")
    op.drop_table("production_outputs")
