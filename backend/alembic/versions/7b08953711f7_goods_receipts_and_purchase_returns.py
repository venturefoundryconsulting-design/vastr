"""goods receipts and purchase returns

Revision ID: 7b08953711f7
Revises: 72407fc6ffda
Create Date: 2026-08-20

Phase 5 - goods receipts as a real document, and purchase returns.

Four tables plus four permission codes. Additive; nothing existing changes.
`purchase_order_items.quantity_received` is untouched and keeps working exactly
as before - existing receiving code paths are not migrated by this revision, only
extended with a real document alongside them.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7b08953711f7"
down_revision: Union[str, None] = "72407fc6ffda"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

QUANTITY = sa.Numeric(14, 4)
COST = sa.Numeric(12, 4)

RECEIPT_STATUS = postgresql.ENUM(
    "DRAFT", "POSTED", "CANCELLED", name="receiptstatus", create_type=False
)

NEW_PERMISSIONS = [
    ("goods_receipts.view", "Purchasing", "View goods receipts"),
    ("goods_receipts.create", "Purchasing", "Record a goods receipt"),
    ("goods_receipts.post", "Purchasing", "Post a goods receipt into stock"),
    ("purchase_returns.manage", "Purchasing", "Send goods back to a vendor"),
]
ALL_CODES = [c for c, _, _ in NEW_PERMISSIONS]
ROLE_GRANTS = {
    "TENANT_OWNER": ALL_CODES, "ADMIN": ALL_CODES, "MANAGER": ALL_CODES,
    "INVENTORY": ALL_CODES,
    "VIEWER": ["goods_receipts.view"],
}


def _ts():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("DO $$ BEGIN CREATE TYPE receiptstatus AS ENUM ('DRAFT','POSTED','CANCELLED'); "
               "EXCEPTION WHEN duplicate_object THEN NULL; END $$;")

    op.create_table(
        "goods_receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("receipt_number", sa.String(30), nullable=False, index=True),
        sa.Column("purchase_order_id", sa.Integer(), sa.ForeignKey("purchase_orders.id"), nullable=True),
        sa.Column("vendor_id", sa.Integer(), sa.ForeignKey("vendors.id"), nullable=True),
        sa.Column("outlet_id", sa.Integer(), sa.ForeignKey("outlets.id"), nullable=False, index=True),
        sa.Column("receipt_date", sa.Date(), nullable=True),
        sa.Column("vendor_invoice_ref", sa.String(60), nullable=True),
        sa.Column("status", RECEIPT_STATUS, nullable=False, server_default="DRAFT", index=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("received_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        *_ts(),
        sa.UniqueConstraint("tenant_id", "receipt_number", name="uq_goods_receipt_number"),
    )
    op.create_index("ix_goods_receipts_po", "goods_receipts", ["purchase_order_id"])
    op.create_index("ix_goods_receipts_tenant_status", "goods_receipts", ["tenant_id", "status"])

    op.create_table(
        "goods_receipt_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("goods_receipt_id", sa.Integer(), sa.ForeignKey("goods_receipts.id"),
                  nullable=False, index=True),
        sa.Column("purchase_order_item_id", sa.Integer(),
                  sa.ForeignKey("purchase_order_items.id"), nullable=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False, index=True),
        sa.Column("quantity", QUANTITY, nullable=False),
        sa.Column("uom_id", sa.Integer(), sa.ForeignKey("units_of_measure.id"), nullable=True),
        sa.Column("quantity_in_stock_uom", QUANTITY, nullable=False),
        sa.Column("unit_cost", COST, nullable=False, server_default="0"),
        sa.Column("stock_movement_id", sa.Integer(), sa.ForeignKey("stock_movements.id"), nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        *_ts(),
        sa.CheckConstraint("quantity > 0", name="ck_goods_receipt_item_qty_positive"),
    )
    op.create_index("ix_goods_receipt_items_receipt", "goods_receipt_items", ["goods_receipt_id"])

    op.create_table(
        "purchase_returns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("return_number", sa.String(30), nullable=False, index=True),
        sa.Column("goods_receipt_id", sa.Integer(), sa.ForeignKey("goods_receipts.id"),
                  nullable=True, index=True),
        sa.Column("vendor_id", sa.Integer(), sa.ForeignKey("vendors.id"), nullable=True),
        sa.Column("outlet_id", sa.Integer(), sa.ForeignKey("outlets.id"), nullable=False),
        sa.Column("return_date", sa.Date(), nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("returned_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        *_ts(),
        sa.UniqueConstraint("tenant_id", "return_number", name="uq_purchase_return_number"),
    )
    op.create_index("ix_purchase_returns_receipt", "purchase_returns", ["goods_receipt_id"])

    op.create_table(
        "purchase_return_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("purchase_return_id", sa.Integer(), sa.ForeignKey("purchase_returns.id"),
                  nullable=False, index=True),
        sa.Column("goods_receipt_item_id", sa.Integer(),
                  sa.ForeignKey("goods_receipt_items.id"), nullable=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False, index=True),
        sa.Column("quantity", QUANTITY, nullable=False),
        sa.Column("uom_id", sa.Integer(), sa.ForeignKey("units_of_measure.id"), nullable=True),
        sa.Column("unit_cost", COST, nullable=False, server_default="0"),
        sa.Column("stock_movement_id", sa.Integer(), sa.ForeignKey("stock_movements.id"), nullable=True),
        *_ts(),
        sa.CheckConstraint("quantity > 0", name="ck_purchase_return_item_qty_positive"),
    )
    op.create_index("ix_purchase_return_items_return", "purchase_return_items", ["purchase_return_id"])

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
    posted = bind.execute(sa.text(
        "SELECT count(*) FROM goods_receipts WHERE status = 'POSTED'"
    )).scalar_one()
    if posted:
        raise RuntimeError(
            f"Cannot downgrade: {posted} goods receipt(s) have already posted real stock "
            "movements. Dropping these tables would orphan that history."
        )
    codes = [c for c, _, _ in NEW_PERMISSIONS]
    bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id IN "
                         "(SELECT id FROM permissions WHERE code = ANY(:c))"), {"c": codes})
    bind.execute(sa.text("DELETE FROM permissions WHERE code = ANY(:c)"), {"c": codes})

    op.drop_index("ix_purchase_return_items_return", table_name="purchase_return_items")
    op.drop_table("purchase_return_items")
    op.drop_index("ix_purchase_returns_receipt", table_name="purchase_returns")
    op.drop_table("purchase_returns")
    op.drop_index("ix_goods_receipt_items_receipt", table_name="goods_receipt_items")
    op.drop_table("goods_receipt_items")
    op.drop_index("ix_goods_receipts_tenant_status", table_name="goods_receipts")
    op.drop_index("ix_goods_receipts_po", table_name="goods_receipts")
    op.drop_table("goods_receipts")
    op.execute("DROP TYPE IF EXISTS receiptstatus")
