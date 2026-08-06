# Security Review — Multi-Tenant Conversion (Phase 6)

Scope: tenant isolation, authentication/authorization, and injection surface
across the changes made in Phases 1–3 and 5. This is a manual code review +
live cross-tenant testing pass, not an automated scan.

## Findings

### 1. [Fixed, Critical] Tenant filter never actually applied over real HTTP requests

**Where:** `app/core/tenant_context.py` + `app/api/deps.py` (Phase 1 state)

**What:** The original design set the tenant `ContextVar` inside
`get_current_user`, a FastAPI dependency. FastAPI dispatches every *sync*
dependency and the *sync* endpoint body through **separate**
`run_in_threadpool` calls, each of which takes its own independent snapshot
of the request's context via `contextvars.copy_context()`. A mutation made
inside one threadpool call (the dependency) is invisible to a later,
separate threadpool call (the endpoint body) — so the tenant filter was
being set in a copy of the context that was discarded immediately after
`get_current_user` returned, and the actual query code ran with the
ContextVar still at its default.

**Impact:** every tenant-scoped query would have silently run unfiltered in
production. For a deployment with only one tenant (Tanisi, at the time),
"unfiltered" and "correctly filtered" produce identical results, which is
exactly why this went undetected during Phase 1: that phase's own isolation
test created a second tenant's data and queried it via a **synchronous
Python script in the same process**, not a real HTTP request — so it never
exercised FastAPI's threadpool dispatch at all, and passed despite the bug.

**How it was caught:** Phase 2 added a Super Admin role whose JWT carries
`tenant_id: null`. Testing that account against an ordinary endpoint
(`GET /api/products`) over real HTTP produced Tanisi's product list instead
of an empty result — an observable failure that a same-tenant test can't
produce.

**Fix:** moved the ContextVar write into `app/middleware/tenant.py`, a pure
ASGI middleware that runs once in the request's own coroutine *before*
FastAPI's dependency injection (and therefore before any threadpool
dispatch) begins. Every later threadpool call — every dependency, the
endpoint body — takes its context snapshot from *after* the middleware ran,
so all of them see the same tenant id.

**Verified:** re-ran the full isolation suite over real HTTP (not scripts)
after the fix — see "Live cross-tenant testing" below.

### 2. [Fixed, High] Super Admin default-open instead of default-deny

**Where:** `app/api/deps.py::get_current_user` (Phase 1 state, alongside
finding #1)

**What:** Before the fix, a Super Admin's `tenant_id = None` was passed
straight to `set_current_tenant_id(None)`, and the filter's own logic treats
`None` as "no tenant in scope → skip filtering entirely." Combined with
finding #1's threading bug this was moot (the value never reached the query
layer at all), but fixing #1 alone would have re-exposed this: a Super
Admin token would then have gotten **fully unfiltered, cross-tenant** access
on *every* endpoint, not just the intended `/api/admin/*` namespace.

**Fix:** `set_authenticated_no_tenant()` (`app/core/tenant_context.py`) sets
a sentinel value (`-1`) instead of `None` for an authenticated user with no
tenant — the filter still runs, it just matches no real tenant, so ordinary
endpoints correctly return nothing. `app/middleware/tenant.py` only sets
the ContextVar to genuinely-unfiltered `None` when *both* the JWT's `role`
claim is `super_admin` *and* the request path starts with `/api/admin`.

**Verified:** Super Admin token against `GET /api/products` and
`GET /api/customers` → `[]`. Same token against `GET /api/admin/tenants` →
full cross-tenant list, as intended.

### 3. [Fixed, High] Cross-tenant staff list leaks in HRM and Payroll

**Where:** `app/routers/hrm.py::list_staff`,
`app/routers/payroll.py::list_salaries`

**What:** `User` is intentionally excluded from the automatic tenant filter
(see `SAAS_ARCHITECTURE.md` for why — email must be globally unique for the
login flow, and Super Admins have no tenant). Every router that queries
`User` directly therefore has to filter by `tenant_id` manually. Two
call sites didn't: both listed **every active user across every tenant**,
not just the caller's own tenant's staff.

**Impact:** any authenticated Manager/Admin at any tenant could see the
names, roles, and outlet assignments of every other tenant's staff via the
HRM staff picker or the Payroll salary list.

**Fix:** both queries now filter `User.tenant_id == current_user.tenant_id`.

### 4. [Fixed, High] IDOR in salary update

**Where:** `app/routers/payroll.py::update_salary`

**What:** `staff = db.get(User, staff_id)` performed no tenant check before
creating/updating a `StaffSalary` row for that `staff_id`. Since
`StaffSalary` *is* tenant-filtered and auto-stamped with the *caller's*
tenant on creation, a malicious/curious admin at Tenant A could supply
Tenant B's numeric `staff_id` and create a `StaffSalary` row tagged as
belonging to Tenant A but referencing Tenant B's user — a cross-tenant data
integrity violation, not just a read-only leak.

**Fix:** the lookup now filters `User.id == staff_id AND User.tenant_id ==
current_user.tenant_id`, returning 404 for any staff_id outside the
caller's own tenant.

