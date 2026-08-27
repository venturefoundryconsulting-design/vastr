/**
 * Types for the manufacturing phases with no prior frontend surface: production
 * output (3E), workforce (3F), quality/costing (3G-3H), MRP, goods receipts (5),
 * and made-to-order (4).
 *
 * Material flow (Phase 3D - reservation/issue/consumption/return) is NOT here:
 * it already has a complete implementation in api/types.ts and api/endpoints.ts
 * (MaterialPosition, OrderMaterialSummary, MaterialReservation, MaterialTxn,
 * reserveMaterials, issueMaterials, etc.), consumed by the existing
 * components/MaterialFlowPanel.tsx. Duplicating it here would just be confusing.
 *
 * Kept in a separate file from api/types.ts rather than appended to it - that
 * file is already large, and this batch is naturally one unit to review.
 */

import type { ProductionStatus } from "./types";

export interface ProductionOutputOut {
  id: number;
  production_order_id: number;
  item_id: number;
  sku?: string | null;
  name?: string | null;
  location_id: number;
  quantity: number;
  uom_code?: string | null;
  stock_movement_id?: number | null;
  note?: string | null;
  created_at?: string | null;
}

// ---- Workforce (Phase 3F) ----
export type PayModel = "per_garment" | "per_stage" | "per_piece" | "hourly" | "fixed";
export type WorkOrderStatus =
  | "pending" | "assigned" | "in_progress" | "paused" | "completed" | "rework" | "cancelled";

export interface ProductionStageOut {
  id: number;
  code: string;
  name: string;
  sequence: number;
  default_rate: number;
  is_qc: boolean;
  is_active: boolean;
}

export interface TailorSkill {
  name: string;
  stage_id?: number | null;
  proficiency: number;
}

export interface TailorOut {
  id: number;
  code: string;
  name: string;
  phone?: string | null;
  user_id?: number | null;
  pay_model: PayModel;
  default_rate: number;
  joined_on?: string | null;
  notes?: string | null;
  is_active: boolean;
  skills: TailorSkill[];
}

export interface TailorWorkload {
  tailor_id: number;
  name: string;
  active: number;
  pending: number;
  completed: number;
  overdue: number;
}

export interface WorkOrderOut {
  id: number;
  wo_number: string;
  production_order_id: number;
  po_number?: string | null;
  item_name?: string | null;
  stage_id: number;
  stage_name?: string | null;
  tailor_id?: number | null;
  tailor_name?: string | null;
  quantity: number;
  completed_quantity: number;
  status: WorkOrderStatus;
  sequence: number;
  due_date?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  pay_model?: PayModel | null;
  rate: number;
  hours: number;
  labour_cost: number;
  is_overdue: boolean;
  notes?: string | null;
  issue_note?: string | null;
  allowed_transitions: WorkOrderStatus[];
}

// ---- Quality (Phase 3G) ----
export type QcResult = "pass" | "fail" | "partial";
export type ReworkStatus = "open" | "in_progress" | "resolved" | "cancelled";

export interface LookupOut {
  id: number;
  code: string;
  name: string;
  is_active: boolean;
}

export interface QualityCheckOut {
  id: number;
  result: QcResult;
  checked_quantity: number;
  passed_quantity: number;
  failed_quantity: number;
  work_order_id?: number | null;
  notes?: string | null;
  photo_path?: string | null;
  inspector_id?: number | null;
  checked_at?: string | null;
  defects: { category: string | null; quantity: number; notes: string | null }[];
}

export interface ReworkOut {
  id: number;
  rework_number: string;
  quantity: number;
  reason: string;
  status: ReworkStatus;
  work_order_id?: number | null;
  assigned_tailor_id?: number | null;
  resolved_at?: string | null;
  created_at?: string | null;
}

export interface WastageEntry {
  id: number;
  item_id: number;
  sku?: string | null;
  name?: string | null;
  quantity: number;
  uom_id?: number | null;
  reason?: string | null;
  tailor_name?: string | null;
  work_order_id?: number | null;
  notes?: string | null;
  created_at?: string | null;
}

