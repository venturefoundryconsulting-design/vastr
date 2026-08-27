/**
 * Logic checks for the BOM builder helpers.
 *
 * Run with:  npm run check:bom
 *
 * The frontend has no test runner (no vitest/jest), and adding one was out of
 * scope for Phase 3B - so this is a plain script bundled through the esbuild
 * that Vite already ships. It covers the pure logic in ./bom.ts: wastage
 * arithmetic, bulk-paste parsing, row validation and version diffing. Grid
 * interaction (keyboard, virtualization, drag) is not covered here and still
 * needs a human or a browser driver.
 */

import { parsePaste, diffVersions, validateRow, plannedRequirement, findDuplicateItemIds, itemToRow, toPayload } from "./bom";

let pass = 0, fail = 0;
const eq = (name: string, got: any, want: any) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { pass++; console.log(`  PASS  ${name}`); }
  else { fail++; console.log(`  FAIL  ${name}\n        got  ${g}\n        want ${w}`); }
};

const uoms: any[] = [
  { id: 1, code: "PC", name: "Piece", category_id: 10, is_active: true },
  { id: 2, code: "M", name: "Meter", category_id: 20, is_active: true },
  { id: 3, code: "CM", name: "Centimeter", category_id: 20, is_active: true },
  { id: 4, code: "KG", name: "Kilogram", category_id: 30, is_active: true },
];
const items: any[] = [
  { id: 101, sku: "FAB-SLK", name: "Silk Fabric", barcode: null, is_active: true, is_stocked: true, stock_uom_id: 2, stock_uom_code: "M" },
  { id: 102, sku: "LAC-GOLD", name: "Gold Lace", barcode: "890111", is_active: true, is_stocked: true, stock_uom_id: 2, stock_uom_code: "M" },
  { id: 103, sku: "BTN-PRL", name: "Pearl Button", barcode: null, is_active: true, is_stocked: true, stock_uom_id: 1, stock_uom_code: "PC" },
  { id: 104, sku: "STM-SWR", name: "Swarovski", barcode: null, is_active: true, is_stocked: true, stock_uom_id: 1, stock_uom_code: "PC" },
  { id: 105, sku: "THR-SLK", name: "Silk Thread", barcode: null, is_active: true, is_stocked: true, stock_uom_id: 4, stock_uom_code: "KG" },
  { id: 106, sku: "OLD-ITEM", name: "Retired Trim", barcode: null, is_active: false, is_stocked: true, stock_uom_id: 1, stock_uom_code: "PC" },
  { id: 107, sku: "SRV-FIT", name: "Fitting Service", barcode: null, is_active: true, is_stocked: false, stock_uom_id: 1, stock_uom_code: "PC" },
];

console.log("\n-- wastage --");
eq("8m + 5% = 8.4", plannedRequirement(8, 5), 8.4);
eq("4.5m + 0% = 4.5", plannedRequirement(4.5, 0), 4.5);
eq("0.125kg + 10%", plannedRequirement(0.125, 10), 0.1375);

console.log("\n-- bulk paste (the brief's example, tab-separated) --");
const pasted = parsePaste(
  "Silk Fabric\t4.5\tm\nGold Lace\t8\tm\nPearl Button\t18\tpc\nSwarovski\t250\tpc\nSilk Thread\t0.2\tkg",
  items, uoms);
eq("5 rows parsed", pasted.length, 5);
eq("all matched", pasted.filter(r => r.matchedItem && !r.error).length, 5);
eq("fabric qty", pasted[0].quantity, 4.5);
eq("fabric uom -> M", pasted[0].matchedUom?.code, "M");
eq("thread qty 0.2", pasted[4].quantity, 0.2);
eq("thread uom -> KG", pasted[4].matchedUom?.code, "KG");

console.log("\n-- paste: CSV, SKU and barcode lookup --");
eq("csv works", parsePaste("FAB-SLK,4.5,m", items, uoms)[0].matchedItem?.id, 101);
eq("sku match", parsePaste("LAC-GOLD\t3\tm", items, uoms)[0].matchedItem?.id, 102);
eq("barcode match", parsePaste("890111\t3\tm", items, uoms)[0].matchedItem?.id, 102);

