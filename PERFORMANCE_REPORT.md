# Performance Report — Multi-Tenant Conversion (Phase 6)

## Indexing strategy

Every tenant-owned table already carries a plain index on `tenant_id` alone
(added in the Phase 1 migration, one per table — `ix_<table>_tenant_id`).
That's sufficient for "give me all of this tenant's rows" queries, but a
single-column index can't efficiently serve a query that filters by tenant
**and** sorts/filters by a second column in the same pass — Postgres would
use the tenant_id index to narrow the set, then sort/filter the remaining
rows without index help.

Phase 6 adds composite indexes for exactly the query shapes the app
actually runs, matching the spec's requested pattern
`(tenant_id, created_at)`, `(tenant_id, status)`, `(tenant_id,
customer_id)`, `(tenant_id, product_id)`:

| Table | Index | Serves |
|---|---|---|
| `sales` | `(tenant_id, created_at)` | Sales trend / recent-sales queries (`reports.py`, `dashboard.py`) |
| `sales` | `(tenant_id, customer_id)` | Customer purchase history |
| `purchase_orders` | `(tenant_id, status)` | "Open POs" dashboard count, PO list filtering |
| `purchase_orders` | `(tenant_id, created_at)` | Recent-POs dashboard widget |
| `stock_transfers` | `(tenant_id, status)` | "In-transit transfers" dashboard count |
| `stock_transfers` | `(tenant_id, created_at)` | Recent-transfers dashboard widget |
| `stock_movements` | `(tenant_id, created_at)` | Movement history, stock-aging's last-sold subquery |
| `alterations` | `(tenant_id, status)`, `(tenant_id, created_at)`, `(tenant_id, customer_id)` | Alterations board filtering/sorting, customer alteration history |
| `returns` | `(tenant_id, created_at)`, `(tenant_id, customer_id)` | Returns list, customer return history |
| `campaigns` | `(tenant_id, created_at)` | Campaign list, newest-first |
| `product_variants` | `(tenant_id, product_id)` | Variant lookup by product (product detail page, every checkout/inventory lookup) |
| `discount_rules` | `(tenant_id, product_id)` | Product-scoped discount rule lookup at checkout |

15 indexes total, all created in
`backend/alembic/versions/02945bbc9a7d_phase_6_composite_performance_indexes.py`.

Not indexed further: tables with low row counts per tenant that will never
benefit from more than the existing single-column index in practice (e.g.
`outlets`, `categories`, `email_providers`) — added complexity with no
measurable benefit at expected scale.

## The isolation mechanism's own cost

The global tenant filter (`with_loader_criteria`, see
`SAAS_ARCHITECTURE.md`) adds one `AND tenant_id = :tenant_id` predicate to
every affected query's `WHERE` clause. This is the same predicate a manually
tenant-scoped query would have needed anyway — the automatic mechanism adds
no *additional* filtering cost over what correct code would already be
doing; it just guarantees the predicate is never missing. The `tenant_id`
index (plain or composite) makes this predicate cheap in every case audited
above.

## Where this wasn't (and shouldn't be) benchmarked

No load testing or query-plan profiling (`EXPLAIN ANALYZE`) was run as part
of this pass — the current dataset (one production tenant, seed-scale
data) is far too small for realistic numbers, and synthetic benchmarks
against empty/toy data tend to produce misleading conclusions about which
indexes matter at real scale. The index list above is chosen from **reading
the actual query code** (`reports.py`, `dashboard.py`, and friends) for
which columns are filtered/sorted together, not from profiling. Recommend
revisiting with `EXPLAIN ANALYZE` against production-scale data once
multiple tenants have meaningful transaction volume — Postgres's query
planner may prefer different composite orderings, or want partial indexes
(e.g. `WHERE status != 'cancelled'`) once real data distribution is known.

## Multi-tenant-specific performance considerations for later

- **Row growth is per-tenant, not global.** A single "busy" tenant with a
  huge sales history doesn't slow down queries for other tenants — every
  query is already scoped down to one tenant's rows before any sort/filter
  work happens, thanks to the index-backed `tenant_id` predicate.
- **Connection pool sizing** (`app/core/database.py`'s `create_engine`) uses
  SQLAlchemy's defaults today. Worth revisiting pool size once concurrent
  tenant count justifies it — not adjusted in this pass since there's no
  data yet on real concurrent load.
- **The permission check** (`has_permission()` in
  `app/permissions/service.py`) does a DB round-trip per call and isn't
  cached. It's not currently wired into any hot path (see
  `SAAS_ARCHITECTURE.md` — the new roles' permission system isn't retrofit
  into existing endpoints yet), so this hasn't mattered in practice; worth
  adding a short-lived cache if/when it is.
