"""ai import batches and rows

Revision ID: c1a4f9e2b7d3
Revises: 5088dc2fa65d
Create Date: 2026-08-27

Phase 9 - AI-assisted invoice import. Two staging tables plus two permission
codes. Nothing here writes to items, vendors or stock - see
app.models.ai_import for why the staging boundary matters.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c1a4f9e2b7d3"
down_revision: Union[str, None] = "5088dc2fa65d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

QUANTITY = sa.Numeric(14, 4)
COST = sa.Numeric(12, 4)
CONFIDENCE = sa.Numeric(3, 2)

AI_IMPORT_STATUS = postgresql.ENUM(
    "PENDING", "APPROVED", "REJECTED", name="aiimportstatus", create_type=False
)

NEW_PERMISSIONS = [
    ("ai_import.create", "Purchasing", "Upload a vendor invoice for AI extraction"),
    ("ai_import.approve", "Purchasing", "Approve an AI-extracted invoice into a draft goods receipt"),
]
ALL_CODES = [c for c, _, _ in NEW_PERMISSIONS]
ROLE_GRANTS = {
    "TENANT_OWNER": ALL_CODES, "ADMIN": ALL_CODES, "MANAGER": ALL_CODES,
    "INVENTORY": ALL_CODES,
}


def _ts():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("DO $$ BEGIN CREATE TYPE aiimportstatus AS ENUM ('PENDING','APPROVED','REJECTED'); "
               "EXCEPTION WHEN duplicate_object THEN NULL; END $$;")

    op.create_table(
        "ai_import_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("outlet_id", sa.Integer(), sa.ForeignKey("outlets.id"), nullable=False, index=True),
        sa.Column("vendor_id", sa.Integer(), sa.ForeignKey("vendors.id"), nullable=True, index=True),
        sa.Column("source_filename", sa.String(255), nullable=False),
        sa.Column("source_path", sa.String(500), nullable=False),
        sa.Column("status", AI_IMPORT_STATUS, nullable=False, server_default="PENDING", index=True),
        sa.Column("raw_extraction", sa.Text(), nullable=True),
        sa.Column("vendor_name_guess", sa.String(150), nullable=True),
        sa.Column("invoice_ref_guess", sa.String(80), nullable=True),
        sa.Column("goods_receipt_id", sa.Integer(), sa.ForeignKey("goods_receipts.id"), nullable=True),
        sa.Column("uploaded_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        *_ts(),
    )
    op.create_index("ix_ai_import_batches_tenant_status", "ai_import_batches", ["tenant_id", "status"])

    op.create_table(
        "ai_import_rows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("ai_import_batches.id"),
                  nullable=False, index=True),
        sa.Column("line_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_description", sa.String(300), nullable=False),
        sa.Column("raw_unit_text", sa.String(40), nullable=True),
        sa.Column("matched_item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=True),
        sa.Column("is_new_item", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("proposed_sku", sa.String(64), nullable=True),
        sa.Column("quantity", QUANTITY, nullable=False, server_default="0"),
        sa.Column("uom_id", sa.Integer(), sa.ForeignKey("units_of_measure.id"), nullable=True),
        sa.Column("unit_cost", COST, nullable=False, server_default="0"),
        sa.Column("description_confidence", CONFIDENCE, nullable=True),
        sa.Column("quantity_confidence", CONFIDENCE, nullable=True),
        sa.Column("cost_confidence", CONFIDENCE, nullable=True),
        sa.Column("match_confidence", CONFIDENCE, nullable=True),
        sa.Column("excluded", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_ts(),
    )
    op.create_index("ix_ai_import_rows_batch", "ai_import_rows", ["batch_id"])

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
    op.drop_index("ix_ai_import_rows_batch", table_name="ai_import_rows")
    op.drop_table("ai_import_rows")
    op.drop_index("ix_ai_import_batches_tenant_status", table_name="ai_import_batches")
    op.drop_table("ai_import_batches")
    op.execute("DROP TYPE IF EXISTS aiimportstatus")
