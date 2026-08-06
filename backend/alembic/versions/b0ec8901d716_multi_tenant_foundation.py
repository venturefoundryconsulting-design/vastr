"""multi tenant foundation

Revision ID: b0ec8901d716
Revises: f536d909714d
Create Date: 2026-08-06 21:00:22.069064

Converts the schema from single-tenant to multi-tenant: creates `tenants`,
creates one "Tanisi" tenant row for all pre-existing data, adds `tenant_id`
to every tenant-owned table (nullable first, backfilled to Tanisi, then made
NOT NULL - never sets a NOT NULL column on a table with existing rows in one
step), and converts several previously-global-unique columns (sku, barcode,
outlet code, invoice/PO/transfer/return/alteration numbers, discount codes,
provider types) to unique-per-tenant instead.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b0ec8901d716'
down_revision: Union[str, None] = 'f536d909714d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Every tenant-owned table via TenantMixin, i.e. everything except `tenants`
# itself and `users` (nullable tenant_id, handled separately below).
TENANT_TABLES = [
    "alterations",
    "app_settings",
    "attendance",
    "campaign_recipients",
    "campaigns",
    "categories",
    "customer_addresses",
    "customer_balance_adjustments",
    "customer_loyalty_adjustments",
    "customers",
    "discount_rules",
    "email_providers",
    "exchange_items",
    "hardware_ai_settings",
    "leave_requests",
    "message_templates",
    "outlets",
    "payslips",
    "product_images",
    "product_variants",
    "products",
    "purchase_order_items",
    "purchase_orders",
    "return_items",
    "returns",
    "sale_items",
    "sales",
    "sms_provider_configs",
    "staff_salaries",
    "stock_levels",
    "stock_movements",
    "stock_transfer_items",
    "stock_transfers",
    "vendor_products",
    "vendors",
    "whatsapp_messages",
]


def upgrade() -> None:
    # --- 1. Create tenants, seed the one pre-existing tenant (Tanisi) ---
    op.create_table('tenants',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('company_name', sa.String(length=200), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('logo', sa.String(length=500), nullable=True),
    sa.Column('primary_color', sa.String(length=20), nullable=True),
    sa.Column('timezone', sa.String(length=60), nullable=False),
    sa.Column('currency', sa.String(length=10), nullable=False),
    sa.Column('country', sa.String(length=80), nullable=True),
    sa.Column('subscription_plan', sa.Enum('FREE', 'STARTER', 'PROFESSIONAL', 'ENTERPRISE', name='subscriptionplanname'), nullable=False),
    sa.Column('subscription_status', sa.Enum('TRIAL', 'ACTIVE', 'SUSPENDED', 'CANCELLED', name='subscriptionstatus'), nullable=False),
    sa.Column('trial_end', sa.Date(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tenants_slug'), 'tenants', ['slug'], unique=True)

    bind = op.get_bind()
    tanisi_id = bind.execute(
        sa.text(
            "INSERT INTO tenants (company_name, slug, timezone, currency, "
            "subscription_plan, subscription_status, is_active, created_at, updated_at) "
            "VALUES ('Tanisi', 'tanisi', 'Asia/Kolkata', 'INR', 'ENTERPRISE', 'ACTIVE', "
            "true, now(), now()) RETURNING id"
        )
    ).scalar_one()

    # --- 2. Add tenant_id nullable, backfill every existing row to Tanisi ---
    for table in TENANT_TABLES:
        op.add_column(table, sa.Column('tenant_id', sa.Integer(), nullable=True))
        op.execute(sa.text(f"UPDATE {table} SET tenant_id = :tid").bindparams(tid=tanisi_id))
        op.alter_column(table, 'tenant_id', nullable=False)

    # users.tenant_id stays nullable (platform Super Admins have none - see
    # app.models.user) but every existing user is Tanisi staff, so backfill anyway.
    op.add_column('users', sa.Column('tenant_id', sa.Integer(), nullable=True))
    op.execute(sa.text("UPDATE users SET tenant_id = :tid").bindparams(tid=tanisi_id))

    # --- 3. Indexes, FKs, and the tenant-scoped unique constraints ---
    op.create_index(op.f('ix_alterations_tenant_id'), 'alterations', ['tenant_id'], unique=False)
    op.drop_index('ix_alterations_alteration_number', table_name='alterations')
    op.create_index(op.f('ix_alterations_alteration_number'), 'alterations', ['alteration_number'], unique=False)
    op.create_unique_constraint('uq_alteration_tenant_number', 'alterations', ['tenant_id', 'alteration_number'])
    op.create_foreign_key(None, 'alterations', 'tenants', ['tenant_id'], ['id'])

    op.create_index(op.f('ix_app_settings_tenant_id'), 'app_settings', ['tenant_id'], unique=True)
    op.create_foreign_key(None, 'app_settings', 'tenants', ['tenant_id'], ['id'])

    op.drop_constraint('uq_attendance_staff_date', 'attendance', type_='unique')
    op.create_unique_constraint('uq_attendance_staff_date', 'attendance', ['tenant_id', 'staff_id', 'date'])
    op.create_index(op.f('ix_attendance_tenant_id'), 'attendance', ['tenant_id'], unique=False)
    op.create_foreign_key(None, 'attendance', 'tenants', ['tenant_id'], ['id'])

    op.create_index(op.f('ix_campaign_recipients_tenant_id'), 'campaign_recipients', ['tenant_id'], unique=False)
    op.create_foreign_key(None, 'campaign_recipients', 'tenants', ['tenant_id'], ['id'])

    op.create_index(op.f('ix_campaigns_tenant_id'), 'campaigns', ['tenant_id'], unique=False)
    op.create_foreign_key(None, 'campaigns', 'tenants', ['tenant_id'], ['id'])

    op.create_index(op.f('ix_categories_tenant_id'), 'categories', ['tenant_id'], unique=False)
    op.create_foreign_key(None, 'categories', 'tenants', ['tenant_id'], ['id'])

    op.create_index(op.f('ix_customer_addresses_tenant_id'), 'customer_addresses', ['tenant_id'], unique=False)
    op.create_foreign_key(None, 'customer_addresses', 'tenants', ['tenant_id'], ['id'])

    op.create_index(op.f('ix_customer_balance_adjustments_tenant_id'), 'customer_balance_adjustments', ['tenant_id'], unique=False)
    op.create_foreign_key(None, 'customer_balance_adjustments', 'tenants', ['tenant_id'], ['id'])

    op.create_index(op.f('ix_customer_loyalty_adjustments_tenant_id'), 'customer_loyalty_adjustments', ['tenant_id'], unique=False)
    op.create_foreign_key(None, 'customer_loyalty_adjustments', 'tenants', ['tenant_id'], ['id'])

    op.create_index(op.f('ix_customers_tenant_id'), 'customers', ['tenant_id'], unique=False)
    op.create_foreign_key(None, 'customers', 'tenants', ['tenant_id'], ['id'])

    op.drop_index('ix_discount_rules_code', table_name='discount_rules')
    op.create_index(op.f('ix_discount_rules_code'), 'discount_rules', ['code'], unique=False)
    op.create_index(op.f('ix_discount_rules_tenant_id'), 'discount_rules', ['tenant_id'], unique=False)
    op.create_unique_constraint('uq_discount_tenant_code', 'discount_rules', ['tenant_id', 'code'])
    op.create_foreign_key(None, 'discount_rules', 'tenants', ['tenant_id'], ['id'])

    op.drop_index('ix_email_providers_provider', table_name='email_providers')
    op.create_index(op.f('ix_email_providers_provider'), 'email_providers', ['provider'], unique=False)
    op.create_index(op.f('ix_email_providers_tenant_id'), 'email_providers', ['tenant_id'], unique=False)
    op.create_unique_constraint('uq_email_provider_tenant', 'email_providers', ['tenant_id', 'provider'])
    op.create_foreign_key(None, 'email_providers', 'tenants', ['tenant_id'], ['id'])

    op.create_index(op.f('ix_exchange_items_tenant_id'), 'exchange_items', ['tenant_id'], unique=False)
    op.create_foreign_key(None, 'exchange_items', 'tenants', ['tenant_id'], ['id'])

    op.create_index(op.f('ix_hardware_ai_settings_tenant_id'), 'hardware_ai_settings', ['tenant_id'], unique=True)
    op.create_foreign_key(None, 'hardware_ai_settings', 'tenants', ['tenant_id'], ['id'])

    op.create_index(op.f('ix_leave_requests_tenant_id'), 'leave_requests', ['tenant_id'], unique=False)
    op.create_foreign_key(None, 'leave_requests', 'tenants', ['tenant_id'], ['id'])

    op.create_index(op.f('ix_message_templates_tenant_id'), 'message_templates', ['tenant_id'], unique=False)
    op.create_foreign_key(None, 'message_templates', 'tenants', ['tenant_id'], ['id'])

    op.drop_index('ix_outlets_code', table_name='outlets')
    op.create_index(op.f('ix_outlets_code'), 'outlets', ['code'], unique=False)
    op.create_index(op.f('ix_outlets_tenant_id'), 'outlets', ['tenant_id'], unique=False)
    op.create_unique_constraint('uq_outlet_tenant_code', 'outlets', ['tenant_id', 'code'])
    op.create_foreign_key(None, 'outlets', 'tenants', ['tenant_id'], ['id'])

    op.drop_constraint('uq_payslip_staff_month', 'payslips', type_='unique')
    op.create_unique_constraint('uq_payslip_staff_month', 'payslips', ['tenant_id', 'staff_id', 'month'])
    op.create_index(op.f('ix_payslips_tenant_id'), 'payslips', ['tenant_id'], unique=False)
    op.create_foreign_key(None, 'payslips', 'tenants', ['tenant_id'], ['id'])

    op.create_index(op.f('ix_product_images_tenant_id'), 'product_images', ['tenant_id'], unique=False)
    op.create_foreign_key(None, 'product_images', 'tenants', ['tenant_id'], ['id'])

    op.drop_index('ix_product_variants_barcode', table_name='product_variants')
    op.create_index(op.f('ix_product_variants_barcode'), 'product_variants', ['barcode'], unique=False)
    op.drop_index('ix_product_variants_sku', table_name='product_variants')
    op.create_index(op.f('ix_product_variants_sku'), 'product_variants', ['sku'], unique=False)
    op.create_index(op.f('ix_product_variants_tenant_id'), 'product_variants', ['tenant_id'], unique=False)
    op.create_unique_constraint('uq_variant_tenant_barcode', 'product_variants', ['tenant_id', 'barcode'])
    op.create_unique_constraint('uq_variant_tenant_sku', 'product_variants', ['tenant_id', 'sku'])
    op.create_foreign_key(None, 'product_variants', 'tenants', ['tenant_id'], ['id'])

    op.create_index(op.f('ix_products_tenant_id'), 'products', ['tenant_id'], unique=False)
    op.create_foreign_key(None, 'products', 'tenants', ['tenant_id'], ['id'])

    op.create_index(op.f('ix_purchase_order_items_tenant_id'), 'purchase_order_items', ['tenant_id'], unique=False)
    op.create_foreign_key(None, 'purchase_order_items', 'tenants', ['tenant_id'], ['id'])

    op.drop_index('ix_purchase_orders_po_number', table_name='purchase_orders')
    op.create_index(op.f('ix_purchase_orders_po_number'), 'purchase_orders', ['po_number'], unique=False)
    op.create_index(op.f('ix_purchase_orders_tenant_id'), 'purchase_orders', ['tenant_id'], unique=False)
    op.create_unique_constraint('uq_po_tenant_number', 'purchase_orders', ['tenant_id', 'po_number'])
    op.create_foreign_key(None, 'purchase_orders', 'tenants', ['tenant_id'], ['id'])

    op.create_index(op.f('ix_return_items_tenant_id'), 'return_items', ['tenant_id'], unique=False)
    op.create_foreign_key(None, 'return_items', 'tenants', ['tenant_id'], ['id'])

    op.drop_index('ix_returns_return_number', table_name='returns')
    op.create_index(op.f('ix_returns_return_number'), 'returns', ['return_number'], unique=False)
    op.create_index(op.f('ix_returns_tenant_id'), 'returns', ['tenant_id'], unique=False)
    op.create_unique_constraint('uq_return_tenant_number', 'returns', ['tenant_id', 'return_number'])
    op.create_foreign_key(None, 'returns', 'tenants', ['tenant_id'], ['id'])

    op.create_index(op.f('ix_sale_items_tenant_id'), 'sale_items', ['tenant_id'], unique=False)
    op.create_foreign_key(None, 'sale_items', 'tenants', ['tenant_id'], ['id'])

    op.drop_index('ix_sales_invoice_number', table_name='sales')
    op.create_index(op.f('ix_sales_invoice_number'), 'sales', ['invoice_number'], unique=False)
    op.create_index(op.f('ix_sales_tenant_id'), 'sales', ['tenant_id'], unique=False)
    op.create_unique_constraint('uq_sale_tenant_invoice', 'sales', ['tenant_id', 'invoice_number'])
    op.create_foreign_key(None, 'sales', 'tenants', ['tenant_id'], ['id'])

    op.drop_index('ix_sms_provider_configs_provider', table_name='sms_provider_configs')
    op.create_index(op.f('ix_sms_provider_configs_provider'), 'sms_provider_configs', ['provider'], unique=False)
    op.create_index(op.f('ix_sms_provider_configs_tenant_id'), 'sms_provider_configs', ['tenant_id'], unique=False)
    op.create_unique_constraint('uq_sms_provider_tenant', 'sms_provider_configs', ['tenant_id', 'provider'])
    op.create_foreign_key(None, 'sms_provider_configs', 'tenants', ['tenant_id'], ['id'])

    op.create_index(op.f('ix_staff_salaries_tenant_id'), 'staff_salaries', ['tenant_id'], unique=False)
    op.create_foreign_key(None, 'staff_salaries', 'tenants', ['tenant_id'], ['id'])

    op.drop_constraint('uq_stock_variant_outlet', 'stock_levels', type_='unique')
    op.create_unique_constraint('uq_stock_variant_outlet', 'stock_levels', ['tenant_id', 'variant_id', 'outlet_id'])
    op.create_index(op.f('ix_stock_levels_tenant_id'), 'stock_levels', ['tenant_id'], unique=False)
    op.create_foreign_key(None, 'stock_levels', 'tenants', ['tenant_id'], ['id'])

    op.create_index(op.f('ix_stock_movements_tenant_id'), 'stock_movements', ['tenant_id'], unique=False)
    op.create_foreign_key(None, 'stock_movements', 'tenants', ['tenant_id'], ['id'])

    op.create_index(op.f('ix_stock_transfer_items_tenant_id'), 'stock_transfer_items', ['tenant_id'], unique=False)
    op.create_foreign_key(None, 'stock_transfer_items', 'tenants', ['tenant_id'], ['id'])

    op.drop_index('ix_stock_transfers_transfer_number', table_name='stock_transfers')
    op.create_index(op.f('ix_stock_transfers_transfer_number'), 'stock_transfers', ['transfer_number'], unique=False)
    op.create_index(op.f('ix_stock_transfers_tenant_id'), 'stock_transfers', ['tenant_id'], unique=False)
    op.create_unique_constraint('uq_transfer_tenant_number', 'stock_transfers', ['tenant_id', 'transfer_number'])
    op.create_foreign_key(None, 'stock_transfers', 'tenants', ['tenant_id'], ['id'])

    op.create_index(op.f('ix_users_tenant_id'), 'users', ['tenant_id'], unique=False)
    op.create_foreign_key(None, 'users', 'tenants', ['tenant_id'], ['id'])

    op.create_index(op.f('ix_vendor_products_tenant_id'), 'vendor_products', ['tenant_id'], unique=False)
    op.create_foreign_key(None, 'vendor_products', 'tenants', ['tenant_id'], ['id'])

    op.create_index(op.f('ix_vendors_tenant_id'), 'vendors', ['tenant_id'], unique=False)
    op.create_foreign_key(None, 'vendors', 'tenants', ['tenant_id'], ['id'])

    op.create_index(op.f('ix_whatsapp_messages_tenant_id'), 'whatsapp_messages', ['tenant_id'], unique=False)
    op.create_foreign_key(None, 'whatsapp_messages', 'tenants', ['tenant_id'], ['id'])


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'whatsapp_messages', type_='foreignkey')
    op.drop_index(op.f('ix_whatsapp_messages_tenant_id'), table_name='whatsapp_messages')
    op.drop_column('whatsapp_messages', 'tenant_id')
    op.drop_constraint(None, 'vendors', type_='foreignkey')
    op.drop_index(op.f('ix_vendors_tenant_id'), table_name='vendors')
    op.drop_column('vendors', 'tenant_id')
    op.drop_constraint(None, 'vendor_products', type_='foreignkey')
    op.drop_index(op.f('ix_vendor_products_tenant_id'), table_name='vendor_products')
    op.drop_column('vendor_products', 'tenant_id')
    op.drop_constraint(None, 'users', type_='foreignkey')
    op.drop_index(op.f('ix_users_tenant_id'), table_name='users')
    op.drop_column('users', 'tenant_id')
    op.drop_constraint(None, 'stock_transfers', type_='foreignkey')
    op.drop_constraint('uq_transfer_tenant_number', 'stock_transfers', type_='unique')
    op.drop_index(op.f('ix_stock_transfers_tenant_id'), table_name='stock_transfers')
    op.drop_index(op.f('ix_stock_transfers_transfer_number'), table_name='stock_transfers')
    op.create_index('ix_stock_transfers_transfer_number', 'stock_transfers', ['transfer_number'], unique=True)
    op.drop_column('stock_transfers', 'tenant_id')
    op.drop_constraint(None, 'stock_transfer_items', type_='foreignkey')
    op.drop_index(op.f('ix_stock_transfer_items_tenant_id'), table_name='stock_transfer_items')
    op.drop_column('stock_transfer_items', 'tenant_id')
    op.drop_constraint(None, 'stock_movements', type_='foreignkey')
    op.drop_index(op.f('ix_stock_movements_tenant_id'), table_name='stock_movements')
    op.drop_column('stock_movements', 'tenant_id')
    op.drop_constraint(None, 'stock_levels', type_='foreignkey')
    op.drop_index(op.f('ix_stock_levels_tenant_id'), table_name='stock_levels')
    op.drop_constraint('uq_stock_variant_outlet', 'stock_levels', type_='unique')
    op.create_unique_constraint('uq_stock_variant_outlet', 'stock_levels', ['variant_id', 'outlet_id'])
    op.drop_column('stock_levels', 'tenant_id')
    op.drop_constraint(None, 'staff_salaries', type_='foreignkey')
    op.drop_index(op.f('ix_staff_salaries_tenant_id'), table_name='staff_salaries')
    op.drop_column('staff_salaries', 'tenant_id')
    op.drop_constraint(None, 'sms_provider_configs', type_='foreignkey')
    op.drop_constraint('uq_sms_provider_tenant', 'sms_provider_configs', type_='unique')
    op.drop_index(op.f('ix_sms_provider_configs_tenant_id'), table_name='sms_provider_configs')
    op.drop_index(op.f('ix_sms_provider_configs_provider'), table_name='sms_provider_configs')
    op.create_index('ix_sms_provider_configs_provider', 'sms_provider_configs', ['provider'], unique=True)
    op.drop_column('sms_provider_configs', 'tenant_id')
    op.drop_constraint(None, 'sales', type_='foreignkey')
    op.drop_constraint('uq_sale_tenant_invoice', 'sales', type_='unique')
    op.drop_index(op.f('ix_sales_tenant_id'), table_name='sales')
    op.drop_index(op.f('ix_sales_invoice_number'), table_name='sales')
    op.create_index('ix_sales_invoice_number', 'sales', ['invoice_number'], unique=True)
    op.drop_column('sales', 'tenant_id')
    op.drop_constraint(None, 'sale_items', type_='foreignkey')
    op.drop_index(op.f('ix_sale_items_tenant_id'), table_name='sale_items')
    op.drop_column('sale_items', 'tenant_id')
    op.drop_constraint(None, 'returns', type_='foreignkey')
    op.drop_constraint('uq_return_tenant_number', 'returns', type_='unique')
    op.drop_index(op.f('ix_returns_tenant_id'), table_name='returns')
    op.drop_index(op.f('ix_returns_return_number'), table_name='returns')
    op.create_index('ix_returns_return_number', 'returns', ['return_number'], unique=True)
    op.drop_column('returns', 'tenant_id')
    op.drop_constraint(None, 'return_items', type_='foreignkey')
    op.drop_index(op.f('ix_return_items_tenant_id'), table_name='return_items')
    op.drop_column('return_items', 'tenant_id')
    op.drop_constraint(None, 'purchase_orders', type_='foreignkey')
    op.drop_constraint('uq_po_tenant_number', 'purchase_orders', type_='unique')
    op.drop_index(op.f('ix_purchase_orders_tenant_id'), table_name='purchase_orders')
    op.drop_index(op.f('ix_purchase_orders_po_number'), table_name='purchase_orders')
    op.create_index('ix_purchase_orders_po_number', 'purchase_orders', ['po_number'], unique=True)
    op.drop_column('purchase_orders', 'tenant_id')
    op.drop_constraint(None, 'purchase_order_items', type_='foreignkey')
    op.drop_index(op.f('ix_purchase_order_items_tenant_id'), table_name='purchase_order_items')
    op.drop_column('purchase_order_items', 'tenant_id')
    op.drop_constraint(None, 'products', type_='foreignkey')
    op.drop_index(op.f('ix_products_tenant_id'), table_name='products')
    op.drop_column('products', 'tenant_id')
    op.drop_constraint(None, 'product_variants', type_='foreignkey')
    op.drop_constraint('uq_variant_tenant_sku', 'product_variants', type_='unique')
    op.drop_constraint('uq_variant_tenant_barcode', 'product_variants', type_='unique')
    op.drop_index(op.f('ix_product_variants_tenant_id'), table_name='product_variants')
    op.drop_index(op.f('ix_product_variants_sku'), table_name='product_variants')
    op.create_index('ix_product_variants_sku', 'product_variants', ['sku'], unique=True)
    op.drop_index(op.f('ix_product_variants_barcode'), table_name='product_variants')
    op.create_index('ix_product_variants_barcode', 'product_variants', ['barcode'], unique=True)
    op.drop_column('product_variants', 'tenant_id')
    op.drop_constraint(None, 'product_images', type_='foreignkey')
    op.drop_index(op.f('ix_product_images_tenant_id'), table_name='product_images')
    op.drop_column('product_images', 'tenant_id')
    op.drop_constraint(None, 'payslips', type_='foreignkey')
    op.drop_index(op.f('ix_payslips_tenant_id'), table_name='payslips')
    op.drop_constraint('uq_payslip_staff_month', 'payslips', type_='unique')
    op.create_unique_constraint('uq_payslip_staff_month', 'payslips', ['staff_id', 'month'])
    op.drop_column('payslips', 'tenant_id')
    op.drop_constraint(None, 'outlets', type_='foreignkey')
    op.drop_constraint('uq_outlet_tenant_code', 'outlets', type_='unique')
    op.drop_index(op.f('ix_outlets_tenant_id'), table_name='outlets')
    op.drop_index(op.f('ix_outlets_code'), table_name='outlets')
    op.create_index('ix_outlets_code', 'outlets', ['code'], unique=True)
    op.drop_column('outlets', 'tenant_id')
    op.drop_constraint(None, 'message_templates', type_='foreignkey')
    op.drop_index(op.f('ix_message_templates_tenant_id'), table_name='message_templates')
    op.drop_column('message_templates', 'tenant_id')
    op.drop_constraint(None, 'leave_requests', type_='foreignkey')
    op.drop_index(op.f('ix_leave_requests_tenant_id'), table_name='leave_requests')
    op.drop_column('leave_requests', 'tenant_id')
    op.drop_constraint(None, 'hardware_ai_settings', type_='foreignkey')
    op.drop_index(op.f('ix_hardware_ai_settings_tenant_id'), table_name='hardware_ai_settings')
    op.drop_column('hardware_ai_settings', 'tenant_id')
    op.drop_constraint(None, 'exchange_items', type_='foreignkey')
    op.drop_index(op.f('ix_exchange_items_tenant_id'), table_name='exchange_items')
    op.drop_column('exchange_items', 'tenant_id')
    op.drop_constraint(None, 'email_providers', type_='foreignkey')
    op.drop_constraint('uq_email_provider_tenant', 'email_providers', type_='unique')
    op.drop_index(op.f('ix_email_providers_tenant_id'), table_name='email_providers')
    op.drop_index(op.f('ix_email_providers_provider'), table_name='email_providers')
    op.create_index('ix_email_providers_provider', 'email_providers', ['provider'], unique=True)
    op.drop_column('email_providers', 'tenant_id')
    op.drop_constraint(None, 'discount_rules', type_='foreignkey')
    op.drop_constraint('uq_discount_tenant_code', 'discount_rules', type_='unique')
    op.drop_index(op.f('ix_discount_rules_tenant_id'), table_name='discount_rules')
    op.drop_index(op.f('ix_discount_rules_code'), table_name='discount_rules')
    op.create_index('ix_discount_rules_code', 'discount_rules', ['code'], unique=True)
    op.drop_column('discount_rules', 'tenant_id')
    op.drop_constraint(None, 'customers', type_='foreignkey')
    op.drop_index(op.f('ix_customers_tenant_id'), table_name='customers')
    op.drop_column('customers', 'tenant_id')
    op.drop_constraint(None, 'customer_loyalty_adjustments', type_='foreignkey')
    op.drop_index(op.f('ix_customer_loyalty_adjustments_tenant_id'), table_name='customer_loyalty_adjustments')
    op.drop_column('customer_loyalty_adjustments', 'tenant_id')
    op.drop_constraint(None, 'customer_balance_adjustments', type_='foreignkey')
    op.drop_index(op.f('ix_customer_balance_adjustments_tenant_id'), table_name='customer_balance_adjustments')
    op.drop_column('customer_balance_adjustments', 'tenant_id')
    op.drop_constraint(None, 'customer_addresses', type_='foreignkey')
    op.drop_index(op.f('ix_customer_addresses_tenant_id'), table_name='customer_addresses')
    op.drop_column('customer_addresses', 'tenant_id')
    op.drop_constraint(None, 'categories', type_='foreignkey')
    op.drop_index(op.f('ix_categories_tenant_id'), table_name='categories')
    op.drop_column('categories', 'tenant_id')
    op.drop_constraint(None, 'campaigns', type_='foreignkey')
    op.drop_index(op.f('ix_campaigns_tenant_id'), table_name='campaigns')
    op.drop_column('campaigns', 'tenant_id')
    op.drop_constraint(None, 'campaign_recipients', type_='foreignkey')
    op.drop_index(op.f('ix_campaign_recipients_tenant_id'), table_name='campaign_recipients')
    op.drop_column('campaign_recipients', 'tenant_id')
    op.drop_constraint(None, 'attendance', type_='foreignkey')
    op.drop_index(op.f('ix_attendance_tenant_id'), table_name='attendance')
    op.drop_constraint('uq_attendance_staff_date', 'attendance', type_='unique')
    op.create_unique_constraint('uq_attendance_staff_date', 'attendance', ['staff_id', 'date'])
    op.drop_column('attendance', 'tenant_id')
    op.drop_constraint(None, 'app_settings', type_='foreignkey')
    op.drop_index(op.f('ix_app_settings_tenant_id'), table_name='app_settings')
    op.drop_column('app_settings', 'tenant_id')
    op.drop_constraint(None, 'alterations', type_='foreignkey')
    op.drop_constraint('uq_alteration_tenant_number', 'alterations', type_='unique')
    op.drop_index(op.f('ix_alterations_tenant_id'), table_name='alterations')
    op.drop_index(op.f('ix_alterations_alteration_number'), table_name='alterations')
    op.create_index('ix_alterations_alteration_number', 'alterations', ['alteration_number'], unique=True)
    op.drop_column('alterations', 'tenant_id')
    op.drop_index(op.f('ix_tenants_slug'), table_name='tenants')
    op.drop_table('tenants')
    # ### end Alembic commands ###