export interface WastageOut {
  entries: WastageEntry[];
  summary: Record<string, number>;
  total_cost: number;
}

// ---- Costing (Phase 3H) ----
export interface CostMaterialLine {
  material_id: number;
  item_id: number;
  sku?: string | null;
  name?: string | null;
  unit_cost: number;
  planned_quantity: number;
  consumed_quantity: number;
  wasted_quantity: number;
  estimated_cost: number;
  actual_cost: number;
  wastage_cost: number;
  variance: number;
}

export interface CostLabourLine {
  work_order_id: number;
  wo_number: string;
  stage_name?: string | null;
  tailor_name?: string | null;
  status: WorkOrderStatus;
  pay_model?: PayModel | null;
  rate: number;
  quantity: number;
  completed_quantity: number;
  hours: number;
  estimated_cost: number;
  actual_cost: number;
}

export interface OrderCost {
  production_order_id: number;
  po_number: string;
  status: ProductionStatus;
  planned_quantity: number;
  produced_quantity: number;
  estimated_material_cost: number;
  actual_material_cost: number;
  wastage_cost: number;
  estimated_labour_cost: number;
  actual_labour_cost: number;
  estimated_total_cost: number;
  actual_total_cost: number;
  variance: number;
  estimated_unit_cost?: number | null;
  actual_unit_cost?: number | null;
  material_lines: CostMaterialLine[];
  labour_lines: CostLabourLine[];
}

export interface VarianceLine {
  sku?: string | null;
  name?: string | null;
  planned: number;
  consumed: number;
  wasted: number;
  quantity_variance: number;
  cost_variance: number;
}

export interface ProductionSummary {
  orders_by_status: Record<string, number>;
  work_orders_by_status: Record<string, number>;
  open_rework: number;
  failed_quality_checks: number;
  active_orders: number;
}

export interface WastageReportRow {
  item_id: number;
  sku?: string | null;
  name?: string | null;
  quantity: number;
  entries: number;
  cost: number;
}

export interface TailorProductivityRow {
  tailor_id: number;
  name?: string | null;
  completed_work_orders: number;
  completed_quantity: number;
  hours: number;
  earnings: number;
}

// ---- MRP ----
export interface MrpRequirementRow {
  item_id: number;
  sku?: string | null;
  name?: string | null;
  uom_code?: string | null;
  required: number;
  on_hand: number;
  reserved: number;
  available: number;
  shortage: number;
  suggested_purchase_qty: number;
  preferred_vendor_id?: number | null;
  preferred_vendor_name?: string | null;
  min_order_qty?: number | null;
  lead_time_days?: number | null;
  contributing_orders: { production_order_id: number; po_number: string; quantity: number }[];
}

// ---- Goods receipts (Phase 5) ----
export type ReceiptStatus = "draft" | "posted" | "cancelled";

export interface GoodsReceiptLineOut {
  id: number;
  item_id: number;
  sku?: string | null;
  name?: string | null;
  quantity: number;
  uom_code?: string | null;
  quantity_in_stock_uom: number;
  unit_cost: number;
  line_cost: number;
  stock_movement_id?: number | null;
  note?: string | null;
}

export interface GoodsReceiptOut {
  id: number;
  receipt_number: string;
  purchase_order_id?: number | null;
  po_number?: string | null;
  vendor_id?: number | null;
  vendor_name?: string | null;
  outlet_id: number;
  outlet_name?: string | null;
  receipt_date?: string | null;
  vendor_invoice_ref?: string | null;
  status: ReceiptStatus;
  posted_at?: string | null;
  notes?: string | null;
  total_cost: number;
  items: GoodsReceiptLineOut[];
}

export interface PurchaseReturnLineOut {
  id: number;
  item_id: number;
  sku?: string | null;
  quantity: number;
  unit_cost: number;
  line_cost: number;
  stock_movement_id?: number | null;
}

