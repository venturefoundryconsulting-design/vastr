# Single-Tenant → SaaS Migration Guide

How an existing single-tenant install of this app (schema before the Phase 1
migration `b0ec8901d716`) becomes a multi-tenant Velora install. This is
exactly what happened to Tanisi's own data during development — this guide
generalizes that process for any other pre-conversion install (e.g. staging,
another self-hosted deployment).

## Before you start

- **Back up the database.** `pg_dump` the whole database before running
  anything below. Every step here is designed to be non-destructive
  (nullable-first, backfill, then constrain), but a migration touching
  every table in a live database always warrants a real backup first, not
  just confidence in the migration's own design.
- **Plan a maintenance window**, or at minimum expect a brief period where
  the app should not be actively writing data while Alembic applies
  migrations `b0ec8901d716` through `02945bbc9a7d` (multi-tenant foundation
  → composite indexes). None of these individually take long against a
  small dataset, but they run as a sequence and the app's own request
  handling should be paused (or the app taken offline) for the duration to
  avoid writes racing the schema change.
- This process assumes exactly **one** existing tenant's worth of data (a
  single company's rows, no tenant concept yet) — which is the situation
  every pre-conversion install is in by definition.

## What the migration chain actually does

Running `alembic upgrade head` from a pre-conversion database applies, in
order:

1. **`b0ec8901d716` (multi-tenant foundation)**
   - Creates the `tenants` table.
   - Inserts one tenant row (`company_name='Tanisi', slug='tanisi'` in the
     original conversion — rename this for a different install, see below).
   - Adds `tenant_id` to every tenant-owned table as **nullable**, backfills
     every existing row to the one tenant's id, *then* alters the column to
     `NOT NULL`. Never sets a NOT NULL constraint on a column with existing
     unbackfilled rows in one step.
   - Converts several previously-globally-unique columns (`sku`, `barcode`,
     outlet `code`, invoice/PO/transfer/return/alteration numbers, discount
     codes, integration provider types) to unique-per-tenant instead of
     globally unique.
   - `users.tenant_id` is added but stays **nullable** — see
     `SAAS_ARCHITECTURE.md` for why (Super Admins have none).

2. **`eacd4d950ed2` (Phase 2: RBAC, audit, Super Admin)**
   - Extends the `userrole` Postgres enum with 5 new values (via an
     autocommit block — Postgres requires `ALTER TYPE ... ADD VALUE` to run
     outside the migration's normal transaction).
   - Creates `permissions`, `role_permissions` (seeded from
     `app/permissions/catalog.py`), and `audit_logs`.

3. **`31a11fe886ba` (Phase 3: subscription plans)**
   - Creates `subscription_plans`, seeded with Free/Starter/Professional/
     Enterprise, every module enabled on every plan.

4. **`02945bbc9a7d` (Phase 6: composite indexes)**
   - Adds the 15 composite `(tenant_id, X)` indexes described in
     `PERFORMANCE_REPORT.md`.

## Step by step

```bash
# 1. Back up first.
pg_dump -Fc "$DATABASE_URL" > backup-before-saas-migration.dump

# 2. Take the app offline (or at least stop accepting writes) for the
#    duration of the next step.

# 3. Apply the migration chain.
cd backend
alembic upgrade head

# 4. If this install's tenant should be named/slugged differently than
#    "Tanisi"/"tanisi" (the name baked into migration b0ec8901d716 for the
#    original conversion), update it now:
python -c "
from app.core.database import SessionLocal
from app.models.tenant import Tenant
db = SessionLocal()
t = db.query(Tenant).first()
t.company_name = 'Your Company Name'
t.slug = 'your-company-slug'
db.commit()
print('Updated tenant:', t.company_name, t.slug)
db.close()
"

# 5. Bring the app back online and smoke-test: log in as an existing user,
#    confirm the dashboard/products/customers/etc. show exactly the same
#    data as before the migration (there's only one tenant, so output
#    should be bit-for-bit identical to pre-migration).
```

## Rollback

Every migration in this chain has a corresponding `downgrade()`. If
something goes wrong before step 5 (the app hasn't been used against the
new schema yet):

```bash
alembic downgrade f536d909714d   # back to the last pre-SaaS migration
```

One caveat, documented in the migration file itself: Postgres has no
`ALTER TYPE ... DROP VALUE`, so downgrading past `eacd4d950ed2` doesn't
remove the 5 new `userrole` enum labels it added — harmless (nothing
references them once the tables that used them are dropped by the
downgrade), but worth knowing if you inspect the enum type afterward and
see extra labels.

If the app **has** been used against the new schema (new tenants created,
new-role users added, etc.), don't downgrade — restore from the Step 1
backup instead. Downgrading after real multi-tenant data exists will lose
it.

## Creating a Super Admin account

The migration doesn't create one automatically (there's no "default"
platform operator to assume). Create the first one directly:

```bash
python -c "
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole

db = SessionLocal()
db.add(User(
    name='Platform Admin',
    email='admin@yourplatform.example',
    hashed_password=hash_password('choose-a-real-password'),
    role=UserRole.SUPER_ADMIN,
    tenant_id=None,
))
db.commit()
print('Super Admin created')
db.close()
"
```

Log in with those credentials — the app redirects Super Admins straight to
`/platform-admin/tenants`.

## Onboarding additional tenants after the migration

Once the platform is live, new tenants no longer go through this migration
process at all — they're created instantly via the Super Admin portal
(`POST /api/admin/tenants`, or the "New Tenant" button in
`/platform-admin/tenants`), which creates the `Tenant` row and its first
user (role `tenant_owner`) in one step. This one-time migration is only for
converting the *original* pre-SaaS data.
