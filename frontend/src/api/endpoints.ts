import { apiClient } from "./client";
import type {
  Alteration,
  AlterationStatus,
  AppSettings,
  AppUser,
  Attendance,
  AttendanceUpdate,
  BarcodeLookupResult,
  BulkImportResult,
  Campaign,
  CampaignCreate,
  CampaignDetail,
  CampaignReport,
  Category,
  Customer,
  CustomerAddress,
  CustomerBalanceAdjustment,
  CustomerBalanceType,
  CustomerLoyaltyAdjustment,
  CustomerPurchase,
  CurrentUser,
  DashboardSummary,
  DiscountApplyResult,
  DiscountRule,
  EmailProviderOut,
  EmailProviderType,
  EmailProviderUpdate,
  HardwareAiSettings,
  HardwareAiSettingsUpdate,
  LeaveRequest,
  LeaveRequestCreate,
  LeaveReview,
  MediaUploadResult,
  MessageTemplate,
  Outlet,
  PaymentMode,
  PaymentModeBreakdownItem,
  Payslip,
  PayslipGenerate,
  PayslipUpdate,
  Product,
  PublicBranding,
  ProductImage,
  PurchaseOrder,
  CreateOrderResponse,
  VerifyPaymentRequest,
  GlobalAuditLogEntry,
  LandingContent,
  LandingContentUpdate,
  LegalPage,
  LegalPageUpsert,
  PlatformDomainConfig,
  PlatformDomainConfigUpdate,
  PlatformEmailConfig,
  PlatformEmailConfigUpdate,
  Payment,
  PlatformOverview,
  PlatformPaymentConfig,
  PlatformPaymentConfigUpdate,
  PlatformTestResult,
  PlatformWebsiteConfig,
  PlatformWebsiteConfigUpdate,
  ReceiptSendResult,
  RegisterRequest,
  RegisterResponse,
  ReorderSuggestion,
  Return,
  Sale,
  SalesTrendPoint,
  SegmentParams,
  SegmentPreviewResult,
  SlugAvailability,
  SmsProviderOut,
  SmsProviderType,
  SmsProviderUpdate,
  StaffMember,
  StaffSalary,
  StaffSalaryUpdate,
  StockAgingItem,
  StockLevelDetail,
  Tenant,
  TenantCreate,
  TenantUpdate,
  TenantUsage,
  TenantSelf,
  TenantSelfUpdate,
  AuditLogEntry,
  TestResult,
  Transfer,
  Vendor,
  VendorProductLink,
  WhatsAppSendResult,
  Item,
  ItemUomConversion,
  Uom,
  UomCategory,
  VendorItem,
  Bom,
  BomAvailability,
  BomCost,
  BomDetail,
  BomDuplicateWarning,
  BomVersion,
  ProductionAvailability,
  ProductionHistoryEntry,
  ProductionOrder,
  ProductionOrderDetail,
  ProductionTraceStep,
  MaterialReservation,
  MaterialTxn,
  OrderMaterialSummary,
} from "./types";

// ---- Auth ----
export const login = (email: string, password: string) =>
  apiClient.post<{ access_token: string; token_type: string }>("/api/auth/login", { email, password });

export const getMe = () => apiClient.get<CurrentUser>("/api/auth/me");

export const registerStore = (data: RegisterRequest) =>
  apiClient.post<RegisterResponse>("/api/auth/register", data);

export const checkSlug = (slug: string) =>
  apiClient.get<SlugAvailability>("/api/auth/check-slug", { params: { slug } });

export const verifyEmail = (token: string) =>
  apiClient.get<{ access_token: string; token_type: string }>("/api/auth/verify-email", { params: { token } });

export const resendVerification = (email: string) =>
  apiClient.post<{ message: string }>("/api/auth/resend-verification", { email });

// ---- Outlets ----
export const listOutlets = () => apiClient.get<Outlet[]>("/api/outlets");
export const createOutlet = (data: Partial<Outlet>) => apiClient.post<Outlet>("/api/outlets", data);
export const updateOutlet = (id: number, data: Partial<Outlet>) =>
  apiClient.patch<Outlet>(`/api/outlets/${id}`, data);

// ---- Users ----
export const listUsers = () => apiClient.get<AppUser[]>("/api/users");
export const createUser = (data: Record<string, unknown>) => apiClient.post<AppUser>("/api/users", data);
export const updateUser = (id: number, data: Record<string, unknown>) =>
  apiClient.patch<AppUser>(`/api/users/${id}`, data);

