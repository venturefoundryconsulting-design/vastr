"""production orders and material snapshot

Revision ID: 365d917819aa
Revises: 306442d89ecb
Create Date: 2026-08-20

Phase 3C - production order planning. Planning only: this migration adds no
inventory columns and the code it enables never writes to stock_levels or
stock_movements. Reservation and physical movement are Phase 3D.

ENUM NOTE: productionstatus and productionpriority are *new* types, created and
used inside this one migration, which PostgreSQL permits. The constraint
identified in Phase 3A applies to ALTER TYPE ... ADD VALUE on an *existing*
type - a new value is invisible until its transaction commits. That is a
different situation, and the 3A enum migrations stay split as instructed.

Safe for existing tenants: two new tables and eight new permission codes.
Nothing existing is altered.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "365d917819aa"
down_revision: Union[str, None] = "306442d89ecb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

QUANTITY = sa.Numeric(14, 4)
SCRAP = sa.Numeric(6, 3)

# create_type=False for the same reason as Phase 3B: the types are created once
# explicitly below, and letting create_table emit CREATE TYPE again fails with
# DuplicateObject.
PROD_STATUS = postgresql.ENUM(
    "DRAFT", "PLANNED", "RELEASED", "IN_PROGRESS", "PARTIALLY_COMPLETED",
    "COMPLETED", "ON_HOLD", "CANCELLED", "CLOSED_SHORT",
    name="productionstatus", create_type=False,
)
PROD_PRIORITY = postgresql.ENUM(
    "LOW", "NORMAL", "HIGH", "URGENT", name="productionpriority", create_type=False,
)

NEW_PERMISSIONS = [
    ("production.view", "Manufacturing", "View production orders"),
    ("production.create", "Manufacturing", "Create production orders"),
    ("production.edit", "Manufacturing", "Edit a draft production order"),
    ("production.plan", "Manufacturing", "Mark a production order as planned"),
    ("production.release", "Manufacturing", "Release a production order for execution"),
    ("production.hold", "Manufacturing", "Put a production order on hold or resume it"),
    ("production.cancel", "Manufacturing", "Cancel a production order"),
    ("production.close_short", "Manufacturing",
     "Close a production order below its planned quantity"),
]

ROLE_GRANTS = {
    "TENANT_OWNER": [c for c, _, _ in NEW_PERMISSIONS],
    "ADMIN": [c for c, _, _ in NEW_PERMISSIONS],
    "MANAGER": [c for c, _, _ in NEW_PERMISSIONS],
    # Inventory staff can see what production intends to consume, but not decide it.
    "INVENTORY": ["production.view"],
    "VIEWER": ["production.view"],
}


def _ts():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def upgrade() -> None:
    bind = op.get_bind()
    op.execute(
        "DO $$ BEGIN CREATE TYPE productionstatus AS ENUM ('DRAFT','PLANNED','RELEASED',"
        "'IN_PROGRESS','PARTIALLY_COMPLETED','COMPLETED','ON_HOLD','CANCELLED','CLOSED_SHORT'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE productionpriority AS ENUM ('LOW','NORMAL','HIGH','URGENT'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )

    op.create_table(
        "production_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("po_number", sa.String(30), nullable=False, index=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False, index=True),
        sa.Column("bom_id", sa.Integer(), sa.ForeignKey("boms.id"), nullable=True),
        sa.Column("bom_version_id", sa.Integer(), sa.ForeignKey("bom_versions.id"), nullable=True),
        sa.Column("planned_quantity", QUANTITY, nullable=False),
        sa.Column("produced_quantity", QUANTITY, nullable=False, server_default="0"),
        sa.Column("cancelled_quantity", QUANTITY, nullable=False, server_default="0"),
        sa.Column("uom_id", sa.Integer(), sa.ForeignKey("units_of_measure.id"), nullable=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("outlets.id"), nullable=False, index=True),
        sa.Column("planned_start", sa.Date(), nullable=True),
        sa.Column("planned_completion", sa.Date(), nullable=True),
        sa.Column("actual_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_completion", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", PROD_STATUS, nullable=False, server_default="DRAFT", index=True),
        sa.Column("priority", PROD_PRIORITY, nullable=False, server_default="NORMAL"),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("released_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_short_reason", sa.String(500), nullable=True),
        sa.Column("closed_short_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("closed_short_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resume_status", PROD_STATUS, nullable=True),
        *_ts(),
        sa.UniqueConstraint("tenant_id", "po_number", name="uq_production_order_tenant_number"),
        sa.CheckConstraint("planned_quantity > 0", name="ck_production_order_qty_positive"),
        sa.CheckConstraint("produced_quantity >= 0", name="ck_production_order_produced_non_negative"),
        sa.CheckConstraint("cancelled_quantity >= 0", name="ck_production_order_cancelled_non_negative"),
    )
    op.create_index("ix_production_orders_tenant_status", "production_orders", ["tenant_id", "status"])
    op.create_index("ix_production_orders_tenant_item", "production_orders", ["tenant_id", "item_id"])

    op.create_table(
        "production_order_materials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("production_order_id", sa.Integer(), sa.ForeignKey("production_orders.id"),
                  nullable=False, index=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("bom_component_id", sa.Integer(), sa.ForeignKey("bom_components.id"), nullable=True),
        sa.Column("quantity_per_unit", QUANTITY, nullable=False, server_default="0"),
        sa.Column("base_quantity", QUANTITY, nullable=False),
        sa.Column("scrap_pct", SCRAP, nullable=False, server_default="0"),
        sa.Column("planned_quantity", QUANTITY, nullable=False),
        sa.Column("uom_id", sa.Integer(), sa.ForeignKey("units_of_measure.id"), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("parent_item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=True),
        sa.Column("is_optional", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_subassembly", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        *_ts(),
        sa.CheckConstraint("base_quantity >= 0", name="ck_pom_base_non_negative"),
        sa.CheckConstraint("planned_quantity >= 0", name="ck_pom_planned_non_negative"),
    )
    op.create_index("ix_pom_order_sequence", "production_order_materials",
                    ["production_order_id", "sequence"])
    op.create_index("ix_pom_item", "production_order_materials", ["item_id"])

    # ------------------------------------------------------------ permissions
    permissions_t = sa.table(
        "permissions", sa.column("id", sa.Integer), sa.column("code", sa.String),
        sa.column("category", sa.String), sa.column("description", sa.String),
    )
    role_permissions_t = sa.table(
        "role_permissions", sa.column("role", sa.String), sa.column("permission_id", sa.Integer),
    )

    code_to_id: dict[str, int] = {}
    for code, category, description in NEW_PERMISSIONS:
        existing = bind.execute(sa.text("SELECT id FROM permissions WHERE code = :c"),
                                {"c": code}).scalar()
        code_to_id[code] = existing or bind.execute(
            permissions_t.insert()
            .values(code=code, category=category, description=description)
            .returning(permissions_t.c.id)
        ).scalar_one()

    rows = [
        {"role": role, "permission_id": code_to_id[code]}
        for role, codes in ROLE_GRANTS.items()
        for code in codes
        if not bind.execute(
            sa.text("SELECT 1 FROM role_permissions WHERE role = :r AND permission_id = :p"),
            {"r": role, "p": code_to_id[code]},
        ).scalar()
    ]
    if rows:
        bind.execute(role_permissions_t.insert(), rows)


def downgrade() -> None:
    bind = op.get_bind()
    codes = [c for c, _, _ in NEW_PERMISSIONS]
    bind.execute(
        sa.text("DELETE FROM role_permissions WHERE permission_id IN "
                "(SELECT id FROM permissions WHERE code = ANY(:codes))"),
        {"codes": codes},
    )
    bind.execute(sa.text("DELETE FROM permissions WHERE code = ANY(:codes)"), {"codes": codes})

    op.drop_index("ix_pom_item", table_name="production_order_materials")
    op.drop_index("ix_pom_order_sequence", table_name="production_order_materials")
    op.drop_table("production_order_materials")
    op.drop_index("ix_production_orders_tenant_item", table_name="production_orders")
    op.drop_index("ix_production_orders_tenant_status", table_name="production_orders")
    op.drop_table("production_orders")
    op.execute("DROP TYPE IF EXISTS productionpriority")
    op.execute("DROP TYPE IF EXISTS productionstatus")