### 5. [Fixed, Medium — functional, not a security hole] Tenant Owner locked out of Admin-gated routes

**Where:** `app/api/deps.py::require_admin`, `require_manager_up`

**What:** `require_admin` checked for the literal `UserRole.ADMIN` enum
value. A newly-created tenant's very first user (always created with role
`tenant_owner` — see `routers/admin.py::create_tenant`) got `403 Forbidden`
on Outlets, Users, Settings, Payroll, Hardware, and Integrations — every
route gated by the original `require_admin`/`require_manager_up`
dependencies. Caught by live-testing tenant creation end-to-end: a brand
new tenant's Owner couldn't configure their own outlets on day one.

**Fix:** both dependencies now also accept `UserRole.TENANT_OWNER`,
consistent with the permission catalog already granting that role every
permission Admin has (`app/permissions/catalog.py::ROLE_GRANTS`).

**Known follow-up (not fixed, out of scope for this pass):** the frontend's
`UserRole` type and `hasMinRole`/`ROLE_RANK` (`frontend/src/utils/roles.ts`)
still only model the original three roles. A Tenant Owner logging into the
tenant app UI (as opposed to the Super Admin portal) will currently have
Admin-gated nav items hidden, even though the backend now correctly permits
the equivalent API calls. This is Phase 4 scope (extending the frontend's
role handling) and doesn't affect Super Admin portal access, which uses its
own separate guard.

## Verified, no issue found

**SQL injection:** grepped for raw string-formatted SQL (`f"SELECT`,
`f"UPDATE`, `.execute(f"..."`, etc.) across `backend/app` — none found.
Every query goes through the SQLAlchemy ORM/Core query builder with bound
parameters. The only raw SQL in the codebase lives in Alembic migrations
(developer-authored, not driven by user input).

**JWT tampering:** `create_access_token`/`decode_access_token`
(`app/core/security.py`) sign/verify with HMAC (`python-jose`,
`settings.SECRET_KEY`). A tampered `tenant_id` or `role` claim invalidates
the signature and `decode_access_token` returns `None`, which both
`get_current_user` and `TenantContextMiddleware` treat as unauthenticated.
There is no code path that trusts an unsigned or client-supplied tenant id
— the ContextVar is only ever set from a value taken out of a verified JWT.

**Privilege escalation via request body:** `UserUpdate`/`TenantUpdate`
schemas don't accept `tenant_id` as a field, so a user can't reassign
themselves (or anyone) to a different tenant via the API even if they tried
to smuggle the field into a PATCH body — Pydantic drops unknown fields by
default.

**IDOR — everything else:** every other `db.get(Model, id)` / `db.query
(Model).filter(Model.id == id)` call site across all 23 routers targets a
`TenantMixin` model, which is automatically scoped by the global filter
(verified live — see below) regardless of whether the router itself
remembers to check. `User` was the sole exception (findings #3–4).

**WhatsApp webhook (`app/routers/webhooks.py`):** intentionally
unauthenticated (Meta calls it) and runs outside any tenant context by
design. It looks up `CampaignRecipient` by `provider_message_id` — an
unguessable id assigned by Meta when the message was sent, not user input —
and only flips a status enum on a matched row. No tenant data is returned
to the caller. Accepted as-is; matches the existing design from before this
conversion.

## Live cross-tenant testing (post-fix)

Performed over real HTTP against the local dev server (not in-process
scripts), using a temporary second tenant ("TestCo") created via the Super
Admin API, with its own outlet, product, variant, and stock:

| Check | Result |
|---|---|
| TestCo owner login → `/api/products` | Only TestCo's product, not Tanisi's |
| TestCo owner → `/api/outlets` | Only TestCo's outlet |
| TestCo owner → `/api/dashboard/summary` | Counts match TestCo only (1 outlet, 1 product) vs. Tanisi's (3, 2) |
| TestCo owner → `/api/reports/stock-aging` (subquery + 4-way join) | Only TestCo's stock row |
| Tanisi admin → same endpoints, same moment | Only Tanisi's data, unaffected by TestCo's existence |
| Super Admin token → `/api/products` (ordinary endpoint) | `[]` (default-deny, not leak) |
| Super Admin token → `/api/admin/tenants` | Full list, both tenants (intended) |
| Tanisi admin (role=`admin`) → `/platform-admin/*` (frontend) and `/api/admin/*` (backend) | 403 in both |
| Suspend tenant → that tenant's users attempt login | Blocked with a clear message |
| Reset a tenant user's password via Super Admin API → login with new password | Succeeds |
| Audit log entries for the above actions | Present, correctly tenant-scoped, visible in that tenant's activity tab only |

The stock-aging check specifically targets the highest-risk query in the
codebase (a raw `.subquery()` outer-joined into a 4-entity tuple select) —
confirming `with_loader_criteria` correctly reaches inside it too, not just
simple single-entity queries.

Test tenant and its data were deleted after verification; production
(`vfcx.tech`) was not touched at any point during this review.