// ---- Categories ----
export const listCategories = () => apiClient.get<Category[]>("/api/categories");
export const createCategory = (data: Partial<Category>) =>
  apiClient.post<Category>("/api/categories", data);

// ---- Products ----
export const listProducts = (params?: { search?: string; category_id?: number }) =>
  apiClient.get<Product[]>("/api/products", { params });
export const getProduct = (id: number) => apiClient.get<Product>(`/api/products/${id}`);
export const createProduct = (data: Record<string, unknown>) =>
  apiClient.post<Product>("/api/products", data);
export const updateProduct = (id: number, data: Record<string, unknown>) =>
  apiClient.patch<Product>(`/api/products/${id}`, data);
export const addVariant = (productId: number, data: Record<string, unknown>) =>
  apiClient.post(`/api/products/${productId}/variants`, data);
export const updateVariant = (variantId: number, data: Record<string, unknown>) =>
  apiClient.patch(`/api/products/variants/${variantId}`, data);
export const searchVariants = (q: string) =>
  apiClient.get(`/api/products/variants/search`, { params: { q } });
export const printLabels = (data: { items: { variant_id: number; quantity: number }[]; layout: string }) =>
  apiClient.post("/api/products/labels/pdf", data, { responseType: "blob" });
export const bulkImportTemplateUrl = () => `${apiClient.defaults.baseURL}/api/products/bulk-import/template`;
export const bulkImportProducts = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return apiClient.post<BulkImportResult>("/api/products/bulk-import", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};

