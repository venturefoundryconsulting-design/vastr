"""material reservation issue consumption return

Revision ID: debaf64667ce
Revises: 671325591073
Create Date: 2026-08-20

Phase 3D, step 2 of 2 - tables, aggregate cache columns and permissions.

Depends on 671325591073 having committed the two new movementtype labels.

Additive and safe for existing tenants: four new tables, four new columns on
production_order_materials (all defaulting to 0), and seven new permission codes.
No existing column changes type and no data is rewritten.

materials.issue_unreserved is created but granted to NO role, including admin.
It bypasses the reservation model, so it is opt-in per deployment rather than
something a powerful role inherits silently.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "debaf64667ce"
down_revision: Union[str, None] = "671325591073"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

QUANTITY = sa.Numeric(14, 4)

RESERVATION_STATUS = postgresql.ENUM(
    "ACTIVE", "PARTIALLY_ISSUED", "CONSUMED", "RELEASED", "CANCELLED",
    name="reservationstatus", create_type=False,
)

NEW_PERMISSIONS = [
    ("materials.view", "Manufacturing", "View material reservations, issues and consumption"),
    ("materials.reserve", "Manufacturing", "Reserve material for a production order"),
    ("materials.release", "Manufacturing", "Release an unused material reservation"),
    ("materials.issue", "Manufacturing", "Issue reserved material to production"),
    ("materials.issue_unreserved", "Manufacturing", "Issue material beyond what is reserved"),
    ("materials.consume", "Manufacturing", "Record actual material consumption"),
    ("materials.return", "Manufacturing", "Return unused material from production"),
]

# Deliberately absent from every list below.
NEVER_GRANTED = {"materials.issue_unreserved"}

ROLE_GRANTS = {
    "TENANT_OWNER": [c for c, _, _ in NEW_PERMISSIONS if c not in NEVER_GRANTED],
    "ADMIN": [c for c, _, _ in NEW_PERMISSIONS if c not in NEVER_GRANTED],
    "MANAGER": [c for c, _, _ in NEW_PERMISSIONS if c not in NEVER_GRANTED],
    # Store staff hand material over the counter and take it back; they do not
    # decide what gets committed to which order.
    "INVENTORY": ["materials.view", "materials.issue", "materials.return"],
    "VIEWER": ["materials.view"],
}


def _ts():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def upgrade() -> None:
    bind = op.get_bind()
    op.execute(
        "DO $$ BEGIN CREATE TYPE reservationstatus AS ENUM "
        "('ACTIVE','PARTIALLY_ISSUED','CONSUMED','RELEASED','CANCELLED'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )

    # ---- aggregate cache over the transaction tables ------------------------
    for col in ("reserved_quantity", "issued_quantity", "consumed_quantity", "returned_quantity"):
        op.add_column(
            "production_order_materials",
            sa.Column(col, QUANTITY, nullable=False, server_default="0"),
        )

    op.create_table(
        "stock_reservations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("production_order_id", sa.Integer(), sa.ForeignKey("production_orders.id"),
                  nullable=False, index=True),
        sa.Column("production_order_material_id", sa.Integer(),
                  sa.ForeignKey("production_order_materials.id"), nullable=False, index=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False, index=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("outlets.id"), nullable=False, index=True),
        sa.Column("quantity", QUANTITY, nullable=False),
        sa.Column("issued_quantity", QUANTITY, nullable=False, server_default="0"),
        sa.Column("uom_id", sa.Integer(), sa.ForeignKey("units_of_measure.id"), nullable=False),
        sa.Column("status", RESERVATION_STATUS, nullable=False, server_default="ACTIVE", index=True),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("released_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("release_reason", sa.String(500), nullable=True),
        *_ts(),
        sa.CheckConstraint("quantity >= 0", name="ck_reservation_qty_non_negative"),
        sa.CheckConstraint("issued_quantity >= 0", name="ck_reservation_issued_non_negative"),
        # A reservation can never have issued more than it promised.
        sa.CheckConstraint("issued_quantity <= quantity", name="ck_reservation_issued_within_qty"),
    )
    op.create_index("ix_reservation_item_location_status", "stock_reservations",
                    ["item_id", "location_id", "status"])
    op.create_index("ix_reservation_order", "stock_reservations", ["production_order_id"])

    op.create_table(
        "production_material_issues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("production_order_id", sa.Integer(), sa.ForeignKey("production_orders.id"),
                  nullable=False, index=True),
        sa.Column("production_order_material_id", sa.Integer(),
                  sa.ForeignKey("production_order_materials.id"), nullable=False, index=True),
        sa.Column("reservation_id", sa.Integer(), sa.ForeignKey("stock_reservations.id"), nullable=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False, index=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("outlets.id"), nullable=False),
        sa.Column("quantity", QUANTITY, nullable=False),
        sa.Column("uom_id", sa.Integer(), sa.ForeignKey("units_of_measure.id"), nullable=False),
        sa.Column("stock_movement_id", sa.Integer(), sa.ForeignKey("stock_movements.id"), nullable=True),
        sa.Column("unreserved_reason", sa.String(500), nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("issued_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        *_ts(),
        sa.CheckConstraint("quantity > 0", name="ck_issue_qty_positive"),
    )
    op.create_index("ix_pmi_order_material", "production_material_issues",
                    ["production_order_id", "production_order_material_id"])

    op.create_table(
        "production_material_consumptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("production_order_id", sa.Integer(), sa.ForeignKey("production_orders.id"),
                  nullable=False, index=True),
        sa.Column("production_order_material_id", sa.Integer(),
                  sa.ForeignKey("production_order_materials.id"), nullable=False, index=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False, index=True),
        sa.Column("quantity", QUANTITY, nullable=False),
        sa.Column("uom_id", sa.Integer(), sa.ForeignKey("units_of_measure.id"), nullable=False),
        sa.Column("over_consumption_reason", sa.String(500), nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("recorded_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        *_ts(),
        sa.CheckConstraint("quantity > 0", name="ck_consumption_qty_positive"),
    )
    op.create_index("ix_pmc_order_material", "production_material_consumptions",
                    ["production_order_id", "production_order_material_id"])

    op.create_table(
        "production_material_returns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("production_order_id", sa.Integer(), sa.ForeignKey("production_orders.id"),
                  nullable=False, index=True),
        sa.Column("production_order_material_id", sa.Integer(),
                  sa.ForeignKey("production_order_materials.id"), nullable=False, index=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False, index=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("outlets.id"), nullable=False),
        sa.Column("quantity", QUANTITY, nullable=False),
        sa.Column("uom_id", sa.Integer(), sa.ForeignKey("units_of_measure.id"), nullable=False),
        sa.Column("stock_movement_id", sa.Integer(), sa.ForeignKey("stock_movements.id"), nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("restock", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("returned_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        *_ts(),
        sa.CheckConstraint("quantity > 0", name="ck_return_qty_positive"),
    )
    op.create_index("ix_pmr_order_material", "production_material_returns",
                    ["production_order_id", "production_order_material_id"])

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

    # Physical movements written by issues/returns are deliberately NOT deleted:
    # they are real inventory history, and the ledger must still reconcile after
    # a downgrade. Refuse instead of silently corrupting stock.
    issued = bind.execute(sa.text("SELECT count(*) FROM production_material_issues")).scalar_one()
    returned = bind.execute(sa.text("SELECT count(*) FROM production_material_returns")).scalar_one()
    if issued or returned:
        raise RuntimeError(
            f"Cannot downgrade: {issued} issue(s) and {returned} return(s) have already moved "
            "physical stock. Dropping these tables would orphan real inventory movements and "
            "leave the ledger unexplainable. Reverse the material flow first if this is intended."
        )

    op.drop_index("ix_pmr_order_material", table_name="production_material_returns")
    op.drop_table("production_material_returns")
    op.drop_index("ix_pmc_order_material", table_name="production_material_consumptions")
    op.drop_table("production_material_consumptions")
    op.drop_index("ix_pmi_order_material", table_name="production_material_issues")
    op.drop_table("production_material_issues")
    op.drop_index("ix_reservation_order", table_name="stock_reservations")
    op.drop_index("ix_reservation_item_location_status", table_name="stock_reservations")
    op.drop_table("stock_reservations")
    for col in ("returned_quantity", "consumed_quantity", "issued_quantity", "reserved_quantity"):
        op.drop_column("production_order_materials", col)
    op.execute("DROP TYPE IF EXISTS reservationstatus")
