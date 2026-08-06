"""The permission catalog and default role grants.

This is architecture, not enforcement: the original three roles (admin/
manager/outlet_staff) keep working exactly as before through the existing
`require_admin`/`require_manager_up`/`require_roles` dependencies (see
app.api.deps) - nothing about them changes. The four new roles (tenant_owner,
sales, inventory, viewer) are resolved through `has_permission()` instead of
being folded into that rank ladder, since they're specializations, not a
strict "higher/lower" fit. Retrofitting every existing endpoint to check
permissions instead of roles is future work, not this phase.
"""

from app.models.user import UserRole

# (code, category, description)
PERMISSION_CATALOG: list[tuple[str, str, str]] = [
    ("products.view", "Products", "View the product catalog"),
    ("products.edit", "Products", "Create, edit, and import products"),
    ("inventory.view", "Inventory", "View stock levels and movements"),
    ("inventory.edit", "Inventory", "Adjust stock, receive transfers"),
    ("pos.access", "Sales", "Use the point-of-sale screen"),
    ("sales.view", "Sales", "View the sales list and receipts"),
    ("sales.create", "Sales", "Record new sales"),
    ("returns.manage", "Sales", "Process returns and exchanges"),
    ("customers.view", "Customers", "View customer profiles"),
    ("customers.edit", "Customers", "Create and edit customer profiles"),
    ("discounts.manage", "Discounts", "Create and edit discount rules"),
    ("campaigns.manage", "Marketing", "Create and send WhatsApp campaigns"),
    ("alterations.manage", "Alterations", "Track and update tailoring jobs"),
    ("purchase_orders.view", "Purchasing", "View purchase orders"),
    ("purchase_orders.edit", "Purchasing", "Create and receive purchase orders"),
    ("vendors.manage", "Purchasing", "Create and edit vendors"),
    ("transfers.manage", "Inventory", "Create and receive stock transfers"),
    ("reports.view", "Reports", "View sales, stock, and other reports"),
    ("hrm.view", "HRM", "View attendance and leave records"),
    ("hrm.manage", "HRM", "Approve leave, correct attendance"),
    ("payroll.manage", "HRM", "View and process payroll"),
    ("settings.manage", "Admin", "Edit organization/business settings"),
    ("users.manage", "Admin", "Create and edit staff accounts"),
    ("outlets.manage", "Admin", "Create and edit outlets"),
]

_ALL_CODES = {code for code, _, _ in PERMISSION_CATALOG}
_VIEW_ONLY = {code for code in _ALL_CODES if code.endswith(".view")}

# Default grants per role. tenant_owner/admin get everything; the others get a
# sensible operational subset matching what the role name implies. These are
# platform defaults - a per-tenant custom role editor is future scope.
ROLE_GRANTS: dict[UserRole, set[str]] = {
    UserRole.TENANT_OWNER: set(_ALL_CODES),
    UserRole.ADMIN: set(_ALL_CODES),
    UserRole.MANAGER: _ALL_CODES - {"settings.manage", "users.manage", "outlets.manage"},
    UserRole.SALES: {
        "pos.access", "sales.view", "sales.create", "returns.manage",
        "customers.view", "customers.edit", "products.view",
    },
    UserRole.INVENTORY: {
        "inventory.view", "inventory.edit", "products.view", "products.edit",
        "transfers.manage", "purchase_orders.view", "purchase_orders.edit", "vendors.manage",
    },
    UserRole.OUTLET_STAFF: {"pos.access", "sales.view", "sales.create", "customers.view"},
    UserRole.VIEWER: set(_VIEW_ONLY),
    # SUPER_ADMIN is platform-level and never tenant-permission-checked (see
    # require_super_admin) - deliberately no entry here.
}
