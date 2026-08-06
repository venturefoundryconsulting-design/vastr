# Velora SaaS Architecture

How the app went from single-tenant (Tanisi) to multi-tenant (Velora — "Fashion
retail, reimagined") without rewriting any business logic. This document
describes the *as-built* architecture; see `MIGRATION_GUIDE.md` for how an
existing single-tenant install gets converted, and `SECURITY_REVIEW.md` /
`PERFORMANCE_REPORT.md` for the hardening pass.

## Model: shared database, shared schema

Every tenant lives in the same PostgreSQL database and the same tables. There
is no per-tenant schema or per-tenant database — isolation is enforced at the
query layer, automatically, for every request. This was chosen over
schema-per-tenant or database-per-tenant because it keeps migrations,
connection pooling, and operational overhead identical to the original
single-tenant app; the only new physical structure is one `tenant_id` column
per table plus a `tenants` reference table.

## Tenant isolation: automatic, not opt-in

`app/core/tenant_context.py` implements SQLAlchemy's documented "global WHERE
criteria" recipe for shared-database multi-tenancy:

- A `ContextVar[int | None]` holds the current request's tenant id.
- A `do_orm_execute` event listener, registered once on the `Session` class,
  injects `with_loader_criteria(TenantMixin, lambda cls: cls.tenant_id ==
  current_tenant_id)` into every SELECT/UPDATE/DELETE — for every mapped
  class that mixes in `TenantMixin` (`app/models/mixins.py`), including
  joins, subqueries, and aliased entities (`include_aliases=True`).
- A `before_flush` listener auto-stamps `tenant_id` on any new row that
  doesn't already have one set.

Because this runs at the `Session` level rather than in individual routers,
**the ~180 existing router/service call sites needed zero changes** to become
tenant-safe. `db.query(Product).all()` inside a request automatically becomes
"this tenant's products" — nobody has to remember to add a filter, and there
is no way to forget one.

Every model except `Tenant` itself, `User` (see below), and the two
per-tenant-singleton settings tables (which declare `tenant_id` directly with
a `unique=True` constraint instead of the mixin's plain index — see
`app/models/settings.py`, `app/models/hardware.py`) uses `TenantMixin`,
**including child/line-item tables** (`SaleItem`, `ReturnItem`,
`PurchaseOrderItem`, etc.) — not just their parents. This matters for
IDOR resistance: a request for `SaleItem` id 42 is scoped by its own
`tenant_id` column directly, not by trusting that whoever looked up the
parent `Sale` first did it correctly.

### Where this mechanism does *not* apply: `User`

`app/models/user.py`'s `User` model is deliberately **not** a `TenantMixin`
subclass. Two reasons:

1. Login resolves a user by email *before* any tenant is known — the app's
   own login flow ("user logs in → determine user's tenant") only works if
   the email lookup isn't itself tenant-scoped. `users.email` is therefore
   globally unique across the whole platform, not per-tenant. (Trade-off:
   two different tenant companies can't register the same email address —
   a common, deliberate SaaS simplification.)
2. Super Admins (`UserRole.SUPER_ADMIN`) aren't a member of any tenant at
   all — `User.tenant_id` is nullable specifically to represent this.

Because `User` is excluded from the automatic filter, every router that
queries `User` directly has to filter by `tenant_id` explicitly (see
`app/routers/users.py`, `app/routers/hrm.py`'s `list_staff`,
`app/routers/payroll.py`'s salary endpoints). This was audited as part of
the Phase 6 security review — see `SECURITY_REVIEW.md` for the two cross-
tenant leaks that audit found and fixed.

## Request flow

```
Request with "Authorization: Bearer <JWT>"
  │
  ▼
TenantContextMiddleware (app/middleware/tenant.py)
  - decodes the JWT directly (no DB call)
  - reads tenant_id + role claims
  - sets the ContextVar BEFORE any dependency injection runs
  │
  ▼
FastAPI dependency injection (get_current_user, require_*, etc.)
  - authenticates, loads the User row, checks role/permission
  │
  ▼
Endpoint body — every query automatically scoped
```

**Why the middleware, not a dependency:** FastAPI dispatches every *sync*
dependency and the *sync* endpoint body through **separate** threadpool
calls, each taking its own snapshot of the request's context. A ContextVar
mutation made inside a dependency (the original Phase 1 approach) never
reaches the endpoint body that actually runs the query — it's set in a
throwaway copy of the context. Moving the write into a pure ASGI middleware
(runs once, in the request's own coroutine, before any threadpool dispatch)
is the only placement in the stack where the mutation reliably propagates
for both sync and async routes. This bug was caught during Phase 2
verification specifically because it produces an *observable* difference
for a Super Admin token (empty vs. non-empty results) — for an ordinary
single-tenant request it silently "worked" by coincidence, which is why it
survived Phase 1's own (script-based, not HTTP-based) isolation test. See
`SECURITY_REVIEW.md` for the full writeup.

## Super Admin: default-deny, not default-open

A Super Admin's JWT has `tenant_id: null`. Naively, "no tenant in scope"
could mean "don't filter" (see everything) — which would let a Super Admin
token see every tenant's data on *any* ordinary endpoint just by having no
tenant, not just on the intended `/api/admin/*` namespace. Instead:

- `set_authenticated_no_tenant()` sets the ContextVar to a sentinel (`-1`,
  no real tenant ever has this id) — the filter still applies, it just
  matches nothing. A Super Admin hitting `/api/products` gets `[]`, not
  every tenant's products.
- Only requests to `/api/admin/*`, from a JWT whose `role` claim is
  literally `super_admin` (a claim that can't be forged without invalidating
  the signature), get the ContextVar set to `None` (genuinely unfiltered).
  `require_super_admin` (a real DB-backed role check, independent of the
  middleware) still gates every endpoint in that router — the middleware
  only ever *widens scope*, it never grants authentication.

## RBAC: two systems, deliberately not merged

- **The original three roles** (`admin`, `manager`, `outlet_staff`) keep
  using the original rank-ladder dependencies (`require_admin`,
  `require_manager_up` in `app/api/deps.py`) — completely unchanged, so
  every existing route-protection decision in the app still behaves
  identically. `TENANT_OWNER` was added to both of these (see
  `SECURITY_REVIEW.md`) since a tenant's very first user is always created
  as its Owner and needs at least Admin-equivalent access on day one.
- **The four new roles** (`tenant_owner`, `sales`, `inventory`, `viewer`)
  resolve through a `Permission` / `RolePermission` catalog
  (`app/permissions/catalog.py`) via `has_permission()` /
  `require_permission(code)`. This is architecture, not yet wired into most
  existing endpoints — retrofitting all 22 routers to check permissions
  instead of roles is future work, not part of this conversion (per the
  "prepare architecture, don't rewrite business logic unless required"
  brief).
- **Super Admin** is checked directly (`user.role == "super_admin"`) and is
  not part of either system — it's a platform-level concept, not a
  tenant-scoped permission.

## Subscriptions & feature flags: schema only

`SubscriptionPlan` (`app/models/subscription_plan.py`) is a small reference
table — one row per plan name, holding a `features: JSONB` map. Every module
is seeded `true` on every plan today; `has_feature(db, tenant, code)`
(`app/services/feature_flags.py`) is real lookup logic (not a hardcoded
stub) but isn't called from any endpoint yet. Flipping a module off for a
plan later is a data change in this table, not a code change. Billing itself
is out of scope per the original brief — `SubscriptionPlan.monthly_price` and
`Tenant.trial_end` exist as placeholders for when it's built.

## Notifications: a dispatcher over existing channels

`app/notifications/service.py` adds `send_notification(channel, ...)` as a
single call site over the channels that already work
(`app/services/email.py`, `sms.py`, `whatsapp.py` — all tenant-scoped since
Phase 1, unchanged here) plus a `PUSH` channel that raises
`NotImplementedError` until a provider exists. Nothing currently calls this
dispatcher — existing features (receipt sharing, campaign sends) still call
their service module directly.

## Frontend: two shells, one router

- The existing tenant app (`Layout.tsx` + all existing pages) is completely
  unchanged in behavior. `/dashboard` replaced `/` as the authenticated
  landing route (`/` is now the public marketing page — see below); every
  other route is untouched.
- A separate Super Admin portal (`frontend/src/admin/`) lives at
  `/platform-admin/*`, with its own shell (`SuperAdminLayout.tsx`, distinct
  indigo branding so it can't be confused with a tenant's own workspace) and
  its own guard (`RequireSuperAdmin.tsx`) that checks
  `user.role === "super_admin"` directly rather than reusing the tenant
  rank ladder (`hasMinRole`/`RequireAuth`), since Super Admin is explicitly
  not part of that ladder.
- `frontend/src/pages/Landing.tsx` is the public "Velora — Fashion retail,
  reimagined" marketing page at `/`. Logged-in visitors are redirected
  straight to `/dashboard` (or `/platform-admin/tenants` for Super Admins);
  logged-out visitors see the landing page.

## What's explicitly deferred

- **Tenant self-service branding UI** (theme color picker, dark mode,
  extending the Settings page with the remaining `Tenant` fields, extending
  the Users page role dropdown to the four new roles) — planned as Phase 4,
  not built in this pass. The backend fields (`Tenant.primary_color`, etc.)
  and the Super Admin API to set them already exist; only the tenant-facing
  self-service UI is missing.
- **Feature-flag enforcement** and **billing** — schema exists, nothing
  reads/charges yet, per the original brief.
- **Full per-tenant custom role editor** — the `Permission`/`RolePermission`
  catalog is platform-defined defaults today, not tenant-customizable.
- **Hard tenant deletion** — `DELETE /api/admin/tenants/{id}` soft-deletes
  (deactivates + cancels the subscription) rather than cascading a real
  delete across ~30 tables. See `app/routers/admin.py`'s `delete_tenant`
  docstring for the reasoning.