// ---- Product images ----
export const productImageUrl = (url: string) => `${apiClient.defaults.baseURL}${url}`;
export const uploadProductImage = (
  productId: number,
  file: File,
  data?: { color?: string; angle?: string }
) => {
  const form = new FormData();
  form.append("file", file);
  if (data?.color) form.append("color", data.color);
  if (data?.angle) form.append("angle", data.angle);
  return apiClient.post<ProductImage>(`/api/products/${productId}/images`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};
export const updateProductImage = (
  imageId: number,
  data: { color?: string | null; angle?: string; is_primary?: boolean; sort_order?: number }
) => apiClient.patch<ProductImage>(`/api/products/images/${imageId}`, data);
export const deleteProductImage = (imageId: number) =>
  apiClient.delete(`/api/products/images/${imageId}`);

// ---- Inventory ----
export const listStock = (params?: { outlet_id?: number; variant_id?: number }) =>
  apiClient.get<StockLevelDetail[]>("/api/inventory/stock", { params });
export const adjustStock = (data: { variant_id: number; outlet_id: number; quantity_delta: number; note?: string }) =>
  apiClient.post("/api/inventory/adjust", data);

// ---- Vendors ----
export const listVendors = () => apiClient.get<Vendor[]>("/api/vendors");
export const createVendor = (data: Partial<Vendor>) => apiClient.post<Vendor>("/api/vendors", data);
export const updateVendor = (id: number, data: Partial<Vendor>) =>
  apiClient.patch<Vendor>(`/api/vendors/${id}`, data);
export const listVendorProducts = (vendorId: number) =>
  apiClient.get<VendorProductLink[]>(`/api/vendors/${vendorId}/products`);
export const linkVendorProduct = (data: {
  vendor_id: number;
  variant_id: number;
  vendor_sku?: string;
  cost_price: number;
  is_preferred: boolean;
}) => apiClient.post<VendorProductLink>("/api/vendors/products", data);
export const unlinkVendorProduct = (linkId: number) =>
  apiClient.delete(`/api/vendors/products/${linkId}`);

// ---- Customers ----
export const listCustomers = (params?: { search?: string; tag?: string }) =>
  apiClient.get<Customer[]>("/api/customers", { params });
export const getCustomer = (id: number) => apiClient.get<Customer>(`/api/customers/${id}`);
export const createCustomer = (data: Record<string, unknown>) =>
  apiClient.post<Customer>("/api/customers", data);
export const updateCustomer = (id: number, data: Record<string, unknown>) =>
  apiClient.patch<Customer>(`/api/customers/${id}`, data);

export const listCustomerAddresses = (customerId: number) =>
  apiClient.get<CustomerAddress[]>(`/api/customers/${customerId}/addresses`);
export const createCustomerAddress = (
  data: Partial<CustomerAddress> & { customer_id: number; line1: string }
) => apiClient.post<CustomerAddress>("/api/customers/addresses", data);
export const updateCustomerAddress = (addressId: number, data: Partial<CustomerAddress>) =>
  apiClient.patch<CustomerAddress>(`/api/customers/addresses/${addressId}`, data);
export const deleteCustomerAddress = (addressId: number) =>
  apiClient.delete(`/api/customers/addresses/${addressId}`);

export const listCustomerPurchases = (customerId: number) =>
  apiClient.get<CustomerPurchase[]>(`/api/customers/${customerId}/purchases`);

export const adjustCustomerBalance = (
  customerId: number,
  data: { balance_type: CustomerBalanceType; amount_delta: number; reason?: string }
) => apiClient.post<CustomerBalanceAdjustment>(`/api/customers/${customerId}/adjust-balance`, data);
export const listCustomerBalanceAdjustments = (customerId: number) =>
  apiClient.get<CustomerBalanceAdjustment[]>(`/api/customers/${customerId}/balance-adjustments`);

export const adjustCustomerLoyalty = (
  customerId: number,
  data: { points_delta: number; reason?: string }
) => apiClient.post<CustomerLoyaltyAdjustment>(`/api/customers/${customerId}/adjust-loyalty`, data);
export const listCustomerLoyaltyAdjustments = (customerId: number) =>
  apiClient.get<CustomerLoyaltyAdjustment[]>(`/api/customers/${customerId}/loyalty-adjustments`);

// ---- Purchase Orders ----
export const listPurchaseOrders = (params?: { status?: string; vendor_id?: number }) =>
  apiClient.get<PurchaseOrder[]>("/api/purchase-orders", { params });
export const getPurchaseOrder = (id: number) =>
  apiClient.get<PurchaseOrder>(`/api/purchase-orders/${id}`);
export const createPurchaseOrder = (data: Record<string, unknown>) =>
  apiClient.post<PurchaseOrder>("/api/purchase-orders", data);
export const getReorderSuggestions = (params?: { outlet_id?: number; vendor_id?: number }) =>
  apiClient.get<ReorderSuggestion[]>("/api/purchase-orders/reorder-suggestions", { params });
export const purchaseOrderPdfUrl = (id: number) => `${apiClient.defaults.baseURL}/api/purchase-orders/${id}/pdf`;
export const sendPurchaseOrderWhatsApp = (id: number) =>
  apiClient.post<WhatsAppSendResult>(`/api/purchase-orders/${id}/send-whatsapp`);
export const receiveGoods = (id: number, items: { item_id: number; quantity_received: number }[]) =>
  apiClient.post<PurchaseOrder>(`/api/purchase-orders/${id}/receive`, { items });

// ---- Transfers ----
export const listTransfers = (params?: { status?: string; outlet_id?: number }) =>
  apiClient.get<Transfer[]>("/api/transfers", { params });
export const getTransfer = (id: number) => apiClient.get<Transfer>(`/api/transfers/${id}`);
export const createTransfer = (data: Record<string, unknown>) =>
  apiClient.post<Transfer>("/api/transfers", data);
export const updateTransfer = (id: number, data: Record<string, unknown>) =>
  apiClient.patch<Transfer>(`/api/transfers/${id}`, data);
export const cancelTransfer = (id: number) => apiClient.post<Transfer>(`/api/transfers/${id}/cancel`);
export const dispatchTransfer = (id: number, items: { item_id: number; quantity_sent: number }[]) =>
  apiClient.post<Transfer>(`/api/transfers/${id}/dispatch`, { items });
export const receiveTransfer = (id: number, items: { item_id: number; quantity_received: number }[]) =>
  apiClient.post<Transfer>(`/api/transfers/${id}/receive`, { items });

// ---- Sales / POS ----
export const lookupBarcode = (code: string, outletId: number) =>
  apiClient.get<BarcodeLookupResult>(`/api/sales/barcode/${encodeURIComponent(code)}`, {
    params: { outlet_id: outletId },
  });
export const searchProductsForPos = (q: string, outletId: number) =>
  apiClient.get<BarcodeLookupResult[]>("/api/sales/search-products", { params: { q, outlet_id: outletId } });
export const checkout = (data: Record<string, unknown>) => apiClient.post<Sale>("/api/sales", data);
export const listSales = (params?: {
  outlet_id?: number;
  search?: string;
  start_date?: string;
  end_date?: string;
  payment_mode?: PaymentMode;
}) => apiClient.get<Sale[]>("/api/sales", { params });
export const getSale = (id: number) => apiClient.get<Sale>(`/api/sales/${id}`);
export const receiptPdfUrl = (id: number) => `${apiClient.defaults.baseURL}/api/sales/${id}/receipt/pdf`;
export const sendReceiptWhatsApp = (id: number) =>
  apiClient.post<ReceiptSendResult>(`/api/sales/${id}/send-whatsapp`);
export const sendReceiptSms = (id: number) => apiClient.post<ReceiptSendResult>(`/api/sales/${id}/send-sms`);
export const sendReceiptEmail = (id: number) => apiClient.post<ReceiptSendResult>(`/api/sales/${id}/send-email`);

// ---- Returns & Exchanges ----
export const listReturns = (params?: { sale_id?: number; outlet_id?: number; customer_id?: number }) =>
  apiClient.get<Return[]>("/api/returns", { params });
export const getReturn = (id: number) => apiClient.get<Return>(`/api/returns/${id}`);
export const createReturn = (data: Record<string, unknown>) => apiClient.post<Return>("/api/returns", data);

// ---- Transfer PDF ----
export const transferPdfUrl = (id: number) => `${apiClient.defaults.baseURL}/api/transfers/${id}/pdf`;

// ---- Discounts ----
export const listDiscountRules = () => apiClient.get<DiscountRule[]>("/api/discounts");
export const createDiscountRule = (data: Record<string, unknown>) =>
  apiClient.post<DiscountRule>("/api/discounts", data);
export const updateDiscountRule = (id: number, data: Record<string, unknown>) =>
  apiClient.patch<DiscountRule>(`/api/discounts/${id}`, data);
export const applyDiscount = (data: {
  items: { variant_id: number; quantity: number; unit_price: number }[];
  customer_id?: number;
  coupon_code?: string;
}) => apiClient.post<DiscountApplyResult>("/api/discounts/apply", data);

// ---- WhatsApp Campaigns ----
export const previewSegment = (data: SegmentParams) =>
  apiClient.post<SegmentPreviewResult>("/api/campaigns/preview", data);
export const listCampaigns = () => apiClient.get<Campaign[]>("/api/campaigns");
export const getCampaign = (id: number) => apiClient.get<CampaignDetail>(`/api/campaigns/${id}`);
export const createCampaign = (data: CampaignCreate) => apiClient.post<CampaignDetail>("/api/campaigns", data);
export const getCampaignReport = (id: number) => apiClient.get<CampaignReport>(`/api/campaigns/${id}/report`);
export const listCampaignPlaceholders = () => apiClient.get<Record<string, string>>("/api/campaigns/placeholders");
export const uploadCampaignMedia = (file: File) => {
  const formData = new FormData();
  formData.append("file", file);
  return apiClient.post<MediaUploadResult>("/api/campaigns/upload-media", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};

export const listMessageTemplates = () => apiClient.get<MessageTemplate[]>("/api/message-templates");
export const createMessageTemplate = (data: { name: string; body: string }) =>
  apiClient.post<MessageTemplate>("/api/message-templates", data);
export const deleteMessageTemplate = (id: number) => apiClient.delete(`/api/message-templates/${id}`);

// ---- Alterations ----
export const listAlterations = (params?: { outlet_id?: number; status?: AlterationStatus; customer_id?: number }) =>
  apiClient.get<Alteration[]>("/api/alterations", { params });
export const createAlteration = (data: Record<string, unknown>) =>
  apiClient.post<Alteration>("/api/alterations", data);
export const updateAlteration = (id: number, data: Record<string, unknown>) =>
  apiClient.patch<Alteration>(`/api/alterations/${id}`, data);

// ---- Export ----
export type ExportFormat = "csv" | "xlsx" | "pdf";
export const exportData = (url: string, params: Record<string, unknown>, format: ExportFormat) =>
  apiClient.get(url, { params: { ...params, format }, responseType: "blob" });

// ---- Reports ----
export const getStockAging = (params?: { outlet_id?: number }) =>
  apiClient.get<StockAgingItem[]>("/api/reports/stock-aging", { params });
export const getDeadStock = (params?: { outlet_id?: number; days?: number }) =>
  apiClient.get<StockAgingItem[]>("/api/reports/dead-stock", { params });
export const getSalesTrend = (params?: { days?: number; outlet_id?: number }) =>
  apiClient.get<SalesTrendPoint[]>("/api/reports/sales-trend", { params });
export const getPaymentModeBreakdown = (params?: { days?: number; outlet_id?: number }) =>
  apiClient.get<PaymentModeBreakdownItem[]>("/api/reports/payment-mode-breakdown", { params });

// ---- Dashboard ----
export const getDashboardSummary = () => apiClient.get<DashboardSummary>("/api/dashboard/summary");

// ---- Settings ----
export const getAppSettings = () => apiClient.get<AppSettings>("/api/settings");
export const updateAppSettings = (data: Record<string, unknown>) =>
  apiClient.patch<AppSettings>("/api/settings", data);
export const getPublicBranding = (slug?: string) =>
  apiClient.get<PublicBranding>("/api/settings/public", { params: slug ? { slug } : {} });
export const uploadLogo = (file: File) => {
  const formData = new FormData();
  formData.append("file", file);
  return apiClient.post<AppSettings>("/api/settings/logo", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};
export const removeLogo = () => apiClient.delete<AppSettings>("/api/settings/logo");
export const listPresetLogos = () => apiClient.get<string[]>("/api/settings/logo/presets");
export const selectPresetLogo = (url: string) =>
  apiClient.put<AppSettings>("/api/settings/logo/preset", null, { params: { url } });

export const getHardwareAiSettings = () => apiClient.get<HardwareAiSettings>("/api/settings/hardware-ai");
export const updateHardwareAiSettings = (data: HardwareAiSettingsUpdate) =>
  apiClient.patch<HardwareAiSettings>("/api/settings/hardware-ai", data);

// ---- Integrations (Email / SMS) ----
export const listEmailProviders = () => apiClient.get<EmailProviderOut[]>("/api/integrations/email");
export const updateEmailProvider = (provider: EmailProviderType, data: EmailProviderUpdate) =>
  apiClient.patch<EmailProviderOut>(`/api/integrations/email/${provider}`, data);
export const testEmailProvider = (provider: EmailProviderType, to_email: string) =>
  apiClient.post<TestResult>(`/api/integrations/email/${provider}/test`, { to_email });

export const listSmsProviders = () => apiClient.get<SmsProviderOut[]>("/api/integrations/sms");
export const updateSmsProvider = (provider: SmsProviderType, data: SmsProviderUpdate) =>
  apiClient.patch<SmsProviderOut>(`/api/integrations/sms/${provider}`, data);
export const testSmsProvider = (provider: SmsProviderType, to_number: string) =>
  apiClient.post<TestResult>(`/api/integrations/sms/${provider}/test`, { to_number });

// ---- HRM ----
export const listStaff = () => apiClient.get<StaffMember[]>("/api/hrm/staff");
export const checkIn = () => apiClient.post<Attendance>("/api/hrm/attendance/check-in");
export const checkOut = () => apiClient.post<Attendance>("/api/hrm/attendance/check-out");
export const getMyAttendance = (days = 30) => apiClient.get<Attendance[]>("/api/hrm/attendance/me", { params: { days } });
export const listAttendance = (params?: { staff_id?: number; outlet_id?: number; month?: string }) =>
  apiClient.get<Attendance[]>("/api/hrm/attendance", { params });
export const updateAttendance = (id: number, data: AttendanceUpdate) =>
  apiClient.patch<Attendance>(`/api/hrm/attendance/${id}`, data);

export const createLeaveRequest = (data: LeaveRequestCreate) =>
  apiClient.post<LeaveRequest>("/api/hrm/leave-requests", data);
export const getMyLeaveRequests = () => apiClient.get<LeaveRequest[]>("/api/hrm/leave-requests/me");
export const listLeaveRequests = (params?: { status?: string; staff_id?: number }) =>
  apiClient.get<LeaveRequest[]>("/api/hrm/leave-requests", { params });
export const reviewLeaveRequest = (id: number, data: LeaveReview) =>
  apiClient.patch<LeaveRequest>(`/api/hrm/leave-requests/${id}/review`, data);

// ---- Payroll ----
export const listSalaries = () => apiClient.get<StaffSalary[]>("/api/payroll/salaries");
export const updateSalary = (staffId: number, data: StaffSalaryUpdate) =>
  apiClient.patch<StaffSalary>(`/api/payroll/salaries/${staffId}`, data);
export const listPayslips = (params?: { month?: string; staff_id?: number }) =>
  apiClient.get<Payslip[]>("/api/payroll/payslips", { params });
export const generatePayslips = (data: PayslipGenerate) =>
  apiClient.post<Payslip[]>("/api/payroll/payslips/generate", data);
export const updatePayslip = (id: number, data: PayslipUpdate) =>
  apiClient.patch<Payslip>(`/api/payroll/payslips/${id}`, data);

// ---- Super Admin ----
export const listTenants = (q?: string) => apiClient.get<Tenant[]>("/api/admin/tenants", { params: { q } });
export const createTenant = (data: TenantCreate) => apiClient.post<Tenant>("/api/admin/tenants", data);
export const getTenant = (id: number) => apiClient.get<Tenant>(`/api/admin/tenants/${id}`);
export const updateTenant = (id: number, data: TenantUpdate) =>
  apiClient.patch<Tenant>(`/api/admin/tenants/${id}`, data);
export const suspendTenant = (id: number) => apiClient.post<Tenant>(`/api/admin/tenants/${id}/suspend`);
export const deleteTenant = (id: number) => apiClient.delete<Tenant>(`/api/admin/tenants/${id}`);
export const getTenantUsage = (id: number) => apiClient.get<TenantUsage>(`/api/admin/tenants/${id}/usage`);
export const getTenantActivity = (id: number, limit = 100) =>
  apiClient.get<AuditLogEntry[]>(`/api/admin/tenants/${id}/activity`, { params: { limit } });
export const listTenantUsers = (id: number) => apiClient.get<AppUser[]>(`/api/admin/tenants/${id}/users`);
export const resetTenantUserPassword = (tenantId: number, userId: number, new_password: string) =>
  apiClient.post<{ ok: boolean }>(`/api/admin/tenants/${tenantId}/users/${userId}/reset-password`, {
    new_password,
  });
export const getPlatformOverview = () => apiClient.get<PlatformOverview>("/api/admin/overview");
export const getGlobalActivity = (limit = 100) =>
  apiClient.get<GlobalAuditLogEntry[]>("/api/admin/activity", { params: { limit } });
export const listPayments = (limit = 100) =>
  apiClient.get<Payment[]>("/api/admin/payments", { params: { limit } });

// ---- Super Admin: Global Settings (Payment / Email / Website / Domain) ----
export const getPlatformEmailConfig = () => apiClient.get<PlatformEmailConfig>("/api/admin/settings/email");
export const updatePlatformEmailConfig = (data: PlatformEmailConfigUpdate) =>
  apiClient.patch<PlatformEmailConfig>("/api/admin/settings/email", data);
export const testPlatformEmailConfig = (to_email: string) =>
  apiClient.post<PlatformTestResult>("/api/admin/settings/email/test", { to_email });

export const getPlatformPaymentConfig = () => apiClient.get<PlatformPaymentConfig>("/api/admin/settings/payment");
export const updatePlatformPaymentConfig = (data: PlatformPaymentConfigUpdate) =>
  apiClient.patch<PlatformPaymentConfig>("/api/admin/settings/payment", data);
export const testPlatformPaymentConfig = () =>
  apiClient.post<PlatformTestResult>("/api/admin/settings/payment/test");

export const getPlatformWebsiteConfig = () => apiClient.get<PlatformWebsiteConfig>("/api/admin/settings/website");
export const updatePlatformWebsiteConfig = (data: PlatformWebsiteConfigUpdate) =>
  apiClient.patch<PlatformWebsiteConfig>("/api/admin/settings/website", data);

export const getPlatformDomainConfig = () => apiClient.get<PlatformDomainConfig>("/api/admin/settings/domain");
export const updatePlatformDomainConfig = (data: PlatformDomainConfigUpdate) =>
  apiClient.patch<PlatformDomainConfig>("/api/admin/settings/domain", data);

// ---- Super Admin: Landing Page CMS + legal pages ----
export const getAdminLandingContent = () => apiClient.get<LandingContent>("/api/admin/landing-content");
export const updateLandingContent = (data: LandingContentUpdate) =>
  apiClient.patch<LandingContent>("/api/admin/landing-content", data);
export const listAdminLegalPages = () => apiClient.get<LegalPage[]>("/api/admin/legal-pages");
export const upsertLegalPage = (slug: string, data: LegalPageUpsert) =>
  apiClient.put<LegalPage>(`/api/admin/legal-pages/${slug}`, data);

// ---- Public: Landing Page content + legal pages ----
export const getPublicLandingContent = () => apiClient.get<LandingContent>("/api/landing-content");
export const getPublicLegalPage = (slug: string) => apiClient.get<LegalPage>(`/api/legal/${slug}`);

// ---- Billing (Razorpay) ----
export const createBillingOrder = (slug: string) =>
  apiClient.post<CreateOrderResponse>("/api/billing/create-order", { slug });
export const verifyBillingPayment = (data: VerifyPaymentRequest) =>
  apiClient.post<{ ok: boolean }>("/api/billing/verify-payment", data);

// ---- Tenant self-service (the tenant's own users, not Super Admin) ----
export const getMyTenant = () => apiClient.get<TenantSelf>("/api/tenant/me");
export const updateMyTenant = (data: TenantSelfUpdate) => apiClient.patch<TenantSelf>("/api/tenant/me", data);

// ---- Item Master & Units of Measure (Phase 2) ----
export const listItems = (params?: {
  item_type?: string;
  category_id?: number;
  is_active?: boolean;
  low_stock?: boolean;
  q?: string;
}) => apiClient.get<Item[]>("/api/items", { params });
export const getItem = (id: number) => apiClient.get<Item>(`/api/items/${id}`);
export const createItem = (data: Partial<Item>) => apiClient.post<Item>("/api/items", data);
export const updateItem = (id: number, data: Partial<Item>) =>
  apiClient.patch<Item>(`/api/items/${id}`, data);

export const listItemConversions = (id: number) =>
  apiClient.get<ItemUomConversion[]>(`/api/items/${id}/conversions`);
export const addItemConversion = (
  id: number,
  data: { from_uom_id: number; to_uom_id: number; factor: number; vendor_id?: number | null },
) => apiClient.post<ItemUomConversion>(`/api/items/${id}/conversions`, data);

export const listItemVendors = (id: number) => apiClient.get<VendorItem[]>(`/api/items/${id}/vendors`);
export const addItemVendor = (id: number, data: Partial<VendorItem>) =>
  apiClient.post<VendorItem>(`/api/items/${id}/vendors`, data);

export const listUoms = (params?: { category_id?: number; is_active?: boolean }) =>
  apiClient.get<Uom[]>("/api/uom", { params });
export const createUom = (data: Partial<Uom>) => apiClient.post<Uom>("/api/uom", data);
export const updateUom = (id: number, data: Partial<Uom>) => apiClient.patch<Uom>(`/api/uom/${id}`, data);
export const listUomCategories = () => apiClient.get<UomCategory[]>("/api/uom/categories");
export const createUomCategory = (data: { code: string; name: string }) =>
  apiClient.post<UomCategory>("/api/uom/categories", data);
export const convertUom = (data: {
  quantity: number;
  from_uom_id: number;
  to_uom_id: number;
  item_id?: number | null;
  vendor_id?: number | null;
}) => apiClient.post<{ quantity: number; from_uom: string; to_uom: string }>("/api/uom/convert", data);

// ---- BOM (Phase 3B) ----
export const listBoms = (params?: { q?: string; item_id?: number; limit?: number; offset?: number }) =>
  apiClient.get<Bom[]>("/api/boms", { params });
export const getBom = (id: number) => apiClient.get<BomDetail>(`/api/boms/${id}`);
export const createBom = (data: {
  item_id: number;
  name: string;
  description?: string | null;
  output_quantity?: number;
  output_uom_id?: number | null;
  components?: unknown[];
}) => apiClient.post<BomDetail>("/api/boms", data);

export const getBomVersion = (bomId: number, versionId: number) =>
  apiClient.get<BomVersion>(`/api/boms/${bomId}/versions/${versionId}`);
export const createBomVersion = (
  bomId: number,
  data: { output_quantity?: number; output_uom_id?: number | null; notes?: string | null; copy_from_version_id?: number | null },
) => apiClient.post<BomVersion>(`/api/boms/${bomId}/versions`, data);
export const replaceBomComponents = (bomId: number, versionId: number, components: unknown[]) =>
  apiClient.put<BomVersion>(`/api/boms/${bomId}/versions/${versionId}/components`, { components });
export const activateBomVersion = (bomId: number, versionId: number) =>
  apiClient.post<BomVersion>(`/api/boms/${bomId}/versions/${versionId}/activate`);
export const archiveBomVersion = (bomId: number, versionId: number) =>
  apiClient.post<BomVersion>(`/api/boms/${bomId}/versions/${versionId}/archive`);

export const getBomCost = (bomId: number, params?: { quantity?: number; version_id?: number }) =>
  apiClient.get<BomCost>(`/api/boms/${bomId}/cost`, { params });
export const getBomAvailability = (bomId: number, params?: { quantity?: number; outlet_id?: number; version_id?: number }) =>
  apiClient.get<BomAvailability>(`/api/boms/${bomId}/availability`, { params });
export const getBomDuplicates = (bomId: number, params?: { version_id?: number }) =>
  apiClient.get<BomDuplicateWarning[]>(`/api/boms/${bomId}/duplicates`, { params });

// ---- Production orders (Phase 3C) ----
export const listProductionOrders = (params?: {
  status?: string; item_id?: number; location_id?: number; priority?: string; q?: string;
}) => apiClient.get<ProductionOrder[]>("/api/production-orders", { params });
export const getProductionOrder = (id: number) =>
  apiClient.get<ProductionOrderDetail>(`/api/production-orders/${id}`);
export const createProductionOrder = (data: {
  item_id: number; planned_quantity: number; location_id: number;
  bom_version_id?: number | null; planned_start?: string | null;
  planned_completion?: string | null; priority?: string; notes?: string | null;
}) => apiClient.post<ProductionOrderDetail>("/api/production-orders", data);
export const updateProductionOrder = (id: number, data: Record<string, unknown>) =>
  apiClient.patch<ProductionOrderDetail>(`/api/production-orders/${id}`, data);

export const planProductionOrder = (id: number) =>
  apiClient.post<ProductionOrderDetail>(`/api/production-orders/${id}/plan`);
export const releaseProductionOrder = (id: number) =>
  apiClient.post<ProductionOrderDetail>(`/api/production-orders/${id}/release`);
export const startProductionOrder = (id: number) =>
  apiClient.post<ProductionOrderDetail>(`/api/production-orders/${id}/start`);
export const holdProductionOrder = (id: number, reason?: string) =>
  apiClient.post<ProductionOrderDetail>(`/api/production-orders/${id}/hold`, { reason });
export const resumeProductionOrder = (id: number) =>
  apiClient.post<ProductionOrderDetail>(`/api/production-orders/${id}/resume`);
export const cancelProductionOrder = (id: number, reason?: string) =>
  apiClient.post<ProductionOrderDetail>(`/api/production-orders/${id}/cancel`, { reason });
export const closeShortProductionOrder = (
  id: number, data: { produced_quantity: number; reason: string },
) => apiClient.post<ProductionOrderDetail>(`/api/production-orders/${id}/close-short`, data);

export const getProductionAvailability = (id: number) =>
  apiClient.get<ProductionAvailability>(`/api/production-orders/${id}/availability`);
export const getProductionHistory = (id: number) =>
  apiClient.get<ProductionHistoryEntry[]>(`/api/production-orders/${id}/history`);
export const getProductionTrace = (id: number, itemId: number) =>
  apiClient.get<ProductionTraceStep[][]>(`/api/production-orders/${id}/trace/${itemId}`);

// ---- Material flow (Phase 3D) ----
export const getOrderMaterials = (id: number) =>
  apiClient.get<OrderMaterialSummary>(`/api/production-orders/${id}/materials`);
export const listReservations = (id: number) =>
  apiClient.get<MaterialReservation[]>(`/api/production-orders/${id}/reservations`);
export const listMaterialIssues = (id: number) =>
  apiClient.get<MaterialTxn[]>(`/api/production-orders/${id}/issues`);
export const listMaterialConsumption = (id: number) =>
  apiClient.get<MaterialTxn[]>(`/api/production-orders/${id}/consumption`);
export const listMaterialReturns = (id: number) =>
  apiClient.get<MaterialTxn[]>(`/api/production-orders/${id}/returns`);

export const reserveMaterials = (
  id: number, lines: { material_id: number; quantity: number; note?: string | null }[],
) => apiClient.post<OrderMaterialSummary>(`/api/production-orders/${id}/reserve`, { lines });
export const releaseReservations = (
  id: number, data: { reservation_ids?: number[]; reason?: string | null },
) => apiClient.post<OrderMaterialSummary>(`/api/production-orders/${id}/release-reservation`, data);
export const issueMaterials = (
  id: number,
  lines: { material_id: number; quantity: number; allow_unreserved?: boolean; unreserved_reason?: string | null; note?: string | null }[],
) => apiClient.post<OrderMaterialSummary>(`/api/production-orders/${id}/issue`, { lines });
export const consumeMaterials = (
  id: number,
  lines: { material_id: number; quantity: number; allow_over_consumption?: boolean; over_consumption_reason?: string | null }[],
) => apiClient.post<OrderMaterialSummary>(`/api/production-orders/${id}/consume`, { lines });
export const returnMaterials = (
  id: number,
  lines: { material_id: number; quantity: number; reason?: string | null; restock?: boolean }[],
) => apiClient.post<OrderMaterialSummary>(`/api/production-orders/${id}/return`, { lines });
