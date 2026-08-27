/**
 * API client functions for the manufacturing phases with no prior frontend
 * surface: production output (3E), workforce (3F), quality/costing (3G-3H),
 * MRP, goods receipts (5), and made-to-order (4).
 *
 * Material flow (Phase 3D) already has a complete client in api/endpoints.ts
 * (getOrderMaterials, reserveMaterials, issueMaterials, consumeMaterials,
 * returnMaterials, releaseReservations, listReservations, listMaterialIssues,
 * listMaterialConsumption, listMaterialReturns) used by
 * components/MaterialFlowPanel.tsx - not duplicated here.
 */

import { apiClient } from "./client";
import type {
  AiImportBatchOut,
  AiImportBatchSummary,
  AiImportRowOut,
  AiImportStatus,
  CustomerOrderOut,
  Fulfilment,
  GoodsReceiptOut,
  LookupOut,
  MeasurementFieldOut,
  MeasurementProfileOut,
  MrpRequirementRow,
  OrderCost,
  ProductionOutputOut,
  ProductionStageOut,
  ProductionSummary,
  PurchaseReturnOut,
  QualityCheckOut,
  ReadinessOut,
  ReworkOut,
  TailorOut,
  TailorProductivityRow,
  TailorWorkload,
  VarianceLine,
  WastageOut,
  WastageReportRow,
  WorkOrderOut,
} from "./manufacturing-types";

// ---- Production output & completion (Phase 3E) ----
export const listOutputs = (orderId: number) =>
  apiClient.get<ProductionOutputOut[]>(`/api/production-orders/${orderId}/outputs`);
export const recordOutput = (orderId: number, quantity: number, note?: string, location_id?: number) =>
  apiClient.post(`/api/production-orders/${orderId}/output`, { quantity, note, location_id });
export const completeProductionOrder = (orderId: number) =>
  apiClient.post(`/api/production-orders/${orderId}/complete`);
export const closeShortProductionOrder = (orderId: number, produced_quantity: number, reason: string) =>
  apiClient.post(`/api/production-orders/${orderId}/close-short`, { produced_quantity, reason });

// ---- Workforce (Phase 3F) ----
export const listProductionStages = () =>
  apiClient.get<ProductionStageOut[]>("/api/production-stages");
export const createProductionStage = (data: Partial<ProductionStageOut>) =>
  apiClient.post<ProductionStageOut>("/api/production-stages", data);
export const updateProductionStage = (id: number, data: Partial<ProductionStageOut>) =>
  apiClient.patch<ProductionStageOut>(`/api/production-stages/${id}`, data);

export const listTailors = (params?: { is_active?: boolean }) =>
  apiClient.get<TailorOut[]>("/api/tailors", { params });
export const getTailorWorkload = () => apiClient.get<TailorWorkload[]>("/api/tailors/workload");
export const createTailor = (data: Partial<TailorOut>) => apiClient.post<TailorOut>("/api/tailors", data);
export const updateTailor = (id: number, data: Partial<TailorOut>) =>
  apiClient.patch<TailorOut>(`/api/tailors/${id}`, data);

export const listWorkOrders = (params?: {
  status?: string; tailor_id?: number; production_order_id?: number; stage_id?: number;
}) => apiClient.get<WorkOrderOut[]>("/api/work-orders", { params });
export const listMyWorkOrders = () => apiClient.get<WorkOrderOut[]>("/api/work-orders/mine");
export const createWorkOrder = (data: {
  production_order_id: number; stage_id: number; tailor_id?: number | null;
  quantity?: number; sequence?: number; due_date?: string | null; rate?: number; notes?: string;
}) => apiClient.post<WorkOrderOut>("/api/work-orders", data);
export const assignWorkOrder = (id: number, tailor_id: number, rate?: number) =>
  apiClient.post<WorkOrderOut>(`/api/work-orders/${id}/assign`, { tailor_id, rate });
export const startWorkOrder = (id: number) => apiClient.post<WorkOrderOut>(`/api/work-orders/${id}/start`);
export const pauseWorkOrder = (id: number) => apiClient.post<WorkOrderOut>(`/api/work-orders/${id}/pause`);
export const completeWorkOrder = (id: number, completed_quantity?: number, hours?: number) =>
  apiClient.post<WorkOrderOut>(`/api/work-orders/${id}/complete`, { completed_quantity, hours });
