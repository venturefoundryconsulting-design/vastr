# VPS Deployment (PostgreSQL + FastAPI + React)

Target stack for the VPS, once access is provided. Docker Compose + Caddy —
no manual Nginx/certbot/systemd config, no reverse-proxy workarounds like the
Hostinger deployment needed (that was purely a shared-hosting restriction,
not something that applies here with root access).

## Architecture

```
Internet
  └─> Caddy (ports 80/443, auto Let's Encrypt HTTPS for $DOMAIN)
        ├─ /api/*, /uploads/*  → reverse_proxy → backend:8000 (FastAPI/Uvicorn)
        └─ everything else     → static SPA files (React build) + index.html fallback
                                        │
                                   backend:8000 → db:5432 (Postgres)
```

Three containers: `db` (Postgres), `backend` (FastAPI), `web` (Caddy, also
serves the built frontend directly — no separate Nginx needed).

## Files added for this

- `backend/Dockerfile.prod` — production image (no `--reload`, single worker)
- `frontend/Dockerfile.prod` — multi-stage: builds the SPA, then serves it
  from a Caddy image
- `frontend/Caddyfile` — routing rules (proxy `/api` + `/uploads`, SPA
  fallback for everything else)
- `docker-compose.prod.yml` — orchestrates all three
- `.env.prod.example` — template for the secrets `docker-compose.prod.yml`
  needs (copy to `.env.prod` on the server, never commit that file)

Existing `docker-compose.yml` / `Dockerfile` (no `.prod` suffix) are
untouched — those still drive local dev exactly as before.

## Deploying via git (recommended)

1. Push this repo to a private GitHub/GitLab repo (I don't have `gh` CLI
   access in this environment to create one automatically — create it
   yourself, or give me a remote URL + push access and I'll push it).
2. On the VPS: `git clone <repo-url> && cd <repo>`
3. `cp .env.prod.example .env.prod` and fill in real values:
   - `DOMAIN` — the subdomain/domain this deployment should answer to.
     A **dedicated subdomain** (e.g. `erp.vntr.online`) is simpler than a
     path prefix like Hostinger's `/app` — no base-path config needed, Caddy
     just owns the whole domain. If you want a path prefix instead (to share
     a domain with a future landing page the way the Hostinger deploy did),
     say so and I'll wire `VITE_BASE_PATH`/`VITE_API_URL` back up the same
     way — that support is still in the frontend, just currently defaulted
     to root.
   - `POSTGRES_PASSWORD`, `SECRET_KEY` — generate real random values, e.g.
     `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`
4. Point `$DOMAIN`'s DNS A record at the VPS's IP before starting Caddy — it
   needs to resolve publicly to issue the Let's Encrypt certificate.
5. `docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build`
6. Run the migration: `docker compose -f docker-compose.prod.yml exec backend alembic upgrade head`
7. (Optional, for testing) seed demo data:
   `docker compose -f docker-compose.prod.yml exec backend python -m app.seed`

## Redeploying after a code change

```bash
git pull
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head  # if migrations changed
```

`restart: unless-stopped` on every service means Docker itself restarts
containers on crash and on VPS reboot (as long as the Docker daemon starts
on boot, which is the default on all major distros) — no separate watchdog
or cron job needed, unlike the Hostinger deployment.

## Deploying the multi-tenant (Velora SaaS) conversion to vfcx.tech

`vfcx.tech` is currently running the pre-conversion (single-tenant, Tanisi-
only) code. Phases 1–3, 5, and 6 of the SaaS conversion are complete and
verified locally (see `SAAS_ARCHITECTURE.md`, `SECURITY_REVIEW.md`,
`PERFORMANCE_REPORT.md`) but have **not** been deployed to this VPS — every
verification in this conversion ran against a local dev database, exactly
as agreed before this work started. Deploying to `vfcx.tech` is a separate,
explicit step, not implied by the code being ready. When it's time:

1. **Back up the production database first.** This is not optional — the
   migration touches every table.
   ```bash
   ssh -i ~/.ssh/vfcx_vps root@200.141.14.35
   cd /opt/erpxone
   docker compose --env-file .env.prod -f docker-compose.prod.yml exec db \
     pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > ~/vfcx-backup-$(date +%Y%m%d-%H%M%S).sql.gz
   ```
   Copy that backup off the VPS somewhere durable before proceeding.

2. **Brief maintenance window.** The migration chain (`b0ec8901d716`
   through `02945bbc9a7d` — see `MIGRATION_GUIDE.md` for what each step
   does) should run without the app actively serving writes. For a single
   small-scale tenant this should take seconds, but treat it as a real
   maintenance window, not a hot deploy.

3. **Pull and rebuild:**
   ```bash
   git pull
   docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
   docker compose --env-file .env.prod -f docker-compose.prod.yml exec backend alembic upgrade head
   ```

4. **Smoke-test immediately:** log in as the existing Tanisi admin, confirm
   the dashboard/products/customers/etc. render identically to before (there's
   only one tenant on this instance, so output should be unchanged — if
   anything looks different, that's a signal to stop and investigate before
   doing anything else).

5. **Create the first Super Admin account** (the migration doesn't do this
   automatically — see `MIGRATION_GUIDE.md`'s "Creating a Super Admin
   account" section), using a real, non-demo password.

6. **Rollback path:** if step 4's smoke test fails, restore the Step 1
   backup rather than attempting `alembic downgrade` on a database that's
   already served live traffic on the new schema:
   ```bash
   docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T db \
     psql -U "$POSTGRES_USER" "$POSTGRES_DB" < <(gunzip -c ~/vfcx-backup-*.sql.gz)
   git checkout <previous-commit>
   docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
   ```

Not yet deployed here (and not blocking the above): the Phase 4 tenant
self-service branding UI, feature-flag enforcement, and billing — all
explicitly out of scope for this conversion, see `SAAS_ARCHITECTURE.md`'s
"What's explicitly deferred."

## What's different from the Hostinger deployment

| | Hostinger (backup branch) | VPS (this) |
|---|---|---|
| Database | MySQL/MariaDB (Postgres unavailable there) | PostgreSQL |
| API routing | PHP bridge script (`mod_proxy` blocked) | Caddy `reverse_proxy` (native) |
| Process mgmt | `nohup` + manual cron watchdog | Docker `restart: unless-stopped` |
| TLS | hPanel's managed free SSL | Caddy automatic Let's Encrypt |
| Deploy mechanism | SFTP + SSH exec (no git access practical there) | `git pull` + `docker compose up` |

The full working Hostinger/MySQL state remains on the
`hostinger-mysql-backup` git branch if that platform is ever needed again —
nothing was deleted, just not carried forward on `main`.
