# Manufacturing Core — Architecture Decisions & Build Spec

Companion to the full architecture document (diagrams, ER model, permission matrix,
roadmap): **https://claude.ai/code/artifact/07e297e5-51f3-4ede-b105-624a4e3a1e7e**

This file is the version-controlled record of *decisions and enforcement points*.
It is what you implement against; the artifact is what you review and share.

Prepared against `main` @ `899fcb5`.

---

## 0. The governing decision

Build the manufacturing layer **as an extension of this codebase**, not as a new one.

Already working here, and therefore not rebuilt: JWT auth, 8-role RBAC catalogue,
tenant isolation (`TenantMixin` + auto-filter), audit log, outlets-as-locations,
vendors + vendor-item links, purchase orders with partial receipt, POS/sales/returns/
transfers, HRM/payroll, and an **immutable `stock_movements` ledger whose mutations
already take `SELECT … FOR UPDATE`** (`app/services/inventory.py`).

That covers the original spec's Phase 1, most of Phase 2, Phase 4 and Phase 7.

Genuinely missing: item typing, units of measure, BOM, production orders,
reservations, work orders, tailors, wastage, QC, MRP, costing.

UI stays **antd** — matching the existing 22 pages. No Tailwind/shadcn migration.

---

## 1. Migration sequence (order is not negotiable)

### Step 1 — widen quantities, alone, in its own deploy — ✅ DONE (`ec27aa62e12f`)

Shipped. 10 columns across 6 tables are now `NUMERIC(14,4)`. Money arithmetic moved
to `Decimal` at the same time because `float(x) * Decimal(y)` raises `TypeError` —
see `app/core/money.py` and `app/schemas/fields.py`. 40 tests in `backend/tests/`.

Two things worth knowing before Phase 2:

- **`ALTER TYPE int -> numeric` rewrites the table** under an `ACCESS EXCLUSIVE`
  lock. Not non-blocking. Maintenance window, app stopped.
- **The ledger-replay property does not hold on seeded data**, because
  `app/seed.py` writes `StockLevel` rows directly for opening stock without a
  matching `stock_movements` row. Pre-existing, unrelated to the migration, but
  Phase 3 must introduce an `OPENING_STOCK` movement type and backfill before
  anything relies on replay being authoritative.

Every quantity in the system is currently `Integer`. Manufacturing needs 4.5 m of
silk, 200 g of thread, 0.5 m of wastage.

| Table | Columns |
|---|---|
| `stock_levels` | `quantity` |
| `stock_movements` | `quantity_delta` |
| `purchase_order_items` | `quantity_ordered`, `quantity_received` |
| `sale_items`, `return_items`, `transfer_items` | quantity columns |

`Integer` → `Numeric(14, 4)`. Widening is lossless and does not rewrite the table in
Postgres, but it touches the ledger hot path, POS and transfers simultaneously.

**Ship nothing else in this migration.** It needs its own rollback.

**Done when:** a sale, a transfer and a receipt still balance, and replaying the full
ledger reproduces every `stock_levels.quantity` exactly.

### Step 2 — `items` supersedes `product_variants` — ✅ DONE (`a335a21c1c40`)

**Correction to the original plan.** This section previously said to create a new
`items` table and keep `product_variants` as an updatable view. That is not
possible: **PostgreSQL cannot use a view as the target of a foreign key**, and
eight tables hold FKs to `product_variants.id` —

    stock_levels, stock_movements, sale_items, return_items, exchange_items,
    stock_transfer_items, purchase_order_items, vendor_products

That route would have meant dropping all eight constraints and permanently losing
referential integrity over the sales history.

**What shipped instead:** `ALTER TABLE product_variants RENAME TO items`. Postgres
carries FK constraints through a rename, so all eight kept pointing at the same
physical table under its new name — every id, sale and stock level valid, no row
copied. A read-only `product_variants` **view** was then created for external SQL
that hardcodes the old name; the ORM maps straight to `items`.

In code, the class is `Item` with a module-level `ProductVariant = Item` alias, so
all 68 pre-Phase-2 references still resolve. `product_id` is now nullable (a bolt
of silk is not a variant of a garment), and the descriptive fields were backfilled
from the parent product so items are self-describing either way.

UoM: `uom_categories` + `units_of_measure` (each unit carries `factor_to_base`, so
same-category conversion needs no lookup table) + `item_uom_conversions` for
packaging rules, which *may* cross dimensions and may be vendor-specific.

### Step 3 — Phase 3A: opening stock + ledger integrity — ✅ DONE (`63a36eea9b05`, `078d64dd5db5`)

