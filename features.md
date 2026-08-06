# Tanisi ERP — Feature Roadmap

Living document: what's implemented vs. what's planned but not built. Update this
whenever a planned item ships, or when new ideas come up that aren't worth building
immediately.

## Reports

### Implemented today
- **Daily Sales** — Sales page (list, filters by outlet/payment mode/date range, export to CSV/XLSX/PDF) + a daily sales-trend chart on the Dashboard
- **Low Stock** — Dashboard widget (count + item list, below each variant's reorder level)
- **Dead Stock** — Reports page tab (no sale in N days, configurable)
- **Slow Moving** (partial) — covered by the Stock Aging tab's bucket breakdown (0-30 / 31-60 / 61-90 / 91-180 / 180+ days since last sale) on the Reports page
- **Payment Mode Report** — Dashboard chart (cash/card/UPI/other breakdown)

### Not yet built
- **Monthly Sales** — a rollup view; only daily granularity exists today
- **Outlet Comparison** — side-by-side sales/performance across outlets
- **Top Customers** — ranked by spend/frequency (per-customer purchase history exists on the Customers page, but no ranked report)
- **Top Products** / **Top Categories** / **Top Brands** — best-sellers by unit/revenue
- **Top Staff** — cashier/staff sales performance ranking
- **Margin Report** — cost price vs. selling price profitability
- **Fast Moving** — inverse of Dead Stock/Stock Aging
- **Sales by Size** / **Sales by Color** — variant-attribute breakdowns
- **Discount Report** — usage and revenue impact of discount rules & coupons (Discounts page manages the rules; no usage report yet)
- **GST Report** — tax summary (GSTIN and HSN codes are already captured and printed on documents, but there's no GST filing/summary report)
- **Hourly Sales** / **Peak Hours** — intraday patterns
- **Customer Frequency** — repeat-purchase interval analysis
- **Loyalty Report** — aggregate view; today loyalty points only have a per-customer ledger (earn/redeem history), no store-wide report

## AI Features

**Not started.** An OpenAI API key can be stored under Settings > Hardware & AI (added
alongside this roadmap) so it's ready to use, but none of these features are wired up
to actually call it yet. Each needs its own design pass when picked up — cost per
call, latency/UX for a retail till, and prompt design all need real decisions, not
just an API key.

- **AI Sales Summary** — morning digest: yesterday's sales, top products, low stock, suggested actions
- **AI Restock Suggestions** — reorder recommendations driven by past sales + season + festival calendar + trend, replacing the static `reorder_level` threshold used today
- **AI Product Description** — upload a product photo → generate description, fabric, care instructions, tags, SEO copy
- **AI WhatsApp Campaign** — e.g. "Generate Diwali sale message" → a ready-to-send campaign draft (would plug into the message composer built for WhatsApp Marketing)
- **AI Customer Insights** — e.g. "Riya usually buys kurtis every 45 days — suggest new arrivals" (would build on the segmentation already used for campaigns)
- **AI Search** — natural-language product search, e.g. "show red kurtis below ₹2000"
- **AI Reports** — natural-language report queries, e.g. "which size sells the most?"
- **AI Photo Tagging** — upload a product photo → auto-detect color, sleeve, neck, fabric, occasion, season

## Employee Module (Simple)

**Explicitly not full HR** — anything beyond the list below (recruitment, performance
reviews, org charts, benefits administration, etc.) is out of scope, that's "full HR,"
which was explicitly ruled out.

### Implemented today
- **Attendance** — self-service check-in/check-out (`/hrm`, "My Attendance" tab, any
  role), one record per staff per day; managers/admins get a "Team Attendance" tab
  filterable by month, plus the ability to manually correct a record
- **Staff Login** — staff already authenticate with real accounts + roles (this *is*
  that item — attendance check-in/out linked to the existing login, not a separate
  system)
- **Leave** — staff submit leave requests (`/hrm`, "My Leave Requests" tab, any role,
  type + date range + reason); managers/admins get a "Leave Approvals" tab to
  approve/reject with a note
- **Salary** — admin sets each staff member's monthly base salary (`/payroll`, admin
  only, "Salary Setup" tab); "Payslips" tab generates one payslip per staff per month
  from that base figure (idempotent - re-running only fills in staff who don't have
  one yet for that month), with editable allowances/deductions and a mark-paid action

### Not yet built
- **Sales Performance** — per-staff sales ranking (would need sales records linked to
  the cashier who rang them up - `Sale.cashier_id` already exists, so the data is
  there, just no report built on it yet)
- **Commission** — percentage-of-sales payout, would build on Sales Performance above
  and feed into the Payslip's allowances
- **Documents** — staff document storage (ID proof, contracts, etc.)
- **Targets** — per-staff or per-outlet sales targets with progress tracking
- **Leaderboard** — gamified ranking view on top of Sales Performance