export const reportWorkOrderIssue = (id: number, reason: string) =>
  apiClient.post<WorkOrderOut>(`/api/work-orders/${id}/report-issue`, { reason });
export const cancelWorkOrder = (id: number, reason?: string) =>
  apiClient.post<WorkOrderOut>(`/api/work-orders/${id}/cancel`, { reason });

// ---- Quality, rework, wastage (Phase 3G) ----
export const listDefectCategories = () => apiClient.get<LookupOut[]>("/api/defect-categories");
export const listWastageReasons = () => apiClient.get<LookupOut[]>("/api/wastage-reasons");

export const listQualityChecks = (orderId: number) =>
  apiClient.get<QualityCheckOut[]>(`/api/production-orders/${orderId}/quality-checks`);
export const createQualityCheck = (orderId: number, data: {
  result: string; checked_quantity: number; failed_quantity?: number; work_order_id?: number | null;
  notes?: string; defects?: { defect_category_id: number; quantity: number; notes?: string }[];
}) => apiClient.post(`/api/production-orders/${orderId}/quality-checks`, data);

export const listRework = (orderId: number) =>
  apiClient.get<ReworkOut[]>(`/api/production-orders/${orderId}/rework`);
export const createRework = (orderId: number, data: {
  quantity: number; reason: string; quality_check_id?: number | null;
  work_order_id?: number | null; assigned_tailor_id?: number | null;
}) => apiClient.post(`/api/production-orders/${orderId}/rework`, data);
export const resolveRework = (reworkId: number) => apiClient.post(`/api/rework/${reworkId}/resolve`);

export const listOrderWastage = (orderId: number) =>
  apiClient.get<WastageOut>(`/api/production-orders/${orderId}/wastage`);
export const recordWastage = (orderId: number, data: {
  material_id: number; quantity: number; reason_id?: number | null;
  work_order_id?: number | null; tailor_id?: number | null; notes?: string;
}) => apiClient.post(`/api/production-orders/${orderId}/wastage`, data);

// ---- Costing & manufacturing reports (Phase 3H) ----
export const getOrderCost = (orderId: number) =>
  apiClient.get<OrderCost>(`/api/production-orders/${orderId}/cost`);
export const getOrderVariance = (orderId: number) =>
  apiClient.get<VarianceLine[]>(`/api/production-orders/${orderId}/variance`);
export const getManufacturingSummary = () =>
  apiClient.get<ProductionSummary>("/api/manufacturing/summary");
export const getWastageReport = (limit = 50) =>
  apiClient.get<WastageReportRow[]>("/api/manufacturing/wastage-report", { params: { limit } });
export const getTailorProductivity = () =>
  apiClient.get<TailorProductivityRow[]>("/api/manufacturing/tailor-productivity");

// ---- MRP ----
export const getMrpRequirements = (location_id?: number) =>
  apiClient.get<MrpRequirementRow[]>("/api/mrp/requirements", { params: { location_id } });
export const generateMrpPurchaseOrders = (outlet_id: number, item_ids?: number[]) =>
  apiClient.post("/api/mrp/generate-purchase-orders", { outlet_id, item_ids });

// ---- Goods receipts & purchase returns (Phase 5) ----
export const listGoodsReceipts = (params?: { status?: string; purchase_order_id?: number }) =>
  apiClient.get<GoodsReceiptOut[]>("/api/goods-receipts", { params });
export const getGoodsReceipt = (id: number) =>
  apiClient.get<GoodsReceiptOut>(`/api/goods-receipts/${id}`);
export const createGoodsReceipt = (data: {
  purchase_order_id?: number | null; vendor_id?: number | null; outlet_id?: number | null;
  vendor_invoice_ref?: string; notes?: string;
  lines: { purchase_order_item_id?: number | null; item_id?: number | null; quantity: number; uom_id?: number | null; unit_cost?: number; note?: string }[];
}) => apiClient.post<GoodsReceiptOut>("/api/goods-receipts", data);
export const postGoodsReceipt = (id: number) =>
  apiClient.post<GoodsReceiptOut>(`/api/goods-receipts/${id}/post`);
export const cancelGoodsReceipt = (id: number) =>
  apiClient.post<GoodsReceiptOut>(`/api/goods-receipts/${id}/cancel`);

export const listPurchaseReturns = (goods_receipt_id?: number) =>
  apiClient.get<PurchaseReturnOut[]>("/api/purchase-returns", { params: { goods_receipt_id } });
