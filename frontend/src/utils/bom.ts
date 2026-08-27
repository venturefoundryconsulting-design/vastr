/**
 * BOM builder helpers: bulk paste parsing, row validation, and version diffing.
 *
 * These are deliberately pure functions with no React or antd in them - the grid
 * is the part most likely to be reworked, and this is the part most worth
 * testing directly.
 *
 * Money is never computed here. Costs come from the backend, in Decimal (see
 * app/services/bom.py); JavaScript numbers are used only for quantities, where
 * a 4-dp value is far below the precision where doubles misbehave.
 */

import type { BomComponent, Item, Uom } from "../api/types";

export interface DraftRow extends Omit<BomComponent, "sequence"> {
  /** Stable client-side key. Server ids are absent until the draft is saved,
   *  and rows get reordered, so the table cannot key on either index or id. */
  key: string;
  sequence: number;
  stock_uom_code?: string | null;
  stock_uom_id?: number | null;
}

let counter = 0;
export const newRowKey = () => `r${Date.now().toString(36)}${(counter++).toString(36)}`;

export function itemToRow(item: Item, sequence: number): DraftRow {
  return {
    key: newRowKey(),
    item_id: item.id,
    sku: item.sku,
    name: item.display_name || item.name || item.sku,
    quantity: 1,
    // Default to the item's own stock unit: the common case, and always a valid
    // conversion, so a freshly added row is never born invalid.
    uom_id: item.stock_uom_id ?? 0,
    uom_code: item.stock_uom_code ?? null,
    stock_uom_id: item.stock_uom_id ?? null,
    stock_uom_code: item.stock_uom_code ?? null,
    scrap_pct: 0,
    is_optional: false,
    sequence,
    notes: null,
    substitutes: [],
  };
}

/** Base quantity plus expected wastage - mirrors BomComponent.gross_quantity. */
export function plannedRequirement(quantity: number, scrapPct: number): number {
  const gross = quantity * (1 + (scrapPct || 0) / 100);
  return Number(gross.toFixed(4));
}

// ---------------------------------------------------------------- validation

export type RowIssue = { field: string; message: string; severity: "error" | "warning" };

export function validateRow(
  row: DraftRow,
  ctx: { uomById: Map<number, Uom>; duplicateItemIds: Set<number>; itemById: Map<number, Item> },
): RowIssue[] {
  const issues: RowIssue[] = [];

  if (row.quantity === null || row.quantity === undefined || Number.isNaN(row.quantity)) {
    issues.push({ field: "quantity", message: "Quantity is required", severity: "error" });
  } else if (row.quantity <= 0) {
    issues.push({ field: "quantity", message: "Quantity must be more than zero", severity: "error" });
  }

  if (!row.uom_id) {
    issues.push({ field: "uom_id", message: "Choose a unit", severity: "error" });
  }

  if (row.scrap_pct < 0 || row.scrap_pct >= 100) {
    issues.push({ field: "scrap_pct", message: "Wastage must be between 0 and 99.9%", severity: "error" });
  }

  const item = ctx.itemById.get(row.item_id);
  if (item && !item.is_active) {
    issues.push({ field: "item", message: "This item is inactive", severity: "error" });
  }
  if (item && !item.is_stocked) {
    issues.push({
      field: "item",
      message: "This item isn't tracked in stock, so it can't be consumed",
      severity: "error",
    });
  }

  // Cross-dimension units (piece -> metre) are only valid when the item itself
  // defines a packaging conversion. The frontend cannot know about those, so
  // this is a warning and the backend remains authoritative.
  const lineUom = ctx.uomById.get(row.uom_id);
  const stockUom = row.stock_uom_id ? ctx.uomById.get(row.stock_uom_id) : undefined;
  if (lineUom && stockUom && lineUom.id !== stockUom.id && lineUom.category_id !== stockUom.category_id) {
    issues.push({
      field: "uom_id",
      message: `${lineUom.code} and ${stockUom.code} measure different things — needs a conversion on the item`,
      severity: "warning",
    });
  }

  if (ctx.duplicateItemIds.has(row.item_id)) {
    issues.push({
      field: "item",
      message: "This material appears on more than one line",
      severity: "warning",
    });
  }

  return issues;
}

/** Item ids appearing on more than one row with the same unit. Reported, never merged. */
export function findDuplicateItemIds(rows: DraftRow[]): Set<number> {
  const seen = new Map<string, number>();
  const dupes = new Set<number>();
  for (const r of rows) {
    const k = `${r.item_id}:${r.uom_id}`;
    seen.set(k, (seen.get(k) ?? 0) + 1);
    if ((seen.get(k) ?? 0) > 1) dupes.add(r.item_id);
  }
  return dupes;
}

// --------------------------------------------------------------- bulk paste

export interface ParsedPasteRow {
  raw: string;
  term: string;
  quantity: number | null;
  uomCode: string | null;
  matchedItem?: Item;
  matchedUom?: Uom;
  error?: string;
}

/**
 * Parses tab- or comma-separated rows pasted out of Excel / Google Sheets.
 *
 *     Silk Fabric\t4.5\tm
 *     Gold Lace,8,m
 *
 * Column order is name-or-SKU, quantity, unit. Matching is exact-SKU first, then
 * a unique case-insensitive name match - an ambiguous name is reported rather
 * than guessed, because silently picking the wrong lace is worse than asking.
 */
