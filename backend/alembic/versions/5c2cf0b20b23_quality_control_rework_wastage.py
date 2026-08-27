"""quality control rework wastage

Revision ID: 5c2cf0b20b23
Revises: 08d4b540a2c4
Create Date: 2026-08-20

Phase 3G - QC, rework and wastage.

Six tables, one new column on production_order_materials, five permission codes,
and seeded defect/wastage reason lists.

Both reason lists are seeded as *data* for the same reason production stages are:
a boutique adds "zip misaligned" from the admin UI, and the rework report groups
on a stable id rather than free text everyone spells differently.

No new movementtype value: wastage deliberately writes no ledger row. The stock
left inventory when the material was issued; deducting again would double-count.
That is why this phase needs no split enum migration.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "5c2cf0b20b23"
down_revision: Union[str, None] = "08d4b540a2c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

QUANTITY = sa.Numeric(14, 4)

QC_RESULT = postgresql.ENUM("PASS", "FAIL", "PARTIAL", name="qcresult", create_type=False)
REWORK_STATUS = postgresql.ENUM(
    "OPEN", "IN_PROGRESS", "RESOLVED", "CANCELLED", name="reworkstatus", create_type=False
)

DEFAULT_DEFECTS = [
    ("STITCHING", "Incorrect stitching"),
    ("LOOSE_THREAD", "Loose thread"),
    ("MEASUREMENT", "Incorrect measurement"),
    ("DAMAGED_MATERIAL", "Damaged material"),
    ("EMBROIDERY", "Embroidery issue"),
    ("FINISHING", "Finishing issue"),
    ("STAINING", "Staining or marking"),
    ("OTHER", "Other"),
]

DEFAULT_WASTAGE_REASONS = [
    ("CUTTING_LOSS", "Cutting loss"),
    ("DAMAGED", "Damaged in handling"),
    ("MISCUT", "Miscut"),
    ("SAMPLE", "Used for sampling"),
    ("SHRINKAGE", "Shrinkage"),
    ("OTHER", "Other"),
]

NEW_PERMISSIONS = [
    ("qc.view", "Manufacturing", "View quality checks"),
    ("qc.create", "Manufacturing", "Record a quality check"),
    ("qc.rework", "Manufacturing", "Raise and resolve rework"),
    ("wastage.view", "Manufacturing", "View production wastage"),
    ("wastage.record", "Manufacturing", "Record production wastage"),
]

ROLE_GRANTS = {
    "TENANT_OWNER": [c for c, _, _ in NEW_PERMISSIONS],
    "ADMIN": [c for c, _, _ in NEW_PERMISSIONS],
    "MANAGER": [c for c, _, _ in NEW_PERMISSIONS],
    "INVENTORY": ["qc.view", "wastage.view"],
    "VIEWER": ["qc.view", "wastage.view"],
    # A tailor can see QC outcomes on their own work and report material they
    # spoiled - not sign off quality, which is somebody else's job by design.
    "TAILOR": ["qc.view", "wastage.record"],
}


def _ts():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("DO $$ BEGIN CREATE TYPE qcresult AS ENUM ('PASS','FAIL','PARTIAL'); "
               "EXCEPTION WHEN duplicate_object THEN NULL; END $$;")
    op.execute("DO $$ BEGIN CREATE TYPE reworkstatus AS ENUM "
               "('OPEN','IN_PROGRESS','RESOLVED','CANCELLED'); "
               "EXCEPTION WHEN duplicate_object THEN NULL; END $$;")

    op.add_column(
        "production_order_materials",
        sa.Column("wasted_quantity", QUANTITY, nullable=False, server_default="0"),
    )

    op.create_table(
        "defect_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("code", sa.String(40), nullable=False, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_ts(),
        sa.UniqueConstraint("tenant_id", "code", name="uq_defect_category_code"),
    )

    op.create_table(
        "wastage_reasons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("code", sa.String(40), nullable=False, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_ts(),
        sa.UniqueConstraint("tenant_id", "code", name="uq_wastage_reason_code"),
    )

    op.create_table(
        "quality_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("production_order_id", sa.Integer(), sa.ForeignKey("production_orders.id"),
                  nullable=False, index=True),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id"), nullable=True, index=True),
        sa.Column("result", QC_RESULT, nullable=False, index=True),
        sa.Column("checked_quantity", QUANTITY, nullable=False, server_default="0"),
        sa.Column("passed_quantity", QUANTITY, nullable=False, server_default="0"),
        sa.Column("failed_quantity", QUANTITY, nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("photo_path", sa.String(300), nullable=True),
        sa.Column("inspector_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        *_ts(),
        sa.CheckConstraint("failed_quantity <= checked_quantity", name="ck_qc_failed_within_checked"),
        sa.CheckConstraint("passed_quantity + failed_quantity = checked_quantity",
                           name="ck_qc_split_adds_up"),
    )
    op.create_index("ix_qc_order", "quality_checks", ["production_order_id"])
    op.create_index("ix_qc_result", "quality_checks", ["tenant_id", "result"])

    op.create_table(
        "quality_defects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("quality_check_id", sa.Integer(), sa.ForeignKey("quality_checks.id"),
                  nullable=False, index=True),
        sa.Column("defect_category_id", sa.Integer(), sa.ForeignKey("defect_categories.id"), nullable=False),
        sa.Column("quantity", QUANTITY, nullable=False, server_default="0"),
        sa.Column("notes", sa.String(500), nullable=True),
        *_ts(),
    )

    op.create_table(
        "rework_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("rework_number", sa.String(30), nullable=False, index=True),
        sa.Column("production_order_id", sa.Integer(), sa.ForeignKey("production_orders.id"),
                  nullable=False, index=True),
        sa.Column("quality_check_id", sa.Integer(), sa.ForeignKey("quality_checks.id"), nullable=True),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id"), nullable=True),
        sa.Column("assigned_tailor_id", sa.Integer(), sa.ForeignKey("tailors.id"), nullable=True),
        sa.Column("quantity", QUANTITY, nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("status", REWORK_STATUS, nullable=False, server_default="OPEN", index=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        *_ts(),
        sa.UniqueConstraint("tenant_id", "rework_number", name="uq_rework_tenant_number"),
        sa.CheckConstraint("quantity > 0", name="ck_rework_qty_positive"),
    )
    op.create_index("ix_rework_order", "rework_orders", ["production_order_id"])

    op.create_table(
        "production_wastage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("production_order_id", sa.Integer(), sa.ForeignKey("production_orders.id"),
                  nullable=False, index=True),
        sa.Column("production_order_material_id", sa.Integer(),
                  sa.ForeignKey("production_order_materials.id"), nullable=False, index=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False, index=True),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id"), nullable=True),
        sa.Column("tailor_id", sa.Integer(), sa.ForeignKey("tailors.id"), nullable=True, index=True),
        sa.Column("quantity", QUANTITY, nullable=False),
        sa.Column("uom_id", sa.Integer(), sa.ForeignKey("units_of_measure.id"), nullable=False),
        sa.Column("reason_id", sa.Integer(), sa.ForeignKey("wastage_reasons.id"), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("recorded_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        *_ts(),
        sa.CheckConstraint("quantity > 0", name="ck_wastage_qty_positive"),
    )
    op.create_index("ix_wastage_order", "production_wastage", ["production_order_id"])
    op.create_index("ix_wastage_item", "production_wastage", ["item_id"])

    # -------------------------------------------------- seed reason lists
    tenant_ids = [r[0] for r in bind.execute(sa.text("SELECT id FROM tenants")).fetchall()]
    defects_t = sa.table("defect_categories", sa.column("tenant_id", sa.Integer),
                         sa.column("code", sa.String), sa.column("name", sa.String))
    reasons_t = sa.table("wastage_reasons", sa.column("tenant_id", sa.Integer),
                         sa.column("code", sa.String), sa.column("name", sa.String))
    if tenant_ids:
        bind.execute(defects_t.insert(), [
            {"tenant_id": t, "code": c, "name": n}
            for t in tenant_ids for c, n in DEFAULT_DEFECTS
        ])
        bind.execute(reasons_t.insert(), [
            {"tenant_id": t, "code": c, "name": n}
            for t in tenant_ids for c, n in DEFAULT_WASTAGE_REASONS
        ])

    # ------------------------------------------------------------ permissions
    permissions_t = sa.table("permissions", sa.column("id", sa.Integer), sa.column("code", sa.String),
                             sa.column("category", sa.String), sa.column("description", sa.String))
    role_permissions_t = sa.table("role_permissions", sa.column("role", sa.String),
                                  sa.column("permission_id", sa.Integer))
    code_to_id = {}
    for code, category, description in NEW_PERMISSIONS:
        existing = bind.execute(sa.text("SELECT id FROM permissions WHERE code = :c"),
                                {"c": code}).scalar()
        code_to_id[code] = existing or bind.execute(
            permissions_t.insert().values(code=code, category=category, description=description)
            .returning(permissions_t.c.id)).scalar_one()
    grants = [
        {"role": r, "permission_id": code_to_id[c]}
        for r, codes in ROLE_GRANTS.items() for c in codes
        if not bind.execute(
            sa.text("SELECT 1 FROM role_permissions WHERE role = :r AND permission_id = :p"),
            {"r": r, "p": code_to_id[c]}).scalar()
    ]
    if grants:
        bind.execute(role_permissions_t.insert(), grants)


def downgrade() -> None:
    bind = op.get_bind()
    codes = [c for c, _, _ in NEW_PERMISSIONS]
    bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id IN "
                         "(SELECT id FROM permissions WHERE code = ANY(:c))"), {"c": codes})
    bind.execute(sa.text("DELETE FROM permissions WHERE code = ANY(:c)"), {"c": codes})

    op.drop_index("ix_wastage_item", table_name="production_wastage")
    op.drop_index("ix_wastage_order", table_name="production_wastage")
    op.drop_table("production_wastage")
    op.drop_index("ix_rework_order", table_name="rework_orders")
    op.drop_table("rework_orders")
    op.drop_table("quality_defects")
    op.drop_index("ix_qc_result", table_name="quality_checks")
    op.drop_index("ix_qc_order", table_name="quality_checks")
    op.drop_table("quality_checks")
    op.drop_table("wastage_reasons")
    op.drop_table("defect_categories")
    op.drop_column("production_order_materials", "wasted_quantity")
    op.execute("DROP TYPE IF EXISTS reworkstatus")
    op.execute("DROP TYPE IF EXISTS qcresult")