export const createPurchaseReturn = (data: {
  goods_receipt_id?: number | null; vendor_id?: number | null; outlet_id: number;
  reason?: string; notes?: string;
  lines: { goods_receipt_item_id?: number | null; item_id?: number | null; quantity: number; uom_id?: number | null; unit_cost?: number }[];
}) => apiClient.post<PurchaseReturnOut>("/api/purchase-returns", data);

// ---- Made-to-order (Phase 4) ----
export const listMeasurementFields = (include_inactive = false) =>
  apiClient.get<MeasurementFieldOut[]>("/api/measurement-fields", { params: { include_inactive } });
export const createMeasurementField = (data: {
  code: string; name: string; unit?: string; sequence?: number; group_name?: string;
}) => apiClient.post<MeasurementFieldOut>("/api/measurement-fields", data);
export const listCustomerMeasurements = (customerId: number) =>
  apiClient.get<MeasurementProfileOut[]>(`/api/customers/${customerId}/measurements`);
export const createMeasurementProfile = (data: {
  customer_id: number; name: string; notes?: string;
  values: { field_id: number; value: number; notes?: string }[];
}) => apiClient.post<MeasurementProfileOut>("/api/measurement-profiles", data);
export const updateMeasurementProfile = (id: number, data: {
  name?: string; notes?: string; is_active?: boolean;
  values?: { field_id: number; value: number; notes?: string }[];
}) => apiClient.patch<MeasurementProfileOut>(`/api/measurement-profiles/${id}`, data);

export const listCustomerOrders = (params?: { status?: string; customer_id?: number }) =>
  apiClient.get<CustomerOrderOut[]>("/api/customer-orders", { params });
export const getCustomerOrder = (id: number) =>
  apiClient.get<CustomerOrderOut>(`/api/customer-orders/${id}`);
export const createCustomerOrder = (data: {
  customer_id: number; outlet_id: number; promised_date?: string | null;
  advance_amount?: number; notes?: string;
  items: {
    item_id: number; quantity: number; unit_price: number; tax_rate?: number;
    fulfilment: Fulfilment; measurement_profile_id?: number | null; notes?: string;
  }[];
}) => apiClient.post<CustomerOrderOut>("/api/customer-orders", data);
export const confirmCustomerOrder = (id: number) =>
  apiClient.post<CustomerOrderOut>(`/api/customer-orders/${id}/confirm`);
export const getCustomerOrderReadiness = (id: number) =>
  apiClient.get<ReadinessOut>(`/api/customer-orders/${id}/readiness`);
export const markCustomerOrderReady = (id: number) =>
  apiClient.post<CustomerOrderOut>(`/api/customer-orders/${id}/ready`);
export const deliverCustomerOrder = (id: number, payment_mode = "cash", discount_amount = 0) =>
  apiClient.post<CustomerOrderOut>(`/api/customer-orders/${id}/deliver`, { payment_mode, discount_amount });
export const cancelCustomerOrder = (id: number, reason?: string) =>
  apiClient.post<CustomerOrderOut>(`/api/customer-orders/${id}/cancel`, { reason });

// ------------------------------------------------------------- AI import (Phase 9)

export const listAiImportBatches = (status?: AiImportStatus) =>
  apiClient.get<AiImportBatchSummary[]>("/api/ai-import", { params: status ? { status } : {} });
export const getAiImportBatch = (id: number) =>
  apiClient.get<AiImportBatchOut>(`/api/ai-import/${id}`);
export const extractAiImportInvoice = (file: File, outletId: number, vendorId?: number) => {
  const formData = new FormData();
  formData.append("file", file);
  const params: Record<string, number> = { outlet_id: outletId };
  if (vendorId) params.vendor_id = vendorId;
  return apiClient.post<AiImportBatchOut>("/api/ai-import/extract", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    params,
  });
};
export const patchAiImportRow = (
  rowId: number,
  data: Partial<{
    raw_description: string; quantity: number; unit_cost: number; uom_id: number | null;
    matched_item_id: number | null; is_new_item: boolean; proposed_sku: string | null; excluded: boolean;
  }>,
) => apiClient.patch<AiImportRowOut>(`/api/ai-import/rows/${rowId}`, data);
export const approveAiImportBatch = (id: number) =>
  apiClient.post<AiImportBatchOut>(`/api/ai-import/batches/${id}/approve`);
export const rejectAiImportBatch = (id: number) =>
  apiClient.post<AiImportBatchOut>(`/api/ai-import/batches/${id}/reject`);
