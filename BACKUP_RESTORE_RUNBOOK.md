# Backup & Restore Runbook

Phase 10 hardening. This is the generic procedure for any deployment of this
codebase (vastr.space, vfcx.tech, or a future one) — deployment-specific paths
and credentials live in each deployment's own `.env.prod` / compose file, not
here.

## Why this matters more than usual here

Manufacturing data is not just rows — it's a ledger. `stock_movements` is
append-only and `stock_levels` is a cache that must equal
`SUM(stock_movements.quantity_delta)` per `(variant_id, outlet_id)` (see
`backend/tests/test_ledger_integrity.py`). A restore that loses movements but
keeps levels, or vice versa, silently breaks that invariant — the app will
look fine until someone runs a reconciliation report. **Always restore the
whole database as one unit, never individual tables.**

## Routine backup

One `pg_dump` per deployment, daily, via cron on the host (not inside the
container — the container is disposable, the dump should not be):

```bash
# /opt/<app>/backup.sh, run by cron
set -euo pipefail
cd /opt/<app>
STAMP=$(date +%Y%m%d-%H%M%S)
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db \
  pg_dump -U "$(grep POSTGRES_USER .env.prod | cut -d= -f2)" \
          "$(grep POSTGRES_DB .env.prod | cut -d= -f2)" \
  | gzip > "/opt/backups/<app>-$STAMP.sql.gz"

# Keep 14 days, delete older
find /opt/backups -name "<app>-*.sql.gz" -mtime +14 -delete
```

```cron
# crontab -e (root)
17 2 * * * /opt/<app>/backup.sh >> /var/log/<app>-backup.log 2>&1
```

Plain SQL dump (`pg_dump` without `-Fc`), gzipped — not a binary/custom-format
dump. That trade-off is deliberate: a `.sql.gz` is restorable with nothing but
`psql`, on a box that may not have the exact matching `pg_restore` version,
which matters more for a small operation than the smaller size or parallel
restore a custom-format dump would buy.

**Before any risky operation** (a migration, a manual data fix, a version
rollback) — not just on the daily schedule — take an out-of-band dump first
and name it for what it's protecting against:

```bash
docker compose ... exec -T db pg_dump -U ... ... > /root/<app>-pre-<what>.sql
```

This is exactly what was done before the manufacturing-module migration
batch on vastr.space on 2026-08-27 — see the deploy notes for that session.

## Restore procedure

**Stop the backend first.** A restore into a database the app is actively
writing to will either fail (lock contention) or, worse, half-succeed and
leave the ledger inconsistent with whatever writes land mid-restore.

```bash
cd /opt/<app>
docker compose --env-file .env.prod -f docker-compose.prod.yml stop backend

# Drop and recreate the target database (adjust names from .env.prod)
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db \
  psql -U <user> -d postgres -c "DROP DATABASE IF EXISTS <db> WITH (FORCE);"
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db \
  psql -U <user> -d postgres -c "CREATE DATABASE <db>;"

# Restore
gunzip -c /opt/backups/<app>-<stamp>.sql.gz | \
  docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db \
  psql -U <user> -d <db>

docker compose --env-file .env.prod -f docker-compose.prod.yml start backend
```

## Verify before declaring the restore done

Three checks, in order — do not skip to "the app loads":

1. **Migration head matches the running code.**
   ```bash
   docker compose ... exec backend alembic current
   docker compose ... exec backend alembic heads
   ```
   These must match. If the restored dump predates a migration the running
   code expects, `alembic upgrade head` before starting the backend, not after
   — the app will otherwise 500 on the first request that touches the missing
   column/table.

2. **Ledger reconciles.** This is the one check specific to this codebase:
   ```sql
   WITH replay AS (
     SELECT variant_id, outlet_id, SUM(quantity_delta) AS ledger
     FROM stock_movements GROUP BY variant_id, outlet_id
   )
   SELECT sl.variant_id, sl.outlet_id, sl.quantity AS cached,
          COALESCE(r.ledger, 0) AS ledger
   FROM stock_levels sl
   LEFT JOIN replay r ON r.variant_id = sl.variant_id AND r.outlet_id = sl.outlet_id
   WHERE sl.quantity <> COALESCE(r.ledger, 0);
   ```
   Zero rows = good. Any row means the dump captured `stock_levels` and
   `stock_movements` at slightly different moments (should not happen with a
   single `pg_dump` transaction, but this is the check that would catch it if
   it somehow did) or the restore was partial.

3. **Smoke test one write in each direction** — a sale, a stock movement, a
   login — before telling anyone the restore is complete.

## What backups do NOT cover

- **Uploaded files** (`backend/uploads/`, product images, logos) live on the
  host filesystem, not in Postgres. Back these up separately (the daily
  script above only dumps the database) — `rsync` or a tarball alongside the
  SQL dump.
- **`.env.prod`** (secrets, `SECRET_KEY`, DB credentials) is gitignored and
  lives only on the host. Losing the host without a copy of this file means
  every existing JWT is invalidated and every password hash is orphaned from
  its salt context in practice terms — keep an encrypted copy off-box.

## Point-in-time recovery

Not configured on any current deployment (`wal_level = replica` /
continuous archiving is off). Recovery today means "restore the most recent
daily dump," with up to 24 hours of loss in the worst case. If that stops
being acceptable at some point — meaning the business, not the code, has
changed — enabling WAL archiving is the next step, not a bigger cron
schedule.
