"""uom foundation and unified item master

Revision ID: a335a21c1c40
Revises: ec27aa62e12f
Create Date: 2026-08-19

Phase 2 of the manufacturing programme (see MANUFACTURING_ARCHITECTURE.md).

Establishes master data only - units of measure, their conversions, and one
unified item master covering raw materials, garments, packaging and services.
No BOM, no production, no reservations: those depend on this and come later.

THE CENTRAL DECISION - RENAME, DON'T REPLACE
--------------------------------------------
``product_variants`` is renamed to ``items`` rather than a new ``items`` table
being created alongside it. Eight tables hold foreign keys to
``product_variants.id``:

    stock_levels, stock_movements, sale_items, return_items, exchange_items,
    stock_transfer_items, purchase_order_items, vendor_products

PostgreSQL carries foreign key constraints through ``ALTER TABLE ... RENAME``
automatically, so all eight keep pointing at the same physical table under its
new name. Every id, every historical sale and every stock level stays valid, and
no row is copied.

The alternative - new table plus a ``product_variants`` compatibility *view* -
was rejected on a hard technical constraint: PostgreSQL cannot use a view as the
target of a foreign key, so that route would have required dropping all eight
constraints and permanently losing referential integrity over the sales history.
A read-only view is still created at the end for any external SQL that hardcodes
the old name.

REVERSIBILITY: fully reversible. The downgrade renames back, drops the added
columns and drops the UoM tables. Data added *since* the upgrade (any raw
material, any UoM) is lost on downgrade because it has nowhere to go in the old
schema - that is inherent, not an oversight, and the downgrade says so.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a335a21c1c40"
down_revision: Union[str, None] = "ec27aa62e12f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


QUANTITY = sa.Numeric(14, 4)
FACTOR = sa.Numeric(20, 10)

ITEM_TYPE = sa.Enum(
    "RAW_MATERIAL", "SEMI_FINISHED", "FINISHED_PRODUCT", "PACKAGING", "SERVICE",
    name="itemtype",
)

# (code, name, symbol, category_code, factor_to_base, is_base, precision)
# Seeded so the system is usable on first boot; more can be added from the admin
# UI without a code change, which is the point of units being data not an enum.
SEED_UNITS = [
    ("PC", "Piece", "pc", "COUNT", "1", True, 0),
    ("DOZ", "Dozen", "doz", "COUNT", "12", False, 0),
    ("BOX", "Box", "box", "COUNT", "1", False, 0),
    ("PKT", "Packet", "pkt", "COUNT", "1", False, 0),
    ("ROLL", "Roll", "roll", "COUNT", "1", False, 0),
    ("SET", "Set", "set", "COUNT", "1", False, 0),
    ("M", "Meter", "m", "LENGTH", "1", True, 2),
    ("CM", "Centimeter", "cm", "LENGTH", "0.01", False, 1),
    ("MM", "Millimeter", "mm", "LENGTH", "0.001", False, 0),
    ("KG", "Kilogram", "kg", "WEIGHT", "1000", False, 3),
    ("G", "Gram", "g", "WEIGHT", "1", True, 2),
    ("L", "Liter", "L", "VOLUME", "1000", False, 3),
    ("ML", "Milliliter", "ml", "VOLUME", "1", True, 1),
]

SEED_CATEGORIES = [("COUNT", "Count"), ("LENGTH", "Length"), ("WEIGHT", "Weight"), ("VOLUME", "Volume")]


def upgrade() -> None:
    conn = op.get_bind()

    # ---------------------------------------------------------------- UoM
    op.create_table(
        "uom_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("code", sa.String(30), nullable=False, index=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "code", name="uq_uom_category_tenant_code"),
    )

    op.create_table(
        "units_of_measure",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("code", sa.String(20), nullable=False, index=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("symbol", sa.String(12), nullable=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("uom_categories.id"), nullable=False, index=True),
        sa.Column("factor_to_base", FACTOR, nullable=False, server_default="1"),
        sa.Column("is_base", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("decimal_precision", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "code", name="uq_uom_tenant_code"),
    )

    # ------------------------------------------------- product_variants -> items
    op.rename_table("product_variants", "items")

    ITEM_TYPE.create(conn, checkfirst=True)
    op.add_column("items", sa.Column("item_type", ITEM_TYPE, nullable=False,
                                     server_default="FINISHED_PRODUCT"))
    op.add_column("items", sa.Column("name", sa.String(200), nullable=True))
    op.add_column("items", sa.Column("description", sa.String(2000), nullable=True))
    op.add_column("items", sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=True))
    op.add_column("items", sa.Column("brand", sa.String(120), nullable=True))
    op.add_column("items", sa.Column("hsn_code", sa.String(20), nullable=True))
    op.add_column("items", sa.Column("tax_rate", sa.Numeric(5, 2), nullable=False, server_default="0"))
    op.add_column("items", sa.Column("stock_uom_id", sa.Integer(), sa.ForeignKey("units_of_measure.id"), nullable=True))
    op.add_column("items", sa.Column("purchase_uom_id", sa.Integer(), sa.ForeignKey("units_of_measure.id"), nullable=True))
    op.add_column("items", sa.Column("sales_uom_id", sa.Integer(), sa.ForeignKey("units_of_measure.id"), nullable=True))
    op.add_column("items", sa.Column("min_stock", QUANTITY, nullable=False, server_default="0"))
    op.add_column("items", sa.Column("is_sellable", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("items", sa.Column("is_purchasable", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("items", sa.Column("is_stocked", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("items", sa.Column("notes", sa.String(1000), nullable=True))
    op.create_index("ix_items_tenant_item_type", "items", ["tenant_id", "item_type"])

    # A raw material has no parent garment to be a variant of.
    op.alter_column("items", "product_id", existing_type=sa.Integer(), nullable=True)
    # Reorder levels are quantities too - 2.5 m is a legitimate threshold.
    op.alter_column("items", "reorder_level", existing_type=sa.INTEGER(), type_=QUANTITY,
                    existing_nullable=False, postgresql_using="reorder_level::numeric(14,4)")

    op.create_table(
        "item_uom_conversions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False, index=True),
        sa.Column("from_uom_id", sa.Integer(), sa.ForeignKey("units_of_measure.id"), nullable=False),
        sa.Column("to_uom_id", sa.Integer(), sa.ForeignKey("units_of_measure.id"), nullable=False),
        sa.Column("factor", FACTOR, nullable=False),
        sa.Column("vendor_id", sa.Integer(), sa.ForeignKey("vendors.id"), nullable=True, index=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "item_id", "from_uom_id", "to_uom_id", "vendor_id",
                            name="uq_item_uom_conversion"),
        sa.CheckConstraint("factor > 0", name="ck_item_uom_conversion_factor_positive"),
    )

    # ---------------------------------------------------------- vendor items
    op.add_column("vendor_products", sa.Column("purchase_uom_id", sa.Integer(),
                                               sa.ForeignKey("units_of_measure.id"), nullable=True))
    op.add_column("vendor_products", sa.Column("min_order_qty", QUANTITY, nullable=False, server_default="0"))
    op.add_column("vendor_products", sa.Column("lead_time_days", sa.Integer(), nullable=True))
    op.add_column("vendor_products", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.alter_column("vendor_products", "cost_price", existing_type=sa.Float(), type_=sa.Numeric(12, 4),
                    existing_nullable=False, postgresql_using="cost_price::numeric(12,4)")
    op.create_index("ix_vendor_products_vendor", "vendor_products", ["vendor_id"])
    op.create_index("ix_vendor_products_variant", "vendor_products", ["variant_id"])

    # -------------------------------------------------------------- backfill
    # Seed UoM data per tenant, so a tenant created before Phase 2 is usable.
    tenant_ids = [r[0] for r in conn.execute(sa.text("SELECT id FROM tenants")).fetchall()]
    for tid in tenant_ids:
        cat_ids = {}
        for code, name in SEED_CATEGORIES:
            cat_ids[code] = conn.execute(
                sa.text(
                    "INSERT INTO uom_categories (tenant_id, code, name, is_active, created_at, updated_at) "
                    "VALUES (:t, :c, :n, true, now(), now()) RETURNING id"
                ),
                {"t": tid, "c": code, "n": name},
            ).scalar_one()
        for code, name, symbol, cat, factor, is_base, prec in SEED_UNITS:
            conn.execute(
                sa.text(
                    "INSERT INTO units_of_measure (tenant_id, code, name, symbol, category_id, "
                    "factor_to_base, is_base, decimal_precision, is_active, created_at, updated_at) "
                    "VALUES (:t, :c, :n, :s, :cat, :f, :b, :p, true, now(), now())"
                ),
                {"t": tid, "c": code, "n": name, "s": symbol, "cat": cat_ids[cat],
                 "f": factor, "b": is_base, "p": prec},
            )

    # Make items self-describing: copy the parent product's descriptive fields
    # down onto the item. Existing code reading variant.product.name keeps
    # working; new code can read item.name without a join.
    conn.execute(sa.text("""
        UPDATE items i SET
            name        = p.name,
            description = p.description,
            category_id = p.category_id,
            brand       = p.brand,
            hsn_code    = p.hsn_code,
            tax_rate    = p.tax_rate
        FROM products p
        WHERE i.product_id = p.id
    """))

    # Everything that existed before Phase 2 is a finished, sellable good, and is
    # counted in pieces - which is exactly what Integer quantities implied.
    conn.execute(sa.text("""
        UPDATE items SET
            item_type    = 'FINISHED_PRODUCT',
            is_sellable  = true,
            is_purchasable = true,
            is_stocked   = true,
            stock_uom_id = u.id,
            sales_uom_id = u.id,
            purchase_uom_id = u.id
        FROM units_of_measure u
        WHERE u.code = 'PC' AND u.tenant_id = items.tenant_id
    """))

    # ------------------------------------------------------ compatibility view
    # For raw SQL, BI tools or scripts that hardcode the old table name. The ORM
    # does not use this - it maps straight to items. Read-only by intent: writes
    # must go through the items table so item_type and the UoM columns cannot be
    # bypassed.
    op.execute("""
        CREATE VIEW product_variants AS
        SELECT id, product_id, sku, barcode, size, color, cost_price, selling_price,
               mrp, reorder_level, is_active, created_at, updated_at, tenant_id
        FROM items
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS product_variants")

    op.drop_index("ix_vendor_products_variant", table_name="vendor_products")
    op.drop_index("ix_vendor_products_vendor", table_name="vendor_products")
    op.alter_column("vendor_products", "cost_price", existing_type=sa.Numeric(12, 4),
                    type_=sa.Float(), existing_nullable=False,
                    postgresql_using="cost_price::double precision")
    for col in ("is_active", "lead_time_days", "min_order_qty", "purchase_uom_id"):
        op.drop_column("vendor_products", col)

    op.drop_table("item_uom_conversions")

    op.drop_index("ix_items_tenant_item_type", table_name="items")
    for col in ("notes", "is_stocked", "is_purchasable", "is_sellable", "min_stock",
                "sales_uom_id", "purchase_uom_id", "stock_uom_id", "tax_rate",
                "hsn_code", "brand", "category_id", "description", "name", "item_type"):
        op.drop_column("items", col)

    op.alter_column("items", "reorder_level", existing_type=sa.Numeric(14, 4),
                    type_=sa.INTEGER(), existing_nullable=False,
                    postgresql_using="reorder_level::integer")

    # Anything created as a non-variant (every raw material) has no parent
    # product and cannot exist in the pre-Phase-2 schema, where product_id was
    # NOT NULL. Refuse rather than silently delete a boutique's material master.
    orphans = op.get_bind().execute(
        sa.text("SELECT count(*) FROM items WHERE product_id IS NULL")
    ).scalar_one()
    if orphans:
        raise RuntimeError(
            f"Cannot downgrade: {orphans} item(s) have no parent product (raw materials, "
            "packaging or services created since Phase 2). Reverting would require deleting "
            "them. Export or reassign them to a product first, then re-run the downgrade."
        )
    op.alter_column("items", "product_id", existing_type=sa.Integer(), nullable=False)

    op.rename_table("items", "product_variants")

    op.drop_table("units_of_measure")
    op.drop_table("uom_categories")
    ITEM_TYPE.drop(op.get_bind(), checkfirst=True)