`OPENING_STOCK` is now a first-class `MovementType`, and every opening balance that
had been written straight onto `stock_levels.quantity` has a matching ledger row.

The backfill computes, per stock level:

    drift = stock_levels.quantity - COALESCE(SUM(stock_movements.quantity_delta), 0)

and writes one `OPENING_STOCK` movement for any non-zero drift. Because the drift is
measured *after* summing existing movements, real history cannot be double-counted;
a level that already reconciled gets no row. Re-running finds zero drift, so it is
idempotent. The migration asserts reconciliation before committing and raises rather
than leave a half-corrected ledger.

`app/seed.py` now routes opening balances through `apply_stock_delta` — the source
of the original drift is closed, not just its symptoms.

**The invariant is now a permanent test** (`tests/test_ledger_integrity.py`):

    for every (variant, outlet):
        stock_levels.quantity == SUM(stock_movements.quantity_delta)

If a future change breaks it, the fix is to route the offending write through
`apply_stock_delta` — never to relax the assertion. One test deliberately bypasses
the service and asserts the guard catches it.

### Still to do before BOM/production

- `stock_levels.reserved_qty numeric(14,4) DEFAULT 0`
- `outlets.location_type` enum, existing rows default `shop`

## Phase 3B — Bill of Materials — ✅ DONE (`306442d89ecb`)

`boms` → `bom_versions` → `bom_components` → `bom_component_substitutes`.

**Naming**: the line table is `bom_components`, not `bom_items`. The house
convention is `<doc>_items`, but `items` is the Item Master since Phase 2, so
`bom_items` would read as "items that are BOMs".

**Versioning / historical integrity.** A version is immutable the moment it leaves
`DRAFT`; `is_locked` (set when production first uses it) is the harder stop and
survives archiving. "Editing" an active BOM means creating a new version, which
copies the current lines forward. Production therefore references a **version**,
never the mutable header — `production_order.bom_version_id` alone reproduces the
recipe exactly, because that row cannot have changed.

**One ACTIVE version per BOM** is a partial unique index
(`uq_bom_one_active_version ... WHERE status = 'ACTIVE'`), not an application
check, so two concurrent activations cannot both win.

**Quantity semantics.** `quantity` = expected **net consumption**. `scrap_pct` is
additional expected loss. Planned issue = `quantity × (1 + scrap_pct/100)`; the
stored quantity is never rewritten, so planned-vs-actual stays answerable. 8 m at
5% ⇒ recipe still reads 8 m, requirement is 8.4 m.

**Scaling.** `required = quantity × (requested / version.output_quantity) × (1 + scrap%)`.
`output_quantity` is explicit, so a BOM whose batch yields 2 panels is expressible.

**Multi-level.** A component with its own ACTIVE BOM is recursed into; leaves are
raw materials. Sub-assemblies are reported too (flagged `is_subassembly`) but not
costed, to avoid double-counting their children. Cycles are rejected by walking
the candidate's subtree for the parent before insert, plus a depth cap of 20.

**Substitutes are inert.** Listed, never auto-swapped. What was actually used gets
recorded against the production order in 3D — that record, not this table, drives
costing and traceability.

**Cost source.** `items.cost_price` (standard cost), *not* vendor price — a BOM
estimate must be stable and supplier-independent; which of three lace vendors wins
the order is a later procurement decision. Line costs convert into the component's
UoM, so a line in centimetres is costed per centimetre.

**Duplicates** are reported, never merged: two lines of the same lace may carry
different notes or substitutes.

**UoM** uses the Phase 2 engine unchanged — no BOM-specific conversion logic.

### BOM Builder UI

`/boms` (list) and `/boms/:id` (builder). Built for 100–500+ component recipes.

**Virtualization is the load-bearing decision.** The grid uses antd's `virtual`
Table, so only the ~20 visible rows mount. That is what makes a per-row unit
selector affordable at 500 rows — without it, 500 mounted `Select`s would make
the page unusable, and the alternative (read-only cells with a separate edit
dialog) would be far slower to actually work in.

