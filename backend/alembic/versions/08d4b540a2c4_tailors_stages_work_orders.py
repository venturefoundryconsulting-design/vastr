"""tailors stages work orders

Revision ID: 08d4b540a2c4
Revises: 9531a69e270c
Create Date: 2026-08-20

Phase 3F - the tailor layer.

Four tables, six permission codes, and the nine default production stages seeded
per tenant. Stages are seeded as *data* precisely so a boutique can add "Beading"
or drop "Handwork" without a release - nothing in the application branches on a
stage code.

Tailors are resources, not inventory locations: no stock table references a
tailor and none should. That decision is recorded in MANUFACTURING_ARCHITECTURE.md.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "08d4b540a2c4"
down_revision: Union[str, None] = "9531a69e270c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

QUANTITY = sa.Numeric(14, 4)
MONEY = sa.Numeric(12, 2)

PAY_MODEL = postgresql.ENUM(
    "PER_GARMENT", "PER_STAGE", "PER_PIECE", "HOURLY", "FIXED",
    name="paymodel", create_type=False,
)
WO_STATUS = postgresql.ENUM(
    "PENDING", "ASSIGNED", "IN_PROGRESS", "PAUSED", "COMPLETED", "REWORK", "CANCELLED",
    name="workorderstatus", create_type=False,
)

# (code, name, sequence, is_qc)
DEFAULT_STAGES = [
    ("DESIGN", "Design", 10, False),
    ("MATERIAL_PREP", "Material Preparation", 20, False),
    ("CUTTING", "Cutting", 30, False),
    ("STITCHING", "Stitching", 40, False),
    ("EMBROIDERY", "Embroidery", 50, False),
    ("HANDWORK", "Handwork", 60, False),
    ("FINISHING", "Finishing", 70, False),
    ("QUALITY_CHECK", "Quality Check", 80, True),
    ("COMPLETED", "Completed", 90, False),
]

NEW_PERMISSIONS = [
    ("tailors.view", "Manufacturing", "View tailors and their workload"),
    ("tailors.manage", "Manufacturing", "Create and edit tailors and skills"),
    ("stages.manage", "Manufacturing", "Configure production stages"),
    ("work_orders.view", "Manufacturing", "View all work orders"),
    ("work_orders.assign", "Manufacturing", "Create and assign work orders"),
    ("work_orders.own", "Manufacturing", "See and drive your own work orders"),
]

ROLE_GRANTS = {
    "TENANT_OWNER": [c for c, _, _ in NEW_PERMISSIONS],
    "ADMIN": [c for c, _, _ in NEW_PERMISSIONS],
    "MANAGER": [c for c, _, _ in NEW_PERMISSIONS],
    "INVENTORY": ["tailors.view", "work_orders.view"],
    "VIEWER": ["tailors.view", "work_orders.view"],
    # A tailor sees their own queue and the materials on it. Nothing else -
    # not purchasing, not reports, not other people's work, not settings.
    "TAILOR": ["work_orders.own"],
}


def _ts():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def upgrade() -> None:
    bind = op.get_bind()
    op.execute(
        "DO $$ BEGIN CREATE TYPE paymodel AS ENUM "
        "('PER_GARMENT','PER_STAGE','PER_PIECE','HOURLY','FIXED'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE workorderstatus AS ENUM "
        "('PENDING','ASSIGNED','IN_PROGRESS','PAUSED','COMPLETED','REWORK','CANCELLED'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )

    op.create_table(
        "production_stages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("code", sa.String(40), nullable=False, index=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("default_rate", MONEY, nullable=False, server_default="0"),
        sa.Column("is_qc", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_ts(),
        sa.UniqueConstraint("tenant_id", "code", name="uq_production_stage_tenant_code"),
    )

    op.create_table(
        "tailors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("code", sa.String(30), nullable=False, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("pay_model", PAY_MODEL, nullable=False, server_default="PER_STAGE"),
        sa.Column("default_rate", MONEY, nullable=False, server_default="0"),
        sa.Column("joined_on", sa.Date(), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_ts(),
        sa.UniqueConstraint("tenant_id", "code", name="uq_tailor_tenant_code"),
    )

    op.create_table(
        "tailor_skills",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("tailor_id", sa.Integer(), sa.ForeignKey("tailors.id"), nullable=False, index=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("stage_id", sa.Integer(), sa.ForeignKey("production_stages.id"), nullable=True),
        sa.Column("proficiency", sa.Integer(), nullable=False, server_default="3"),
        *_ts(),
        sa.UniqueConstraint("tenant_id", "tailor_id", "name", name="uq_tailor_skill_name"),
        sa.CheckConstraint("proficiency BETWEEN 1 AND 5", name="ck_tailor_skill_proficiency"),
    )

    op.create_table(
        "work_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("wo_number", sa.String(30), nullable=False, index=True),
        sa.Column("production_order_id", sa.Integer(), sa.ForeignKey("production_orders.id"),
                  nullable=False, index=True),
        sa.Column("stage_id", sa.Integer(), sa.ForeignKey("production_stages.id"),
                  nullable=False, index=True),
        sa.Column("tailor_id", sa.Integer(), sa.ForeignKey("tailors.id"), nullable=True, index=True),
        sa.Column("quantity", QUANTITY, nullable=False),
        sa.Column("completed_quantity", QUANTITY, nullable=False, server_default="0"),
        sa.Column("status", WO_STATUS, nullable=False, server_default="PENDING", index=True),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pay_model", PAY_MODEL, nullable=True),
        sa.Column("rate", MONEY, nullable=False, server_default="0"),
        sa.Column("hours", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("issue_note", sa.String(1000), nullable=True),
        sa.Column("assigned_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        *_ts(),
        sa.UniqueConstraint("tenant_id", "wo_number", name="uq_work_order_tenant_number"),
        sa.CheckConstraint("quantity > 0", name="ck_work_order_qty_positive"),
        sa.CheckConstraint(
            "completed_quantity >= 0 AND completed_quantity <= quantity",
            name="ck_work_order_completed_within_qty",
        ),
    )
    op.create_index("ix_work_orders_tenant_status", "work_orders", ["tenant_id", "status"])
    op.create_index("ix_work_orders_tailor_status", "work_orders", ["tailor_id", "status"])
    op.create_index("ix_work_orders_order", "work_orders", ["production_order_id"])

    # ------------------------------------------------- seed stages per tenant
    stages_t = sa.table(
        "production_stages", sa.column("tenant_id", sa.Integer), sa.column("code", sa.String),
        sa.column("name", sa.String), sa.column("sequence", sa.Integer), sa.column("is_qc", sa.Boolean),
    )
    tenant_ids = [r[0] for r in bind.execute(sa.text("SELECT id FROM tenants")).fetchall()]
    rows = [
        {"tenant_id": t, "code": c, "name": n, "sequence": seq, "is_qc": qc}
        for t in tenant_ids
        for c, n, seq, qc in DEFAULT_STAGES
    ]
    if rows:
        bind.execute(stages_t.insert(), rows)

    # ------------------------------------------------------------ permissions
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
    # The tailor also needs materials.view (created in Phase 3D) so their own
    # work order can show what it consumes.
    mv = bind.execute(sa.text("SELECT id FROM permissions WHERE code = 'materials.view'")).scalar()
    if mv and not bind.execute(
        sa.text("SELECT 1 FROM role_permissions WHERE role = 'TAILOR' AND permission_id = :p"),
        {"p": mv},
    ).scalar():
        grants.append({"role": "TAILOR", "permission_id": mv})
    if grants:
        bind.execute(role_permissions_t.insert(), grants)


def downgrade() -> None:
    bind = op.get_bind()
    codes = [c for c, _, _ in NEW_PERMISSIONS]
    bind.execute(sa.text("DELETE FROM role_permissions WHERE role = 'TAILOR'"))
    bind.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE code = ANY(:c))"
        ),
        {"c": codes},
    )
    bind.execute(sa.text("DELETE FROM permissions WHERE code = ANY(:c)"), {"c": codes})
    op.drop_index("ix_work_orders_order", table_name="work_orders")
    op.drop_index("ix_work_orders_tailor_status", table_name="work_orders")
    op.drop_index("ix_work_orders_tenant_status", table_name="work_orders")
    op.drop_table("work_orders")
    op.drop_table("tailor_skills")
    op.drop_table("tailors")
    op.drop_table("production_stages")
    op.execute("DROP TYPE IF EXISTS workorderstatus")
    op.execute("DROP TYPE IF EXISTS paymodel")
