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
    ("bom.view", "Manufacturing", "View bills of materials"),
    ("bom.create", "Manufacturing", "Create a bill of materials"),
    ("bom.edit", "Manufacturing", "Edit a draft bill of materials"),
    ("bom.activate", "Manufacturing", "Activate a BOM version for production"),
    ("bom.archive", "Manufacturing", "Archive a BOM version"),
    ("bom.cost.view", "Manufacturing", "View estimated material cost of a BOM"),
    ("production.view", "Manufacturing", "View production orders"),
    ("production.create", "Manufacturing", "Create production orders"),
    ("production.edit", "Manufacturing", "Edit a draft production order"),
    ("production.plan", "Manufacturing", "Mark a production order as planned"),
    ("production.release", "Manufacturing", "Release a production order for execution"),
    ("production.hold", "Manufacturing", "Put a production order on hold or resume it"),
    ("production.cancel", "Manufacturing", "Cancel a production order"),
    ("production.close_short", "Manufacturing", "Close a production order below its planned quantity"),
    ("materials.view", "Manufacturing", "View material reservations, issues and consumption"),
    ("materials.reserve", "Manufacturing", "Reserve material for a production order"),
    ("materials.release", "Manufacturing", "Release an unused material reservation"),
    ("materials.issue", "Manufacturing", "Issue reserved material to production"),
    ("materials.issue_unreserved", "Manufacturing", "Issue material beyond what is reserved"),
    ("materials.consume", "Manufacturing", "Record actual material consumption"),
    ("materials.return", "Manufacturing", "Return unused material from production"),
    ("production.output", "Manufacturing", "Record finished output from a production order"),
    ("production.complete", "Manufacturing", "Complete a production order"),
    ("tailors.view", "Manufacturing", "View tailors and their workload"),
    ("tailors.manage", "Manufacturing", "Create and edit tailors and skills"),
    ("stages.manage", "Manufacturing", "Configure production stages"),
    ("work_orders.view", "Manufacturing", "View all work orders"),
    ("work_orders.assign", "Manufacturing", "Create and assign work orders"),
    ("work_orders.own", "Manufacturing", "See and drive your own work orders"),
    ("qc.view", "Manufacturing", "View quality checks"),
    ("qc.create", "Manufacturing", "Record a quality check"),
    ("qc.rework", "Manufacturing", "Raise and resolve rework"),
    ("wastage.view", "Manufacturing", "View production wastage"),
    ("wastage.record", "Manufacturing", "Record production wastage"),
    ("costing.view", "Manufacturing", "View production cost and variance"),
    ("production.reports", "Manufacturing", "View manufacturing reports"),
    ("measurements.view", "Customers", "View customer measurements"),
    ("measurements.manage", "Customers", "Record and edit customer measurements"),
    ("customer_orders.view", "Sales", "View customer orders"),
    ("customer_orders.create", "Sales", "Create customer orders"),
    ("customer_orders.confirm", "Sales", "Confirm a customer order and start production"),
    ("customer_orders.deliver", "Sales", "Deliver a customer order and raise the sale"),
    ("customer_orders.cancel", "Sales", "Cancel a customer order"),
    ("goods_receipts.view", "Purchasing", "View goods receipts"),
    ("goods_receipts.create", "Purchasing", "Record a goods receipt"),
    ("goods_receipts.post", "Purchasing", "Post a goods receipt into stock"),
    ("purchase_returns.manage", "Purchasing", "Send goods back to a vendor"),
    ("mrp.view", "Purchasing", "View material requirement planning"),
    ("mrp.generate_po", "Purchasing", "Draft purchase orders from MRP shortages"),
    ("outlets.manage", "Admin", "Create and edit outlets"),
]

_ALL_CODES = {code for code, _, _ in PERMISSION_CATALOG}
# Granted to nobody by default. Issuing material that was never reserved
# bypasses the commitment model, so it is opt-in per deployment rather than
# something a role picks up by being powerful.
_NEVER_BY_DEFAULT = {"materials.issue_unreserved"}
_VIEW_ONLY = {code for code in _ALL_CODES if code.endswith(".view")}

# Default grants per role. tenant_owner/admin get everything; the others get a
# sensible operational subset matching what the role name implies. These are
# platform defaults - a per-tenant custom role editor is future scope.
ROLE_GRANTS: dict[UserRole, set[str]] = {
    UserRole.TENANT_OWNER: _ALL_CODES - _NEVER_BY_DEFAULT,
    UserRole.ADMIN: _ALL_CODES - _NEVER_BY_DEFAULT,
    UserRole.MANAGER: _ALL_CODES - _NEVER_BY_DEFAULT - {"settings.manage", "users.manage", "outlets.manage"},
    UserRole.SALES: {
        "pos.access", "sales.view", "sales.create", "returns.manage",
        "customers.view", "customers.edit", "products.view",
        "measurements.view", "measurements.manage",
        "customer_orders.view", "customer_orders.create", "customer_orders.confirm",
        "customer_orders.deliver", "customer_orders.cancel",
    },
    UserRole.INVENTORY: {
        "inventory.view", "inventory.edit", "products.view", "products.edit",
        "transfers.manage", "purchase_orders.view", "purchase_orders.edit", "vendors.manage",
        "goods_receipts.view", "goods_receipts.create", "goods_receipts.post",
        "purchase_returns.manage", "mrp.view", "mrp.generate_po",
        "bom.view", "bom.cost.view", "production.view",
        "materials.view", "materials.issue", "materials.return",
    },
    UserRole.OUTLET_STAFF: {
        "pos.access", "sales.view", "sales.create", "customers.view",
        "measurements.view", "measurements.manage",
        "customer_orders.view", "customer_orders.create", "customer_orders.deliver",
    },
    # A tailor gets their own queue and nothing else. Explicitly NOT purchasing,
    # reports, other people's records, settings, or arbitrary stock adjustment.
    UserRole.TAILOR: {"work_orders.own", "materials.view"},
    UserRole.VIEWER: set(_VIEW_ONLY),
    # SUPER_ADMIN is platform-level and never tenant-permission-checked (see
    # require_super_admin) - deliberately no entry here.
}
