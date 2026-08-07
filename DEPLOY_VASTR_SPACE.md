# vastr.space deployment (shared VPS with vfcx.tech)

`vastr.space` and `vfcx.tech` (the older single-tenant deployment, a
separate `erpxone` repo/checkout) run **on the same VPS** (`200.141.14.35`)
and share **one IP** via name-based virtual hosting - one Caddy instance owns
ports 80/443 and routes by domain (SNI/Host header) to two completely
independent backends. No second IP was needed.

## Architecture

```
Internet
  └─> shared-web (Caddy, ports 80/443, one cert per domain via Let's Encrypt)
        ├─ vfcx.tech    → erpxone-backend-1:8000 (api/uploads) + /srv/vfcx-tech (static)
        └─ vastr.space  → vastr-backend-1:8000   (api/uploads) + /srv/vastr-space (static)

/opt/erpxone   - existing erpxone stack (db, backend) - UNTOUCHED, own compose project
/opt/vastr     - this repo, checked out at /opt/vastr - own compose project (db, backend)
/opt/shared-web - the shared Caddy's Caddyfile + both domains' built static files
```

Each app still has its **own isolated Postgres** (`erpxone-db-1` / `vastr-db-1`,
separate containers, separate volumes, separate credentials) - only the outer
web/TLS layer is shared. `erpxone-backend-1` and `erpxone-db-1` were never
touched by this deployment; the only thing that changed for vfcx.tech is
which container terminates its HTTPS traffic (previously a dedicated
`erpxone-web-1` Caddy, now `shared-web`) - same reverse-proxy behavior,
same static files.

Both `/opt/vastr`'s `db`/`backend` containers and the standalone `shared-web`
container are attached to the `erpxone_default` docker network (created by
`/opt/erpxone`'s compose project) purely so `shared-web` can reach
`vastr-backend-1` by container name - `erpxone-backend-1` and `erpxone-db-1`
were never modified or restarted to make this work.

## Redeploying vastr.space after a code change

```bash
cd /opt/vastr
git pull
docker compose --env-file .env.prod -f docker-compose.prod.yml build backend web
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d backend   # db rarely needs restarting
docker compose --env-file .env.prod -f docker-compose.prod.yml exec backend alembic upgrade head   # if migrations changed

# Static frontend isn't served by its own container - shared-web serves it
# directly from /opt/shared-web/sites/vastr-space, extracted from the built
# `web` image:
docker rm -f vastr-web-tmp 2>/dev/null
docker create --name vastr-web-tmp vastr-web
rm -rf /opt/shared-web/sites/vastr-space
docker cp vastr-web-tmp:/usr/share/caddy /opt/shared-web/sites/vastr-space
docker rm vastr-web-tmp

# IMPORTANT: shared-web's bind mount goes stale if the host directory it
# points at gets rm -rf'd and recreated while it's running (the mount
# doesn't follow the new inode) - always restart it after replacing static
# files, or the site 404s despite the files being correct on disk:
docker restart shared-web
```

## Where things live

- `/opt/vastr/.env.prod` - `DOMAIN=vastr.space`, its own `POSTGRES_*` /
  `SECRET_KEY` (all freshly generated for this deployment, unrelated to
  erpxone's), `chmod 600`, gitignored, never committed.
- `/opt/shared-web/Caddyfile` - the two site blocks (vfcx.tech, vastr.space).
  Not part of either git repo - lives only on the server.
- `/opt/shared-web/sites/vfcx-tech` and `/opt/shared-web/sites/vastr-space` -
  extracted static builds, bind-mounted read-only into `shared-web`.
- Super Admin login: `admin@vastr.space` - created directly via a one-off
  script (see `MIGRATION_GUIDE.md`'s "Creating a Super Admin account"), not
  via `python -m app.seed` (that also seeds fake Tanisi demo data, which a
  fresh production SaaS platform shouldn't have).

## If vfcx.tech ever needs its own IP again

Nothing here is hard to unwind: stop `shared-web`, restore a dedicated Caddy
container for `erpxone` on 80/443 (same Caddyfile/image it used before), and
either give `vastr.space` its own IP or repeat this same shared-Caddy setup
with a different partner domain. Both apps' actual data (Postgres volumes,
uploaded files) are untouched by any of this either way.