**One shared item picker, not a dropdown per row.** Search runs server-side
against SKU, barcode and name, debounced at 250 ms, and adds many materials at
once — which matches how a BOM is really built ("find six trims, add them all,
then set quantities").

**The grid is local state; the server is written once.** Component edits never
round-trip per keystroke; `Save draft` sends the whole list to
`PUT .../components`. Saving 500 rows is one API call. There is no autosave — an
explicit save with a visible `Unsaved changes` tag was preferred over silently
writing drafts a user is still mid-thought on.

**Money is never computed in the browser.** The cost panel renders whatever
`GET /boms/{id}/cost` returned (Decimal, server-side). While the grid is dirty it
says so and offers to refresh after saving, rather than showing a JS-float
estimate that would disagree with the backend.

**Validation is inline and continuous** — zero/negative quantity, missing unit,
out-of-range wastage, inactive item, non-stocked item, duplicated material,
cross-dimension unit. Cross-dimension units are a *warning*, not an error: the
frontend cannot see item-level packaging conversions, so the backend stays
authoritative and the UI never blocks something the server would accept.

**Bulk paste** accepts tab- or comma-separated rows from Excel/Sheets
(`name-or-SKU, qty, unit`), matching SKU then barcode then a unique name. An
ambiguous name is reported, never guessed. A preview table shows what matched
before anything is added.

**Version comparison** diffs two versions into added / removed / quantity / uom /
wastage / substitutes.

**Unsaved-change protection**: `beforeunload` for tab close/reload, and a confirm
dialog on the in-page actions that leave (back to list, switching version).
*Known gap*: this app uses a non-data React Router, so `useBlocker` is
unavailable and sidebar navigation away from the builder is not intercepted.

## Phase 3C — Production Orders + Material Availability — ✅ DONE (`365d917819aa`)

**Phase 3C is planning only, and read-only with respect to inventory.** Creating,
planning, releasing, starting, cancelling or short-closing a production order —
and every availability calculation — leaves `stock_levels` and `stock_movements`
byte-identical. Neither `services/production.py` nor `routers/production_orders.py`
imports `apply_stock_delta`; a test asserts the invariant by hashing inventory
around the whole lifecycle. Reservation and physical movement are Phase 3D.

### Lifecycle

    DRAFT ──▶ PLANNED ──▶ RELEASED ──▶ IN_PROGRESS ──▶ PARTIALLY_COMPLETED ──▶ COMPLETED
      │          │            │              │                                      
      ▼          ▼            ▼              ▼                                      
   CANCELLED  CANCELLED   ON_HOLD       CLOSED_SHORT                                

`ON_HOLD` remembers where it was entered from (`resume_status`) so Resume is
unambiguous. `COMPLETED`, `CANCELLED` and `CLOSED_SHORT` are terminal.

**Status is never a settable field.** Every change goes through a transition
endpoint that validates against `ALLOWED_TRANSITIONS` server-side, so a client
cannot PATCH its way to COMPLETED. Invalid transitions return 409 naming what is
actually reachable.

**Closing short is never implicit**: produced quantity and reason are both
mandatory in the schema, and the order records who decided and when.

### BOM reference and snapshot

An order references a **version**, and Phase 3B guarantees a version is immutable
once it leaves DRAFT — so the FK alone reproduces the recipe. The snapshot in
`production_order_materials` exists for different reasons: multi-level explosion
is expensive to recompute, Phase 3D needs somewhere to hang reserved/issued/
consumed per material, and per-order deviations need a home that is not the BOM.

The snapshot rebuilds while DRAFT/PLANNED (so changing quantity re-derives it) and
**freezes at RELEASED**. Releasing also sets `bom_version.is_locked` — the flag
Phase 3B defined and left for whoever first consumed a version.

### Requirement calculation

    required = component.quantity
             × (order_quantity / bom_version.output_quantity)
             × (1 + scrap_pct / 100)

Base, expected wastage and planned issue are stored as three separate columns, so
"we planned 80 m and expected to waste 4" stays answerable afterwards. 8 m at 5%
× 10 units ⇒ base 80, wastage 4, planned issue 84.

### Availability

    available = on_hand − reserved

Not on-hand alone: material can physically exist while already committed
elsewhere. Reservations arrive in 3D, so `_reserved_by_item` returns empty today
— it exists as a seam so the arithmetic is written correctly *now* and 3D only
fills in the query. A test pins the rule by stubbing it (20 on hand, 15 reserved,
10 required ⇒ available 5, short 5).

Per material: `AVAILABLE` / `PARTIAL` / `SHORT` / `NOT_STOCKED` / `INVALID`.
Per order: `READY` / `PARTIAL_MATERIAL` / `MATERIAL_SHORTAGE` / `INVALID_MATERIAL`.

**A shortage never blocks creation or release** — a boutique legitimately plans a
run before the lace arrives. It is reported prominently, not enforced.

### Multi-level explosion

Sub-assemblies are recursed into and reported (flagged `is_subassembly`) but
excluded from material totals, because their own children are already listed.
10 lehengas → 10 blouses → 20 m fabric; never 30 of anything. A repeated material
is aggregated across lines and levels before comparing to stock, or each line
looks satisfiable while the order as a whole is short.

### Traceability

`GET /production-orders/{id}/trace/{item_id}` answers "why do I need 45 m of
silk?" as an explicit chain — order quantity → BOM version → per-unit → required —
walking back up through each parent on multi-level orders.

### Performance

The naive approach (re-explode, then resolve each row's item/stock/unit) is O(n)
queries per component. Everything batch-loads instead: `_BomTree` pulls every
active version and its components in two queries, then items, stock and units in
one each. A test asserts a 200-component order costs **< 20 queries**; N+1 would
be ~600.

### Permissions

Eight `production.*` codes, all gated with `require_permission` — never the
admin/manager/staff rank ladder. INVENTORY and VIEWER get `production.view` only.

### Audit

Every transition writes to the shared `audit_logs` with from/to/reason, surfaced
at `GET /production-orders/{id}/history`.

## Phase 3D — Reservation / Issue / Consumption / Return — ✅ DONE (`671325591073`, `debaf64667ce`)

**Four quantities, four meanings, never collapsed:** on hand, reserved, issued,
consumed. Only **issue** and **return** move physical stock.

    Reservation  does NOT change physical inventory — it is a promise.
    Consumption  does NOT deduct stock again — it already left at issue.
    Return       creates a compensating movement — the issue is never edited.

### Concurrency strategy

Every mutating operation takes **the same lock**: the `stock_levels` row for
(item, location), via the ledger's existing `SELECT … FOR UPDATE`. One lock
serializes reserve-vs-reserve, reserve-vs-issue and issue-vs-issue, because all
three reason about the same scarce thing. A second locking scheme over the same
rows is how deadlocks get in.

The sequence is always: **lock → re-read the position from the database →
validate → write → let the caller commit.**

The re-read is the part that is easy to omit and expensive to get wrong. A
`material` loaded before the lock carries whatever the transaction saw at load
time; validating against it means two concurrent callers each read "0 consumed"
and each decide their request fits. `_lock_and_refresh` exists for exactly this —
**and the concurrency tests caught a real bug here**, where consume and return
were validating against stale in-session values while reserve and issue happened
to be safe by re-querying reservations.

### Where truth lives

The three transaction tables (issues, consumptions, returns) plus
`stock_reservations` are immutable history. The four aggregate columns on
`production_order_materials` are a **cache** over them, maintained in the same
transaction under the same lock — the same relationship `stock_levels` has with
`stock_movements`. A test asserts cache == sum(transactions).

### Invariants

    reserved  <= available_at_location          (= on_hand − reserved elsewhere)
    issued    <= reserved                        (unless materials.issue_unreserved)
    issued    <= planned                         (no silent over-issue)
    consumed + returned <= issued
    returnable            = issued − consumed − returned
    still_with_production = issued − consumed − returned

`still_with_production` is exposed explicitly: at the end of a run it is what is
sitting in a tailor's tray.

### Release

Releasing a reservation frees only the **unissued** portion — issued material has
physically gone and comes back through a return, not by withdrawing a promise.
Cancel and close-short both release all outstanding reservations (Rule 8).

### Material custody

Tailors remain resources, not stock locations. Material issued to production is
attributed to the production order, material line, user and location — no fake
transfers to per-tailor locations. Work-order-level attribution stays additive.

### Permissions

Seven `materials.*` codes. **`materials.issue_unreserved` is granted to no role,
not even admin** — it bypasses the commitment model, so it is opt-in per
deployment rather than inherited by being powerful.

## Phase 3E — Production Output + Partial Production — ✅ DONE (`a55cf911332c`, `2a381270b1ed`)

`PRODUCTION_OUTPUT` is the mirror of `PRODUCTION_ISSUE`: finished goods enter
stock through the same `apply_stock_delta` chokepoint, so a garment in inventory
is as explainable as the fabric that left.

**Partial production never auto-closes.** Below plan the order becomes
`PARTIALLY_COMPLETED` and stays there; stopping short is a decision made through
close-short, which records who and why. Reaching the planned quantity *does*
complete the order — nothing is being abandoned, so there is no judgement to
record. The rule protected is "never silently close **short**".

## Phase 3F — Tailors + Work Orders — ✅ DONE (`9531a69e270c`, `08d4b540a2c4`)

`tailors`, `tailor_skills`, `production_stages`, `work_orders`. The nine default
stages are **seeded as data** — nothing branches on a stage code, so a boutique
can add "Beading" without a release.

**Tailors are resources, not inventory locations** — asserted by a test that no
stock table carries a FK to `tailors`. Material custody stays with the production
order; there are no fake transfers to per-tailor locations.

**The `TAILOR` role sits outside the rank ladder** deliberately: a tailor outranks
nobody yet needs write access to their own work orders, which rank checks cannot
express. It holds exactly `work_orders.own` + `materials.view` (+ `qc.view`,
`wastage.record` from 3G). `/work-orders/mine` resolves the tailor **from the
authenticated user**, never a query parameter.

Pay terms are **frozen onto the work order at assignment**, so raising someone's
rate never rewrites what past work cost.

## Phase 3G — QC + Rework + Wastage — ✅ DONE (`5c2cf0b20b23`)

Defect categories and wastage reasons are configurable tables, so reports group
on a stable id rather than free text.

**Rework stays on the original production order** — no duplicate order, so the
fault stays linked to the run and output is not counted twice. A failed check
re-opens the completed work order into `REWORK`.

**Wastage writes no ledger row.** The material left at issue; deducting again
would double-count. What wastage adds is the reason, the attribution and the cost.
It is kept separate from consumption because consumed material became product and
wasted material did not — collapsing them would destroy the variance signal.

Material now reconciles as:

    issued = consumed + wasted + returned + still_with_production

## Phase 3H — Production Costing + Reports — ✅ DONE (`a7b6b501c16a`)

    Material cost + Labour cost + Wastage cost = Production cost

**Permissions only — no new tables.** Cost is derived entirely from the
requirement snapshot, consumption, wastage and work orders. Persisting it would
create a second source of truth that drifts the moment a rate changes.

**Estimated and actual are never back-filled from each other.** Estimated prices
the BOM requirement at standard cost (the same way Phase 3B costs a BOM, so the
two screens never disagree); actual prices real consumption and completed labour.
The variance between them is the number that tells a boutique whether its BOM is
honest — so an over-consumption never quietly rewrites the recipe.

Unit cost is `None` until something is produced, rather than a division by zero
dressed up as a number.

Reports: manufacturing summary, wastage by material, tailor productivity (priced
at the frozen rates, so the report does not move when a rate changes).


## Phase 4 — Made-to-order + POS integration — ✅ DONE (`a6a0ec63719a`)

Five tables: `measurement_fields`, `measurement_profiles`, `measurement_values`,
`customer_orders`, `customer_order_items`.

### Measurements are data, not columns

Bust, waist, sleeve and the rest are rows in `measurement_fields`, seeded with ten
defaults and extensible from the API. Nothing in the application branches on a
measurement code. A customer holds **several named profiles** ("Bridal 2026",
"Blouse") because one person is not one set of numbers, and a re-measure creates a
new profile rather than overwriting the one an existing garment was cut to.

Values are `Numeric`, not text, so a tailor can see that a waist moved 30 → 31.5.

### Ready stock and made-to-order on one order

Both line types live on the same `customer_order`. A customer buying a dupatta off
the rack and commissioning a lehenga in the same visit is one transaction to them;
splitting it would make the boutique reconcile two documents by hand.

Confirming spawns **one production order per made-to-order line**, in `DRAFT` —
confirming is a commercial decision, releasing material is a production one.
Ready-stock lines spawn nothing. Re-confirming is refused by the state machine
rather than silently duplicating a run.

    DRAFT ──▶ CONFIRMED ──▶ IN_PRODUCTION ──▶ READY ──▶ DELIVERED
      │           │               │             │
      └───────────┴───────────────┴─────────────┴──▶ CANCELLED

### Delivery reuses the POS — no parallel sales path

`/customer-orders/{id}/deliver` builds an ordinary `SaleCreate` and calls
`sales.checkout` — the same function the counter uses. That is what validates
stock, writes the `SALE` ledger row, applies loyalty and produces the receipt. A
made-to-order garment therefore leaves inventory by exactly the same path as an
off-the-rack one, and its history reads `PRODUCTION_OUTPUT` then `SALE`.

The advance already taken is passed as a discount so the customer is charged only
the balance, not billed twice.

**Consequence worth knowing:** because delivery is a real POS sale, *automatic
discount rules apply to it*. Verified live — a seeded "10% Off Everything" rule
took a further ₹4,700 off a ₹47,000 commissioned order at handover. That may be
wanted or not; if a negotiated made-to-order price should be exempt from blanket
promotions, that is a rule-scoping decision, not a code change.

Cancelling a customer order cancels the production it spawned, which is what
releases those material reservations (Rule 8 reaching through from the counter).

### Permissions

Seven codes. Counter staff (`OUTLET_STAFF`) can take orders, record measurements
and hand orders over — but **not confirm**, because confirming commits material.



## Phase 5 — Goods Receipts + Purchase Returns — ✅ DONE (`72407fc6ffda`, `7b08953711f7`)

Rule 2 ("only receiving increases inventory") made auditable. Receiving used to
be a quantity nudged onto `purchase_order_items.quantity_received` with no
document, date or receiver. `services/goods_receipt.py::post_receipt` is now the
**only** writer of `PURCHASE_RECEIPT`.

### Units and cost, not just a document

A receipt is counted in the vendor's unit and converts into the item's stock
unit through the Phase 2 engine — 2 ROLL of lace at 25 m/roll lands as 50 M.
Verified live. Weighted-average cost recalculates on every posting and is
stamped onto the ledger row itself (`stock_movements.unit_cost`, new nullable
column) — carrying it per movement, not only on the item, is what would let FIFO
be added later without reconstructing history from invoices.

### Draft, then post

A receipt can be drafted (counted, priced, checked) before it touches stock;
`post_receipt` is the one moment inventory moves, and posting twice is refused.
A posted receipt is immutable — corrections go through a purchase return, never
an edit.

### Purchase returns are compensating, never edits

`post_return` writes a negative `PURCHASE_RETURN` movement referencing the
receipt; the receipt itself is untouched. Bounded by two independent limits —
`returnable = received − already returned` **and** physical stock on hand — the
tighter of which wins. Live-verified: returning 45 of a line with 50 received and
10 already returned is correctly capped and refused at "at most 40".

**Bug found and fixed during testing**: `returnable()` originally summed a
return's own not-yet-posted line against its own limit, understating what could
go back by exactly that line's quantity. Fixed by excluding the line being
validated from its own sum; caught by `test_return_cannot_exceed_what_was_received`
before it shipped.



## MRP — Material Requirement Planning — ✅ DONE (`b2edd6ef4b33`)

**Stateless by design.** Every earlier manufacturing table records something
that happened. MRP records nothing — `services/mrp.py::requirements` computes
its answer fresh from `production_order_materials`, `stock_levels` and
`stock_reservations` on every call. There is no MRP table to go stale, and no
migration beyond two permission codes.

### What counts as demand

Only material lines on production orders in `RELEASED`, `IN_PROGRESS` or
`PARTIALLY_COMPLETED` — a `DRAFT` order is a plan nobody committed to, and MRP
must not count it. Only the **outstanding** portion, `planned − issued`, so
material already pulled to the floor stops counting as something to buy.
Sub-assembly lines are excluded, matching Phase 3C's availability calculation.
Two orders needing the same lace aggregate correctly — verified live at
2 orders × 8 m = 16 m required, not double-counted or dropped.

### What counts as supply

`on_hand − reserved`, aggregated per item across every open reservation, the
same formula Phase 3D established for one order extended across all of them.

### Never automatic

`generate_draft_purchase_orders` is the one function that writes anything, and
what it writes is a `DRAFT` purchase order — inert until a human reviews,
prices and sends it. It refuses outright if any requested item has no preferred
vendor, rather than guessing one. Suggested quantity rounds up to the vendor's
`min_order_qty` only when the MOQ exceeds the shortage; a shortage larger than
the MOQ is never rounded down. Verified live: generating a draft PO wrote zero
stock movements — 70 before, 70 after.


## Frontend — 3E through 5H + MRP — ✅ DONE

Every phase above shipped backend-first with API-level verification only. This
batch is the UI catch-up: it puts a screen in front of everything that was
previously curl-only.

**New API surface.** `api/manufacturing-types.ts` and
`api/manufacturing-endpoints.ts` hold types/functions for the phases that had
no prior frontend surface — output, workforce, quality/costing, MRP, goods
receipts, made-to-order. Material flow (Phase 3D — reservation/issue/
consumption/return) already had a complete implementation
(`components/MaterialFlowPanel.tsx`, backed by `api/types.ts` /
`api/endpoints.ts`) discovered mid-build; it was deliberately **not**
duplicated into the new files. One real gap was patched into the existing
`api/types.ts` instead: `MaterialPosition` was missing the `wasted` field the
backend already sent.

**New components** (mounted as tabs inside `ProductionOrderDetail`, alongside
the existing materials tab): `ProductionOutputPanel` (record output, shows
produced/remaining, surfaces "Complete" once the plan is met),
`QualityPanel` (checks + rework, raise rework from a failed check),
`WastagePanel` (record wastage, running cost total), `ProductionCostPanel`
(estimated vs actual, material lines, labour lines).

**New pages**, each thin over the state machine the backend already enforces
— none of them re-implement `ALLOWED_TRANSITIONS` client-side, they render
whatever `allowed_transitions` the API returns:
- `Tailors.tsx` / `WorkOrders.tsx` — manager-side roster and floor-wide work
  order table with inline tailor assignment
- `MyWork.tsx` — a tailor's own queue, scoped server-side to the caller,
  polling every 30s; Start/Pause/Complete/Report issue/Cancel
- `CustomerOrders.tsx` / `CustomerOrderDetail.tsx` — made-to-order intake with
  per-line ready-stock vs made-to-order fulfilment, readiness tracking,
  Confirm/Mark ready/Deliver/Cancel gated on `allowed_transitions`
- `GoodsReceipts.tsx` — draft-then-post receipts (stock does not move until
  posted), expandable rows showing vendor-unit vs stock-unit quantity and
  unit cost, purchase returns capped at what remains returnable
- `Mrp.tsx` — requirements table with row selection, "Generate draft purchase
  order(s)" disabled unless a shortage exists and an outlet is chosen; states
  plainly in the UI that nothing is committed automatically

**Navigation.** `Layout.tsx` gained a new "Manufacturing" nav group (Tailors,
Work Orders, Material Planning) plus `/customer-orders` and `/my-work` under
Sales and `/goods-receipts` under Procurement — all seven new routes were
previously reachable only by typing the URL.

**Verification.** `tsc -b` and `npm run build` both clean (2,355 kB main
bundle, pre-existing chunk-size warning, unrelated to this batch). Backend
suite reconfirmed at 339 passed / 1 skipped (frontend-only change, as
expected, nothing moved). Unlike every prior phase, this one *was* visually
verified — logged in through the actual login page and clicked through all
seven new routes plus all five ProductionOrderDetail tabs in the browser
preview, against live seeded data: Tailors, Work Orders, MRP shortages,
Goods Receipts (including its Return action), Customer Orders list and
detail (a delivered order showing both fulfilment types), My Work's empty
state, and Materials/Output/Quality & rework/Wastage/Cost all rendered
correctly with real numbers.


## Architectural decisions on record

**1. Tailors do not own inventory locations.** A tailor is a resource (an employee
with skills and a rate), not a stock location. Material issued to production moves to
a shared production location, not to a per-tailor one. This avoids a scanning burden
the boutique has not asked for, and per-tailor locations remain purely additive if
material custody per tailor ever becomes a real requirement.

**2. Partial production stays open until explicitly resolved.** An order for 10 that
produces 6 goes to `PARTIALLY_COMPLETED` with `ordered / produced / remaining` tracked;
it does **not** auto-close. Closing short is a deliberate action recording quantity
cancelled, reason, user and timestamp. Silent short-closing would quietly destroy the
variance signal that makes production planning improvable.

Both are revisable if the business contradicts them — deliberately, not by drift.

---

## 2. Enforcement points for the business rules

The original spec's §69 rules are only real if they live at a chokepoint. These are
the chokepoints:

| Rule | Enforced where |
|---|---|
| 2 — only receiving raises stock | `POST /api/v1/goods-receipts` is the **sole** writer of `purchase_receipt` ledger rows. PO endpoints must not touch stock. |
| 3 — creating a production order consumes nothing | `production_orders` creation writes no ledger row and no reservation. Status starts `draft`. |
| 4 — reservation reduces available, not physical | `stock_reservations` rows + cached `reserved_qty`. **No ledger row is written.** `available = quantity − reserved_qty`, always derived. |
| 5 — consumption reduces physical stock | `POST /production-orders/{id}/consume` → `material_consumptions` row → `apply_stock_delta`. |
| 6 — completion outputs stock | `POST /production-orders/{id}/complete` → positive ledger row for the produced item. |
| 8 — cancel releases reservations | `POST /production-orders/{id}/cancel` sets every `active` reservation to `released` in one transaction. |
| 10 — every change has a transaction record | **`apply_stock_delta` is the only function permitted to mutate `stock_levels`.** Add a test that greps for direct `stock_levels` writes outside it. |
| 11 — AI needs human confirmation | `ai_import_rows` → `POST /ai/import-jobs/{id}/approve` is the only path to master data. |
| 12 — used BOM versions are immutable | `bom_versions.is_locked` set on first production-order reference; enforced by DB trigger, not app code alone. |

### Concurrency invariant

Every stock mutation, in one transaction, in this order:

```
SELECT … FOR UPDATE on stock_levels
  → validate resulting balance (refuse negative)
  → INSERT stock_movements
  → UPDATE stock_levels
```

**Reservations must take the same lock**, or two production orders will both reserve
the last 4.5 m of silk. This is the single most likely correctness bug in the module.

---

## 3. Decisions taken (and why)

**Reservations are rows, not a counter.** A counter cannot be aged, released
selectively, or explained to a user. Rows make Rule 8 a status update rather than
arithmetic, and give the shortage report something to link to.

**Snapshot the BOM at release; don't just reference it.** `production_order_materials`
copies the BOM lines when the order is released. The FK to `bom_version_id` is kept for
provenance, but planned quantities live on the snapshot. A recipe can then evolve
without rewriting history.

**UoM conversions are item-specific.** `1 kg = 1000 g` is global (`uom_conversions`).
`1 box = 500 stones` is true only of that item, sometimes only from that vendor
(`item_uom_conversions`, with nullable `vendor_id`). Resolution order:
vendor-specific → item-generic → global. Conflating these is how a manufacturing
inventory silently goes wrong — one vendor's roll is 25 m, another's is 50 m.

**Weighted average cost, FIFO-ready.** `items.moving_avg_cost` recalculated on each
receipt. Additionally write `unit_cost` onto **every ledger row** — it costs nothing
now and is the only thing that makes FIFO addable later without a backfill.

**Negative stock is refused,** with a `409` carrying the numbers:

```json
{ "code": "INSUFFICIENT_STOCK", "item": "Gold Lace 2\"",
  "requested": 10, "on_hand": 6, "reserved": 2, "available": 4, "uom": "m" }
```

Never a bare 500 for a predictable business condition.

**Cycle detection is mandatory.** Multi-level BOMs allow A → B → A. The explosion
service walks with a visited-set and a depth cap; adding a BOM line rejects a component
whose own tree already contains the parent.

**Batch tracking deferred, not designed out.** `batch_id` stays nullable on ledger rows
so dye-lot tracking can be enabled per item later with no migration.

**No Redis/Celery until Phase 9.** Nothing in Phases 1–8 outlives a request, and the
existing campaign scheduler already covers deferred sending. Adding them earlier is
infrastructure to operate with no work to do.

---

## 4. Still open — needs a call from the business

**Does a tailor hold stock?** Either issuing moves material to a per-tailor location
(accurate wastage attribution, more scanning) or to one shared production floor.
Recommend the shared floor first; per-tailor locations are purely additive later.

**Partial production output.** If an order for 5 lehengas finishes 3 — close short with
a recorded variance, or split the order? Recommend closing short, since boutique runs
are small.

---

## 5. Permission model note

`app/permissions/catalog.py` describes itself as "architecture, not enforcement" —
routes still gate on the `admin/manager/outlet_staff` rank ladder via
`require_manager_up`.

The new `TAILOR` role **breaks that ladder**: a tailor outranks nobody, yet needs write
access to their own work orders. So:

- Manufacturing routes gate on `has_permission()` from day one, not on rank.
- `GET /api/v1/my/work-orders` scopes to the caller's tailor record **server-side**.
  Never filter by client-supplied tailor id.

New roles: `PRODUCTION_MANAGER`, `PURCHASE_MANAGER`, `TAILOR`, `ACCOUNTANT`.
"POS Operator" and "Sales Staff" from the spec map onto the existing `OUTLET_STAFF`
and `SALES` — no new roles needed for those.

---

## 6. Acceptance test (the one that matters)

The module is done when this runs green end to end, as a single integration test,
with an audit trail at every step:

```
create vendor
  → create raw materials (silk 4.5m, lace 8m, stones 250pc, thread 200g)
  → purchase order
  → goods receipt                    → assert raw stock ↑, moving_avg_cost moved
  → create finished item + BOM v1
  → create production order          → assert stock UNCHANGED        (Rule 3)
  → check availability               → assert shortage math correct
  → release                          → assert reserved ↑, on-hand UNCHANGED (Rule 4)
                                     → assert bom_version.is_locked  (Rule 12)
  → assign tailor, create work order
  → issue materials
  → consume (actual ≠ planned)       → assert on-hand ↓, variance recorded (Rule 5)
  → record wastage                   → assert attributable to tailor + material
  → quality check pass
  → complete                         → assert finished stock ↑        (Rule 6)
                                     → assert actual cost = materials + labour
  → sell via POS                     → assert finished stock ↓
  → traceability query               → assert garment resolves back to vendor
```

Plus two property tests worth their weight:

1. **Ledger replay** — replaying all `stock_movements` reproduces every
   `stock_levels` row exactly. `stock_levels` is a cache; prove it.
2. **Concurrent reservation** — two simultaneous releases against the last 4.5 m
   result in exactly one success and one typed `409`.

---

## 7. Seed data

Extend `app/seed.py`: 10 tailors, 20 vendors, 50 raw materials across the real
categories (fabric, lining, thread, buttons, stones, lace, zips, hooks, labels,
packaging), 20 finished garments, 10 BOMs, and one production order mid-flight so
the board is not empty on first login.

Existing demo logins are unchanged (`admin@tanisi.demo.com` / `admin123`, plus
manager and staff).