export interface PurchaseReturnOut {
  id: number;
  return_number: string;
  goods_receipt_id?: number | null;
  vendor_id?: number | null;
  vendor_name?: string | null;
  outlet_id: number;
  return_date?: string | null;
  reason?: string | null;
  total_cost: number;
  items: PurchaseReturnLineOut[];
}

// ---- Made-to-order (Phase 4) ----
export type CustomerOrderStatus =
  | "draft" | "confirmed" | "in_production" | "ready" | "delivered" | "cancelled";
export type Fulfilment = "ready_stock" | "made_to_order";

export interface MeasurementFieldOut {
  id: number;
  code: string;
  name: string;
  unit: string;
  sequence: number;
  group_name?: string | null;
  is_active: boolean;
}

export interface MeasurementProfileOut {
  id: number;
  customer_id: number;
  name: string;
  notes?: string | null;
  taken_at?: string | null;
  is_active: boolean;
  values: {
    field_id: number; code: string | null; label: string | null;
    unit: string | null; value: number; notes: string | null;
  }[];
}

export interface CustomerOrderItemOut {
  id: number;
  item_id: number;
  sku?: string | null;
  name?: string | null;
  quantity: number;
  unit_price: number;
  tax_rate: number;
  line_total: number;
  fulfilment: Fulfilment;
  measurement_profile_id?: number | null;
  production_order_id?: number | null;
  production_status?: ProductionStatus | null;
  produced_quantity?: number | null;
  notes?: string | null;
}

export interface CustomerOrderOut {
  id: number;
  order_number: string;
  customer_id: number;
  customer_name?: string | null;
  outlet_id: number;
  outlet_name?: string | null;
  status: CustomerOrderStatus;
  order_date?: string | null;
  promised_date?: string | null;
  delivered_at?: string | null;
  advance_amount: number;
  total_amount: number;
  balance_due: number;
  sale_id?: number | null;
  notes?: string | null;
  cancel_reason?: string | null;
  has_made_to_order: boolean;
  allowed_transitions: CustomerOrderStatus[];
  items: CustomerOrderItemOut[];
}

export interface ReadinessLine {
  item_id: number;
  sku?: string | null;
  name?: string | null;
  quantity: number;
  fulfilment: Fulfilment;
  production_order_id?: number | null;
  is_ready: boolean;
  note?: string | null;
}

export interface ReadinessOut {
  all_ready: boolean;
  lines: ReadinessLine[];
}

// ------------------------------------------------------------- AI import (Phase 9)

export type AiImportStatus = "pending" | "approved" | "rejected";

export interface AiImportRowOut {
  id: number;
  line_no: number;
  raw_description: string;
  raw_unit_text?: string | null;
  matched_item_id?: number | null;
  matched_item_name?: string | null;
  matched_item_sku?: string | null;
  is_new_item: boolean;
  proposed_sku?: string | null;
  quantity: number;
  uom_id?: number | null;
  uom_code?: string | null;
  unit_cost: number;
  description_confidence?: number | null;
  quantity_confidence?: number | null;
  cost_confidence?: number | null;
  match_confidence?: number | null;
  excluded: boolean;
}

export interface AiImportBatchOut {
  id: number;
  outlet_id: number;
  outlet_name?: string | null;
  vendor_id?: number | null;
  vendor_name?: string | null;
  source_filename: string;
  status: AiImportStatus;
  vendor_name_guess?: string | null;
  invoice_ref_guess?: string | null;
  goods_receipt_id?: number | null;
  goods_receipt_number?: string | null;
  notes?: string | null;
  created_at: string;
  rows: AiImportRowOut[];
}

export interface AiImportBatchSummary {
  id: number;
  outlet_name?: string | null;
  vendor_name?: string | null;
  source_filename: string;
  status: AiImportStatus;
  line_count: number;
  created_at: string;
}
