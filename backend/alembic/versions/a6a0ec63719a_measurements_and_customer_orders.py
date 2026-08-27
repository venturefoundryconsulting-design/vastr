"""measurements and customer orders

Revision ID: a6a0ec63719a
Revises: a7b6b501c16a
Create Date: 2026-08-20

Phase 4 - made-to-order and POS integration.

Five tables, seven permission codes, and a seeded list of the measurements a
boutique actually takes.

The measurement list is seeded as *data* for the same reason production stages
and defect categories are: every boutique measures slightly differently, and a
schema change per garment style is not a workable answer. Nothing in the
application branches on a measurement code.

No new movementtype: delivery raises an ordinary Sale through the existing POS
checkout, which already writes a SALE ledger row. There is no parallel sales
path, so this phase needs no split enum migration.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a6a0ec63719a"
down_revision: Union[str, None] = "a7b6b501c16a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

QUANTITY = sa.Numeric(14, 4)
MONEY = sa.Numeric(12, 2)

MEASUREMENT_UNIT = postgresql.ENUM("INCH", "CM", name="measurementunit", create_type=False)
FULFILMENT = postgresql.ENUM(
    "READY_STOCK", "MADE_TO_ORDER", name="fulfilment", create_type=False
)
CO_STATUS = postgresql.ENUM(
    "DRAFT", "CONFIRMED", "IN_PRODUCTION", "READY", "DELIVERED", "CANCELLED",
    name="customerorderstatus", create_type=False,
)

# (code, name, sequence, group)
DEFAULT_MEASUREMENTS = [
    ("BUST", "Bust", 10, "Upper body"),
    ("WAIST", "Waist", 20, "Upper body"),
    ("HIP", "Hip", 30, "Lower body"),
    ("SHOULDER", "Shoulder", 40, "Upper body"),
    ("SLEEVE_LENGTH", "Sleeve length", 50, "Upper body"),
    ("ARMHOLE", "Armhole", 60, "Upper body"),
    ("NECK", "Neck", 70, "Upper body"),
    ("BLOUSE_LENGTH", "Blouse length", 80, "Blouse"),
    ("LEHENGA_LENGTH", "Lehenga length", 90, "Lehenga"),
    ("KURTI_LENGTH", "Kurti length", 100, "Kurti"),
]

NEW_PERMISSIONS = [
    ("measurements.view", "Customers", "View customer measurements"),
    ("measurements.manage", "Customers", "Record and edit customer measurements"),
    ("customer_orders.view", "Sales", "View customer orders"),
    ("customer_orders.create", "Sales", "Create customer orders"),
    ("customer_orders.confirm", "Sales", "Confirm a customer order and start production"),
    ("customer_orders.deliver", "Sales", "Deliver a customer order and raise the sale"),
    ("customer_orders.cancel", "Sales", "Cancel a customer order"),
]

ALL_CODES = [c for c, _, _ in NEW_PERMISSIONS]
ROLE_GRANTS = {
    "TENANT_OWNER": ALL_CODES,
    "ADMIN": ALL_CODES,
    "MANAGER": ALL_CODES,
    "SALES": ALL_CODES,
    # Counter staff take orders and hand them over. Confirming spawns production
    # and commits material, which is a manager's decision - so not that one.
    "OUTLET_STAFF": [
        "measurements.view", "measurements.manage",
        "customer_orders.view", "customer_orders.create", "customer_orders.deliver",
    ],
    "VIEWER": ["measurements.view", "customer_orders.view"],
}


def _ts():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("DO $$ BEGIN CREATE TYPE measurementunit AS ENUM ('INCH','CM'); "
               "EXCEPTION WHEN duplicate_object THEN NULL; END $$;")
    op.execute("DO $$ BEGIN CREATE TYPE fulfilment AS ENUM ('READY_STOCK','MADE_TO_ORDER'); "
               "EXCEPTION WHEN duplicate_object THEN NULL; END $$;")
    op.execute("DO $$ BEGIN CREATE TYPE customerorderstatus AS ENUM "
               "('DRAFT','CONFIRMED','IN_PRODUCTION','READY','DELIVERED','CANCELLED'); "
               "EXCEPTION WHEN duplicate_object THEN NULL; END $$;")

    op.create_table(
        "measurement_fields",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("code", sa.String(40), nullable=False, index=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("unit", MEASUREMENT_UNIT, nullable=False, server_default="INCH"),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("group_name", sa.String(60), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_ts(),
        sa.UniqueConstraint("tenant_id", "code", name="uq_measurement_field_code"),
    )

    op.create_table(
        "measurement_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("taken_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_ts(),
    )
    op.create_index("ix_measurement_profile_customer", "measurement_profiles", ["customer_id"])

    op.create_table(
        "measurement_values",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("measurement_profiles.id"),
                  nullable=False, index=True),
        sa.Column("field_id", sa.Integer(), sa.ForeignKey("measurement_fields.id"), nullable=False),
        sa.Column("value", sa.Numeric(10, 2), nullable=False),
        sa.Column("notes", sa.String(255), nullable=True),
        *_ts(),
        sa.UniqueConstraint("tenant_id", "profile_id", "field_id", name="uq_measurement_value"),
        sa.CheckConstraint("value > 0", name="ck_measurement_value_positive"),
    )

    op.create_table(
        "customer_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("order_number", sa.String(30), nullable=False, index=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False, index=True),
        sa.Column("outlet_id", sa.Integer(), sa.ForeignKey("outlets.id"), nullable=False, index=True),
        sa.Column("status", CO_STATUS, nullable=False, server_default="DRAFT", index=True),
        sa.Column("order_date", sa.Date(), nullable=True),
        sa.Column("promised_date", sa.Date(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("advance_amount", MONEY, nullable=False, server_default="0"),
        sa.Column("sale_id", sa.Integer(), sa.ForeignKey("sales.id"), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("cancel_reason", sa.String(500), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        *_ts(),
        sa.UniqueConstraint("tenant_id", "order_number", name="uq_customer_order_number"),
        sa.CheckConstraint("advance_amount >= 0", name="ck_customer_order_advance_non_negative"),
    )
    op.create_index("ix_customer_orders_tenant_status", "customer_orders", ["tenant_id", "status"])
    op.create_index("ix_customer_orders_customer", "customer_orders", ["customer_id"])

    op.create_table(
        "customer_order_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("customer_order_id", sa.Integer(), sa.ForeignKey("customer_orders.id"),
                  nullable=False, index=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False, index=True),
        sa.Column("quantity", QUANTITY, nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("tax_rate", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("fulfilment", FULFILMENT, nullable=False, server_default="READY_STOCK"),
        sa.Column("measurement_profile_id", sa.Integer(),
                  sa.ForeignKey("measurement_profiles.id"), nullable=True),
        sa.Column("production_order_id", sa.Integer(),
                  sa.ForeignKey("production_orders.id"), nullable=True, index=True),
        sa.Column("notes", sa.String(500), nullable=True),
        *_ts(),
        sa.CheckConstraint("quantity > 0", name="ck_customer_order_item_qty_positive"),
    )
    op.create_index("ix_customer_order_items_order", "customer_order_items", ["customer_order_id"])

    # -------------------------------------------------- seed measurement list
    tenant_ids = [r[0] for r in bind.execute(sa.text("SELECT id FROM tenants")).fetchall()]
    fields_t = sa.table(
        "measurement_fields", sa.column("tenant_id", sa.Integer), sa.column("code", sa.String),
        sa.column("name", sa.String), sa.column("sequence", sa.Integer),
        sa.column("group_name", sa.String),
    )
    if tenant_ids:
        bind.execute(fields_t.insert(), [
            {"tenant_id": t, "code": c, "name": n, "sequence": seq, "group_name": g}
            for t in tenant_ids for c, n, seq, g in DEFAULT_MEASUREMENTS
        ])

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

    existing_roles = {
        r[0] for r in bind.execute(sa.text(
            "SELECT enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
            "WHERE t.typname = 'userrole'"
        )).fetchall()
    }
    grants = [
        {"role": r, "permission_id": code_to_id[c]}
        for r, codes in ROLE_GRANTS.items()
        for c in codes
        if r in existing_roles
        and not bind.execute(
            sa.text("SELECT 1 FROM role_permissions WHERE role = :r AND permission_id = :p"),
            {"r": r, "p": code_to_id[c]},
        ).scalar()
    ]
    if grants:
        bind.execute(role_permissions_t.insert(), grants)


def downgrade() -> None:
    bind = op.get_bind()
    delivered = bind.execute(
        sa.text("SELECT count(*) FROM customer_orders WHERE sale_id IS NOT NULL")
    ).scalar_one()
    if delivered:
        raise RuntimeError(
            f"Cannot downgrade: {delivered} customer order(s) have already been delivered and "
            "are linked to real sales. Dropping these tables would orphan that history."
        )
    codes = [c for c, _, _ in NEW_PERMISSIONS]
    bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id IN "
                         "(SELECT id FROM permissions WHERE code = ANY(:c))"), {"c": codes})
    bind.execute(sa.text("DELETE FROM permissions WHERE code = ANY(:c)"), {"c": codes})

    op.drop_index("ix_customer_order_items_order", table_name="customer_order_items")
    op.drop_table("customer_order_items")
    op.drop_index("ix_customer_orders_customer", table_name="customer_orders")
    op.drop_index("ix_customer_orders_tenant_status", table_name="customer_orders")
    op.drop_table("customer_orders")
    op.drop_table("measurement_values")
    op.drop_index("ix_measurement_profile_customer", table_name="measurement_profiles")
    op.drop_table("measurement_profiles")
    op.drop_table("measurement_fields")
    op.execute("DROP TYPE IF EXISTS customerorderstatus")
    op.execute("DROP TYPE IF EXISTS fulfilment")
    op.execute("DROP TYPE IF EXISTS measurementunit")
