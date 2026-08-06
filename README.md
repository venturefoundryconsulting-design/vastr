# Tanisi ERP — Phase 1

A modular ERP for a multi-outlet fashion retail brand, built to eventually match Odoo's
breadth (CRM, HRM, Accounting to follow in later phases). Phase 1 covers the ERP core:

- **Product & Inventory** — SKUs with size/color variants, barcodes, per-outlet stock
- **Vendors & Purchasing** — vendor master, low-stock reorder suggestions, PO generation,
  PDF invoices, one-click **Send via WhatsApp**
- **Stock Transfers** — inter-outlet transfer requests, dispatch, receipt
- **Point of Sale** — counter billing screen for outlet staff

## Stack

- **Backend**: FastAPI (Python 3.11+), SQLAlchemy 2.0, PostgreSQL, Alembic, JWT auth
- **Frontend**: React + TypeScript (Vite), Ant Design, TanStack Query
- **Deployment**: cloud-hosted, single central database, outlets connect over the browser

## Project layout

```
backend/    FastAPI app (see backend/README.md)
frontend/   React app (see frontend/README.md)
docker-compose.yml   Postgres + backend + frontend for local dev
```

## Quick start (local dev)

```bash
docker compose up --build
```

- Backend API: http://localhost:8000 (docs at /docs)
- Frontend: http://localhost:5173
- Postgres: localhost:5432 (db: `tanisi_erp`, user: `tanisi`, password: `tanisi`)

On first run, apply migrations and seed demo data:

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.seed
```

Demo login: `admin@tanisi.demo.com` / `admin123`

## Roadmap

- **Phase 1 (this repo, in progress)**: ERP core — inventory, purchasing, transfers, POS
- **Phase 2**: CRM — customer profiles captured at POS, loyalty, campaigns, WhatsApp/SMS marketing
- **Phase 3**: HRM — staff records, attendance, payroll, outlet staffing
- **Phase 4**: Accounting — ledgers, GST/tax filing, P&L, balance sheet, bank reconciliation,
  auto-posting from POS sales and vendor bills
