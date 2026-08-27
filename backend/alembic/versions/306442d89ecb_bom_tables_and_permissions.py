"""bom tables and permissions

Revision ID: 306442d89ecb
Revises: 078d64dd5db5
Create Date: 2026-08-19

Phase 3B - Bill of Materials.

Four tables plus the six bom.* permission codes. No production tables: those are
3C, and this schema is shaped so they can reference bom_versions without needing
another migration to the BOM side.

The one-ACTIVE-version-per-BOM rule is a partial unique index rather than an
application check, so two concurrent activations cannot both win.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "306442d89ecb"
down_revision: Union[str, None] = "078d64dd5db5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

QUANTITY = sa.Numeric(14, 4)
SCRAP = sa.Numeric(6, 3)

# create_type=False: the type is created once explicitly in upgrade(). Without
# this, create_table() tries to emit CREATE TYPE a second time and fails with
# DuplicateObject.
BOM_STATUS = postgresql.ENUM(
    "DRAFT", "ACTIVE", "ARCHIVED", name="bomstatus", create_type=False
)

NEW_PERMISSIONS = [
    ("bom.view", "Manufacturing", "View bills of materials"),
    ("bom.create", "Manufacturing", "Create a bill of materials"),
    ("bom.edit", "Manufacturing", "Edit a draft bill of materials"),
    ("bom.activate", "Manufacturing", "Activate a BOM version for production"),
    ("bom.archive", "Manufacturing", "Archive a BOM version"),
    ("bom.cost.view", "Manufacturing", "View estimated material cost of a BOM"),
]

# MANAGER already receives everything except the three admin codes, so it picks
# these up automatically. INVENTORY gets read-only visibility. The dedicated
# production roles land in Phase 3F.
ROLE_GRANTS = {
    "MANAGER": [c for c, _, _ in NEW_PERMISSIONS],
    "TENANT_OWNER": [c for c, _, _ in NEW_PERMISSIONS],
    "ADMIN": [c for c, _, _ in NEW_PERMISSIONS],
    "INVENTORY": ["bom.view", "bom.cost.view"],
    "VIEWER": ["bom.view"],
}


def _ts():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def upgrade() -> None:
    bind = op.get_bind()
    op.execute(
        "DO $$ BEGIN CREATE TYPE bomstatus AS ENUM ('DRAFT', 'ACTIVE', 'ARCHIVED'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )

    op.create_table(
        "boms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(2000), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_ts(),
        sa.UniqueConstraint("tenant_id", "item_id", name="uq_bom_tenant_item"),
    )

    op.create_table(
        "bom_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("bom_id", sa.Integer(), sa.ForeignKey("boms.id"), nullable=False, index=True),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("status", BOM_STATUS, nullable=False, server_default="DRAFT", index=True),
        sa.Column("output_quantity", QUANTITY, nullable=False, server_default="1"),
        sa.Column("output_uom_id", sa.Integer(), sa.ForeignKey("units_of_measure.id"), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        *_ts(),
        sa.UniqueConstraint("tenant_id", "bom_id", "version_no", name="uq_bom_version_no"),
        sa.CheckConstraint("output_quantity > 0", name="ck_bom_version_output_positive"),
    )
    # Only one ACTIVE version per BOM. In the database, not in Python: two
    # concurrent activate calls must not both succeed.
    op.create_index(
        "uq_bom_one_active_version", "bom_versions", ["bom_id"],
        unique=True, postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    op.create_table(
        "bom_components",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("bom_version_id", sa.Integer(), sa.ForeignKey("bom_versions.id"), nullable=False, index=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("quantity", QUANTITY, nullable=False),
        sa.Column("uom_id", sa.Integer(), sa.ForeignKey("units_of_measure.id"), nullable=False),
        sa.Column("scrap_pct", SCRAP, nullable=False, server_default="0"),
        sa.Column("is_optional", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.String(500), nullable=True),
        *_ts(),
        sa.CheckConstraint("quantity > 0", name="ck_bom_component_quantity_positive"),
        sa.CheckConstraint("scrap_pct >= 0 AND scrap_pct < 100", name="ck_bom_component_scrap_range"),
    )
    op.create_index("ix_bom_components_version_seq", "bom_components", ["bom_version_id", "sequence"])
    op.create_index("ix_bom_components_item", "bom_components", ["item_id"])

    op.create_table(
        "bom_component_substitutes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("bom_component_id", sa.Integer(), sa.ForeignKey("bom_components.id"), nullable=False, index=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.String(500), nullable=True),
        *_ts(),
        sa.UniqueConstraint(
            "tenant_id", "bom_component_id", "item_id", name="uq_bom_substitute_component_item"
        ),
    )

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
        existing = bind.execute(
            sa.text("SELECT id FROM permissions WHERE code = :c"), {"c": code}
        ).scalar()
        if existing:
            code_to_id[code] = existing
            continue
        code_to_id[code] = bind.execute(
            permissions_t.insert()
            .values(code=code, category=category, description=description)
            .returning(permissions_t.c.id)
        ).scalar_one()

    rows = [
        {"role": role, "permission_id": code_to_id[code]}
        for role, codes in ROLE_GRANTS.items()
        for code in codes
        # Idempotent: skip a grant that somehow already exists.
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
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE code = ANY(:codes))"
        ),
        {"codes": codes},
    )
    bind.execute(sa.text("DELETE FROM permissions WHERE code = ANY(:codes)"), {"codes": codes})

    op.drop_table("bom_component_substitutes")
    op.drop_index("ix_bom_components_item", table_name="bom_components")
    op.drop_index("ix_bom_components_version_seq", table_name="bom_components")
    op.drop_table("bom_components")
    op.drop_index("uq_bom_one_active_version", table_name="bom_versions")
    op.drop_table("bom_versions")
    op.drop_table("boms")
    op.execute("DROP TYPE IF EXISTS bomstatus")