console.log("\n-- paste: error reporting --");
eq("unknown item", !!parsePaste("Nonexistent\t1\tpc", items, uoms)[0].error, true);
eq("bad qty", !!parsePaste("FAB-SLK\tabc\tm", items, uoms)[0].error, true);
eq("unknown unit", !!parsePaste("FAB-SLK\t1\tfurlong", items, uoms)[0].error, true);
eq("negative qty", !!parsePaste("FAB-SLK\t-5\tm", items, uoms)[0].error, true);

console.log("\n-- duplicates --");
const rows = [itemToRow(items[1], 0), itemToRow(items[1], 1), itemToRow(items[0], 2)];
rows[0].quantity = 4; rows[1].quantity = 3;
eq("gold lace flagged twice", [...findDuplicateItemIds(rows)], [102]);
eq("rows not merged", rows.length, 3);

console.log("\n-- validation --");
const ctx = {
  uomById: new Map(uoms.map(u => [u.id, u])),
  itemById: new Map(items.map(i => [i.id, i])),
  duplicateItemIds: new Set<number>(),
};
const mk = (over: any) => ({ ...itemToRow(items[0], 0), ...over });
eq("valid row clean", validateRow(mk({}), ctx).length, 0);
eq("zero qty errors", validateRow(mk({ quantity: 0 }), ctx).some(i => i.severity === "error"), true);
eq("negative qty errors", validateRow(mk({ quantity: -1 }), ctx).some(i => i.severity === "error"), true);
eq("no uom errors", validateRow(mk({ uom_id: 0 }), ctx).some(i => i.severity === "error"), true);
eq("wastage 100 errors", validateRow(mk({ scrap_pct: 100 }), ctx).some(i => i.severity === "error"), true);
eq("cm on m-stocked ok", validateRow(mk({ uom_id: 3 }), ctx).filter(i => i.severity === "error").length, 0);
eq("PC on m-stocked warns", validateRow(mk({ uom_id: 1 }), ctx).some(i => i.severity === "warning"), true);
eq("inactive item errors", validateRow({ ...itemToRow(items[5], 0) }, ctx).some(i => i.severity === "error"), true);
eq("non-stocked item errors", validateRow({ ...itemToRow(items[6], 0) }, ctx).some(i => i.severity === "error"), true);

console.log("\n-- version diff --");
const v1: any[] = [
  { item_id: 101, sku: "FAB-SLK", name: "Silk Fabric", quantity: 4.5, uom_code: "M", scrap_pct: 0, substitutes: [] },
  { item_id: 102, sku: "LAC-GOLD", name: "Gold Lace", quantity: 8, uom_code: "M", scrap_pct: 0, substitutes: [] },
  { item_id: 103, sku: "BTN-PRL", name: "Pearl Button", quantity: 18, uom_code: "PC", scrap_pct: 0, substitutes: [] },
];
const v2: any[] = [
  { item_id: 101, sku: "FAB-SLK", name: "Silk Fabric", quantity: 4.5, uom_code: "M", scrap_pct: 0, substitutes: [] },
  { item_id: 102, sku: "LAC-GOLD", name: "Gold Lace", quantity: 10, uom_code: "M", scrap_pct: 0, substitutes: [] },
  { item_id: 104, sku: "STM-SWR", name: "Swarovski", quantity: 250, uom_code: "PC", scrap_pct: 5, substitutes: [] },
];
const d = diffVersions(v1, v2);
const kind = (id: number) => d.find(x => x.item_id === id)?.kind;
eq("stones added", kind(104), "added");
eq("buttons removed", kind(103), "removed");
eq("lace qty changed", kind(102), "quantity");
eq("fabric unchanged", kind(101), "unchanged");
eq("lace 8 -> 10", [d.find(x => x.item_id === 102)?.from?.quantity, d.find(x => x.item_id === 102)?.to?.quantity], [8, 10]);

console.log("\n-- payload shaping --");
const payload = toPayload([itemToRow(items[0], 0), itemToRow(items[1], 1)] as any);
eq("sequence renumbered", payload.map(p => p.sequence), [0, 1]);
eq("carries item ids", payload.map(p => p.item_id), [101, 102]);

console.log(`\n${pass} passed, ${fail} failed`);
if (fail) throw new Error(`${fail} BOM helper check(s) failed`);