export function parsePaste(text: string, items: Item[], uoms: Uom[]): ParsedPasteRow[] {
  const bySku = new Map(items.map((i) => [i.sku.toLowerCase(), i]));
  const byBarcode = new Map(items.filter((i) => i.barcode).map((i) => [String(i.barcode).toLowerCase(), i]));
  const byName = new Map<string, Item[]>();
  for (const i of items) {
    const n = (i.name || i.display_name || "").toLowerCase().trim();
    if (!n) continue;
    byName.set(n, [...(byName.get(n) ?? []), i]);
  }
  const uomByCode = new Map(uoms.map((u) => [u.code.toLowerCase(), u]));
  const uomByName = new Map(uoms.map((u) => [u.name.toLowerCase(), u]));

  return text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean)
    .map((line) => {
      const cells = line.split(/\t|,(?=(?:[^"]*"[^"]*")*[^"]*$)/).map((c) => c.trim().replace(/^"|"$/g, ""));
      const [term = "", qtyRaw = "", uomRaw = ""] = cells;
      const row: ParsedPasteRow = {
        raw: line,
        term,
        quantity: qtyRaw ? Number(qtyRaw.replace(/,/g, "")) : null,
        uomCode: uomRaw || null,
      };

      if (!term) {
        row.error = "No material name or SKU";
        return row;
      }
      const key = term.toLowerCase();
      const item = bySku.get(key) ?? byBarcode.get(key);
      if (item) {
        row.matchedItem = item;
      } else {
        const candidates = byName.get(key) ?? [];
        if (candidates.length === 1) row.matchedItem = candidates[0];
        else if (candidates.length > 1) row.error = `"${term}" matches ${candidates.length} items — use the SKU`;
        else row.error = `No item found for "${term}"`;
      }

      if (row.quantity !== null && (Number.isNaN(row.quantity) || row.quantity <= 0)) {
        row.error = row.error ?? `"${qtyRaw}" isn't a valid quantity`;
      }

      if (uomRaw) {
        const u = uomByCode.get(uomRaw.toLowerCase()) ?? uomByName.get(uomRaw.toLowerCase());
        if (u) row.matchedUom = u;
        else row.error = row.error ?? `Unknown unit "${uomRaw}"`;
      }
      return row;
    });
}

// ------------------------------------------------------------ version diffing

export type DiffKind = "added" | "removed" | "quantity" | "uom" | "wastage" | "substitutes" | "unchanged";

export interface DiffRow {
  item_id: number;
  sku: string;
  name: string;
  kind: DiffKind;
  from?: { quantity: number; uom_code?: string | null; scrap_pct: number; substitutes: number };
  to?: { quantity: number; uom_code?: string | null; scrap_pct: number; substitutes: number };
}

/** Compares two versions' component lists. Set comparison, not arithmetic. */
export function diffVersions(from: BomComponent[], to: BomComponent[]): DiffRow[] {
  const snap = (c: BomComponent) => ({
    quantity: Number(c.quantity),
    uom_code: c.uom_code ?? null,
    scrap_pct: Number(c.scrap_pct),
    substitutes: c.substitutes?.length ?? 0,
  });
  const fromMap = new Map(from.map((c) => [c.item_id, c]));
  const toMap = new Map(to.map((c) => [c.item_id, c]));
  const out: DiffRow[] = [];

  for (const [itemId, t] of toMap) {
    const f = fromMap.get(itemId);
    const base = { item_id: itemId, sku: t.sku ?? "", name: t.name ?? "" };
    if (!f) {
      out.push({ ...base, kind: "added", to: snap(t) });
      continue;
    }
    const a = snap(f);
    const b = snap(t);
    let kind: DiffKind = "unchanged";
    if (a.quantity !== b.quantity) kind = "quantity";
    else if (a.uom_code !== b.uom_code) kind = "uom";
    else if (a.scrap_pct !== b.scrap_pct) kind = "wastage";
    else if (a.substitutes !== b.substitutes) kind = "substitutes";
    out.push({ ...base, kind, from: a, to: b });
  }
  for (const [itemId, f] of fromMap) {
    if (!toMap.has(itemId)) {
      out.push({
        item_id: itemId, sku: f.sku ?? "", name: f.name ?? "",
        kind: "removed", from: snap(f),
      });
    }
  }
  const order: DiffKind[] = ["added", "removed", "quantity", "uom", "wastage", "substitutes", "unchanged"];
  return out.sort((x, y) => order.indexOf(x.kind) - order.indexOf(y.kind) || x.sku.localeCompare(y.sku));
}

/** Shape the grid rows into the payload the components-replace endpoint expects. */
export function toPayload(rows: DraftRow[]) {
  return rows.map((r, i) => ({
    item_id: r.item_id,
    quantity: r.quantity,
    uom_id: r.uom_id,
    scrap_pct: r.scrap_pct,
    is_optional: r.is_optional,
    sequence: i,
    notes: r.notes || null,
    substitutes: (r.substitutes ?? []).map((s) => ({
      item_id: s.item_id, priority: s.priority ?? 0, notes: s.notes || null,
    })),
  }));
}
