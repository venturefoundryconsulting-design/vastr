// super_admin is deliberately not part of this type - it's a platform-level
// role, not a tenant-scoped one, and is checked separately (see
// admin/RequireSuperAdmin.tsx) rather than through the tenant rank ladder
// (utils/roles.ts) that this type feeds.
export type UserRole = "tenant_owner" | "admin" | "manager" | "sales" | "inventory" | "outlet_staff" | "viewer";

export type PaperSize = "a4" | "thermal_58" | "thermal_80";

export interface Outlet {
  id: number;
  name: string;
  code: string;
  address?: string | null;
  phone?: string | null;
  is_warehouse: boolean;
  is_active: boolean;
  receipt_paper_size: PaperSize;
  transfer_paper_size: PaperSize;
}

export interface CurrentUser {
  id: number;
  name: string;
  email: string;
  role: UserRole;
  outlet_id?: number | null;
  tenant_id?: number | null;
}

export interface AppUser extends CurrentUser {
  is_active: boolean;
}

export interface Category {
  id: number;
  name: string;
  parent_id?: number | null;
}

export interface Variant {
  id: number;
  product_id: number;
  sku: string;
  barcode?: string | null;
  size?: string | null;
  color?: string | null;
  cost_price: number;
  selling_price: number;
  mrp: number;
  reorder_level: number;
  is_active: boolean;
}

export interface VariantWithStock extends Variant {
  product_name: string;
  total_stock: number;
}

export type ImageAngle = "front" | "back" | "side" | "detail" | "other";

export interface ProductImage {
  id: number;
  product_id: number;
  color?: string | null;
  angle: ImageAngle;
  url: string;
  is_primary: boolean;
  sort_order: number;
}

export interface Product {
  id: number;
  name: string;
  category_id?: number | null;
  brand?: string | null;
  description?: string | null;
  hsn_code?: string | null;
  tax_rate: number;
  is_active: boolean;
  variants: Variant[];
  images: ProductImage[];
}

export interface StockLevelDetail {
  id: number;
  variant_id: number;
  outlet_id: number;
  quantity: number;
  sku: string;
  product_name: string;
  size?: string | null;
  color?: string | null;
  outlet_name: string;
  reorder_level: number;
}

export interface LowStockItem {
  variant_id: number;
  sku: string;
  product_name: string;
  size?: string | null;
  color?: string | null;
  outlet_id: number;
  outlet_name: string;
  quantity: number;
  reorder_level: number;
  preferred_vendor_id?: number | null;
  preferred_vendor_name?: string | null;
}

export interface Vendor {
  id: number;
  name: string;
  contact_person?: string | null;
  whatsapp_number?: string | null;
  phone?: string | null;
  email?: string | null;
  address?: string | null;
  gstin?: string | null;
  payment_terms?: string | null;
  is_active: boolean;
}

export interface VendorProductLink {
  id: number;
  vendor_id: number;
  variant_id: number;
  vendor_sku?: string | null;
  cost_price: number;
  is_preferred: boolean;
  sku?: string | null;
  product_name?: string | null;
}

export type PurchaseOrderStatus =
  | "draft"
  | "sent"
  | "confirmed"
  | "partially_received"
  | "received"
  | "cancelled";

export interface PurchaseOrderItem {
  id: number;
  variant_id: number;
  quantity_ordered: number;
  quantity_received: number;
  unit_cost: number;
  tax_rate: number;
  amount: number;
  sku?: string | null;
  product_name?: string | null;
}

export interface PurchaseOrder {
  id: number;
  po_number: string;
  vendor_id: number;
  vendor_name?: string | null;
  outlet_id: number;
  outlet_name?: string | null;
  status: PurchaseOrderStatus;
  order_date: string;
  expected_date?: string | null;
  notes?: string | null;
  total_amount: number;
  items: PurchaseOrderItem[];
}

export interface ReorderSuggestionItem {
  variant_id: number;
  sku: string;
  product_name: string;
  size?: string | null;
  color?: string | null;
  outlet_id: number;
  outlet_name: string;
  current_quantity: number;
  reorder_level: number;
  suggested_quantity: number;
  cost_price: number;
}

export interface ReorderSuggestion {
  vendor_id: number;
  vendor_name: string;
  items: ReorderSuggestionItem[];
}

export type TransferStatus = "requested" | "dispatched" | "received" | "cancelled";

export interface TransferItem {
  id: number;
  variant_id: number;
  quantity_requested: number;
  quantity_sent: number;
  quantity_received: number;
  sku?: string | null;
  product_name?: string | null;
}

export interface Transfer {
  id: number;
  transfer_number: string;
  source_outlet_id: number;
  source_outlet_name?: string | null;
  dest_outlet_id: number;
  dest_outlet_name?: string | null;
  status: TransferStatus;
  notes?: string | null;
  dispatched_at?: string | null;
  received_at?: string | null;
  items: TransferItem[];
}

export type PaymentMode = "cash" | "card" | "upi" | "other";

export interface SaleItem {
  id: number;
  variant_id: number;
  quantity: number;
  unit_price: number;
  tax_rate: number;
  sku?: string | null;
  product_name?: string | null;
}

export interface Sale {
  id: number;
  invoice_number: string;
  outlet_id: number;
  outlet_name?: string | null;
  customer_id?: number | null;
  customer_name?: string | null;
  customer_phone?: string | null;
  customer_email?: string | null;
  discount_amount: number;
  coupon_code?: string | null;
  rule_discount_amount: number;
  discount_rule_name?: string | null;
  credit_applied: number;
  points_redeemed: number;
  loyalty_points_earned: number;
  payment_mode: PaymentMode;
  subtotal: number;
  tax_amount: number;
  total: number;
  created_at: string;
  items: SaleItem[];
}

export type RefundMode = "cash" | "store_credit";

export interface ReturnLineItem {
  id: number;
  sale_item_id: number;
  variant_id: number;
  quantity: number;
  unit_price: number;
  tax_rate: number;
  restock: boolean;
  sku?: string | null;
  product_name?: string | null;
}

export interface ExchangeLineItem {
  id: number;
  variant_id: number;
  quantity: number;
  unit_price: number;
  tax_rate: number;
  sku?: string | null;
  product_name?: string | null;
}

export interface Return {
  id: number;
  return_number: string;
  sale_id: number;
  sale_invoice_number?: string | null;
  outlet_id: number;
  outlet_name?: string | null;
  customer_id?: number | null;
  customer_name?: string | null;
  reason?: string | null;
  refund_mode?: RefundMode | null;
  payment_mode?: PaymentMode | null;
  returned_value: number;
  exchanged_value: number;
  difference: number;
  created_by_id?: number | null;
  created_at: string;
  return_items: ReturnLineItem[];
  exchange_items: ExchangeLineItem[];
}

export interface BarcodeLookupResult {
  variant_id: number;
  sku: string;
  barcode?: string | null;
  product_name: string;
  size?: string | null;
  color?: string | null;
  selling_price: number;
  tax_rate: number;
  available_quantity: number;
}

export interface DashboardSummary {
  total_outlets: number;
  total_products: number;
  total_variants: number;
  low_stock_count: number;
  open_purchase_orders: number;
  in_transit_transfers: number;
  sales_today_count: number;
  sales_today_total: number;
  low_stock_items: LowStockItem[];
  recent_purchase_orders: PurchaseOrder[];
  recent_transfers: Transfer[];
}

export type CustomerBalanceType = "credit" | "outstanding";

export interface CustomerAddress {
  id: number;
  customer_id: number;
  label?: string | null;
  line1: string;
  line2?: string | null;
  city?: string | null;
  state?: string | null;
  pincode?: string | null;
  is_default: boolean;
}

export interface Customer {
  id: number;
  name: string;
  phone?: string | null;
  email?: string | null;
  whatsapp_number?: string | null;
  is_gst_customer: boolean;
  gstin?: string | null;
  birthday?: string | null;
  anniversary?: string | null;
  preferred_sizes: string[];
  preferred_colors: string[];
  favorite_brands: string[];
  tags: string[];
  notes?: string | null;
  credit_balance: number;
  loyalty_points: number;
  is_vip: boolean;
  is_active: boolean;
}

export interface CustomerBalanceAdjustment {
  id: number;
  customer_id: number;
  balance_type: CustomerBalanceType;
  amount_delta: number;
  reference_type?: string | null;
  reference_id?: number | null;
  reason?: string | null;
  created_by_id?: number | null;
  created_at: string;
}

export interface CustomerLoyaltyAdjustment {
  id: number;
  customer_id: number;
  points_delta: number;
  reference_type?: string | null;
  reference_id?: number | null;
  reason?: string | null;
  created_by_id?: number | null;
  created_at: string;
}

export interface CustomerPurchase {
  sale_id: number;
  invoice_number: string;
  outlet_id: number;
  outlet_name?: string | null;
  total: number;
  payment_mode: PaymentMode;
  created_at: string;
}

export type DiscountType = "percentage" | "flat" | "bogo";
export type DiscountScope = "all" | "category" | "brand" | "product";

export interface DiscountRule {
  id: number;
  name: string;
  code?: string | null;
  discount_type: DiscountType;
  scope: DiscountScope;
  category_id?: number | null;
  brand?: string | null;
  product_id?: number | null;
  vip_only: boolean;
  value: number;
  max_discount_amount?: number | null;
  min_purchase_amount: number;
  buy_quantity?: number | null;
  get_quantity?: number | null;
  start_date?: string | null;
  end_date?: string | null;
  usage_limit?: number | null;
  times_used: number;
  is_active: boolean;
}

export interface DiscountApplyResult {
  applied: boolean;
  rule_id?: number | null;
  rule_name?: string | null;
  code?: string | null;
  discount_amount: number;
  message: string;
}

export type SegmentType =
  | "all"
  | "vip"
  | "tag"
  | "category_purchase"
  | "brand_purchase"
  | "inactive"
  | "birthday_month";

export interface SegmentParams {
  segment_type: SegmentType;
  segment_tag?: string | null;
  segment_category_id?: number | null;
  segment_brand?: string | null;
  segment_days?: number | null;
}

export interface SegmentPreviewCustomer {
  id: number;
  name: string;
  phone?: string | null;
}

export interface SegmentPreviewResult {
  count: number;
  customers: SegmentPreviewCustomer[];
}

export type CampaignRecipientStatus = "link_generated" | "sent" | "delivered" | "read" | "failed";

export interface CampaignRecipient {
  id: number;
  customer_id: number;
  customer_name?: string | null;
  phone_number: string;
  message_text: string;
  status: CampaignRecipientStatus;
  whatsapp_link?: string | null;
  error?: string | null;
  sent_at?: string | null;
  delivered_at?: string | null;
  read_at?: string | null;
}

export type CampaignMediaType = "image" | "video" | "document";
export type CampaignButtonType = "quick_reply" | "url" | "phone" | "catalog";
export type CampaignStatus = "scheduled" | "sent" | "failed";

export interface CampaignButton {
  type: CampaignButtonType;
  label: string;
  value: string;
}

export interface CampaignCreate extends SegmentParams {
  name: string;
  message_template: string;
  media_url?: string | null;
  media_type?: CampaignMediaType | null;
  buttons?: CampaignButton[] | null;
  offer_code?: string | null;
  product_name?: string | null;
  scheduled_at?: string | null;
}

export interface Campaign extends SegmentParams {
  id: number;
  name: string;
  message_template: string;
  media_url?: string | null;
  media_type?: CampaignMediaType | null;
  buttons?: CampaignButton[] | null;
  offer_code?: string | null;
  product_name?: string | null;
  scheduled_at?: string | null;
  status: CampaignStatus;
  recipient_count: number;
  sent_count: number;
  created_at: string;
}

export interface CampaignDetail extends Campaign {
  recipients: CampaignRecipient[];
}

export interface CampaignReport {
  recipient_count: number;
  link_generated_count: number;
  sent_count: number;
  delivered_count: number;
  read_count: number;
  failed_count: number;
}

export interface MessageTemplate {
  id: number;
  name: string;
  body: string;
  created_at: string;
}

export interface MediaUploadResult {
  url: string;
  media_type: CampaignMediaType;
}

export interface BulkImportError {
  row: number;
  message: string;
}

export interface BulkImportResult {
  created_products: number;
  updated_products: number;
  created_variants: number;
  updated_variants: number;
  total_rows: number;
  errors: BulkImportError[];
}

export interface SalesTrendPoint {
  date: string;
  total: number;
  count: number;
}

export interface PaymentModeBreakdownItem {
  payment_mode: string;
  total: number;
  count: number;
}

export interface StockAgingItem {
  variant_id: number;
  product_id: number;
  sku: string;
  product_name: string;
  color?: string | null;
  size?: string | null;
  outlet_id: number;
  outlet_name: string;
  quantity: number;
  cost_price: number;
  stock_value: number;
  last_sold_at?: string | null;
  days_since_last_sale: number;
}

export type AlterationStatus = "requested" | "assigned" | "in_progress" | "ready" | "delivered" | "cancelled";

export interface Alteration {
  id: number;
  alteration_number: string;
  outlet_id: number;
  outlet_name?: string | null;
  sale_id?: number | null;
  sale_invoice_number?: string | null;
  sale_item_id?: number | null;
  item_name?: string | null;
  customer_id?: number | null;
  customer_name?: string | null;
  customer_phone?: string | null;
  description: string;
  tailor_name?: string | null;
  status: AlterationStatus;
  expected_ready_date?: string | null;
  delivered_at?: string | null;
  notes?: string | null;
  created_at: string;
}

export interface WhatsAppSendResult {
  whatsapp_link: string;
  status: "link_generated" | "sent" | "failed";
  message_id: number;
  provider_message_id?: string | null;
  note: string;
}

export interface ReceiptSendResult {
  ok: boolean;
  detail: string;
  whatsapp_link?: string | null;
  media_attached?: boolean;
  needs_setup?: boolean;
}

export interface AppSettings {
  business_name?: string | null;
  business_address?: string | null;
  business_gstin?: string | null;
  business_phone?: string | null;
  business_email?: string | null;
  invoice_footer_text?: string | null;
  show_hsn_on_documents: boolean;
  logo_url?: string | null;

  whatsapp_phone_number_id?: string | null;
  whatsapp_api_version?: string | null;
  whatsapp_token_set: boolean;
}

export interface PublicBranding {
  business_name?: string | null;
  logo_url?: string | null;
  primary_color?: string | null;
  slug?: string | null;
}

export interface RegisterRequest {
  company_name: string;
  slug: string;
  owner_name: string;
  email: string;
  password: string;
  plan: "free" | "starter" | "professional" | "enterprise";
}

export interface SlugAvailability {
  slug: string;
  available: boolean;
}

export type EmailProviderType = "brevo" | "resend" | "emailjs" | "smtp_generic" | "gmail_smtp" | "outlook_smtp";
export type SmsProviderType = "msg91" | "textlocal_india" | "two_factor" | "generic_http" | "twilio";

export interface EmailProviderOut {
  provider: EmailProviderType;
  is_enabled: boolean;
  is_default: boolean;
  api_key_set: boolean;
  secret_key_set: boolean;
  sender_name?: string | null;
  sender_email?: string | null;
  smtp_host?: string | null;
  smtp_port?: number | null;
  smtp_username?: string | null;
  smtp_password_set: boolean;
  smtp_use_tls: boolean;
  extra_config: Record<string, unknown>;
  is_configured: boolean;
  last_test_status?: string | null;
  last_test_at?: string | null;
  last_test_error?: string | null;
}

export interface EmailProviderUpdate {
  is_enabled?: boolean;
  is_default?: boolean;
  api_key?: string;
  secret_key?: string;
  sender_name?: string;
  sender_email?: string;
  smtp_host?: string;
  smtp_port?: number;
  smtp_username?: string;
  smtp_password?: string;
  smtp_use_tls?: boolean;
  extra_config?: Record<string, unknown>;
}

export interface SmsProviderOut {
  provider: SmsProviderType;
  is_enabled: boolean;
  is_default: boolean;
  api_key_set: boolean;
  auth_token_set: boolean;
  sender_id?: string | null;
  extra_config: Record<string, unknown>;
  is_configured: boolean;
  last_test_status?: string | null;
  last_test_at?: string | null;
  last_test_error?: string | null;
}

export interface SmsProviderUpdate {
  is_enabled?: boolean;
  is_default?: boolean;
  api_key?: string;
  auth_token?: string;
  sender_id?: string;
  extra_config?: Record<string, unknown>;
}

export interface TestResult {
  ok: boolean;
  detail: string;
}

export interface HardwareAiSettings {
  barcode_min_length?: number | null;
  barcode_beep_on_scan: boolean;

  thermal_printer_name?: string | null;
  thermal_printer_ip?: string | null;

  biometric_enabled: boolean;
  biometric_device_api_url?: string | null;
  biometric_api_key_set: boolean;

  openai_api_key_set: boolean;
  openai_model?: string | null;
}

export interface HardwareAiSettingsUpdate {
  barcode_min_length?: number | null;
  barcode_beep_on_scan?: boolean;
  thermal_printer_name?: string;
  thermal_printer_ip?: string;
  biometric_enabled?: boolean;
  biometric_device_api_url?: string;
  biometric_api_key?: string;
  openai_api_key?: string;
  openai_model?: string;
}

// ---- HRM ----

export interface StaffMember {
  id: number;
  name: string;
  role: string;
  outlet_id?: number | null;
  outlet_name?: string | null;
}

export type AttendanceStatus = "present" | "absent" | "half_day" | "on_leave";

export interface Attendance {
  id: number;
  staff_id: number;
  staff_name?: string | null;
  outlet_id?: number | null;
  outlet_name?: string | null;
  date: string;
  check_in_at?: string | null;
  check_out_at?: string | null;
  status: AttendanceStatus;
  notes?: string | null;
}

export interface AttendanceUpdate {
  status?: AttendanceStatus;
  check_in_at?: string | null;
  check_out_at?: string | null;
  notes?: string;
}

export type LeaveType = "sick" | "casual" | "unpaid" | "other";
export type LeaveStatus = "pending" | "approved" | "rejected";

export interface LeaveRequestCreate {
  leave_type: LeaveType;
  start_date: string;
  end_date: string;
  reason?: string;
}

export interface LeaveRequest {
  id: number;
  staff_id: number;
  staff_name?: string | null;
  leave_type: LeaveType;
  start_date: string;
  end_date: string;
  reason?: string | null;
  status: LeaveStatus;
  reviewed_by_id?: number | null;
  reviewed_by_name?: string | null;
  reviewed_at?: string | null;
  review_note?: string | null;
  created_at: string;
}

export interface LeaveReview {
  status: LeaveStatus;
  review_note?: string;
}

// ---- Payroll ----

export interface StaffSalary {
  staff_id: number;
  staff_name?: string | null;
  monthly_salary?: number | null;
  notes?: string | null;
}

export interface StaffSalaryUpdate {
  monthly_salary: number;
  notes?: string;
}

export type PayslipStatus = "draft" | "paid";

export interface Payslip {
  id: number;
  staff_id: number;
  staff_name?: string | null;
  month: string;
  basic_amount: number;
  allowances: number;
  deductions: number;
  net_amount: number;
  status: PayslipStatus;
  paid_at?: string | null;
  created_at: string;
}

export interface PayslipGenerate {
  month: string;
  staff_id?: number;
}

export interface PayslipUpdate {
  allowances?: number;
  deductions?: number;
  status?: PayslipStatus;
}

// ---- Super Admin ----
export type SubscriptionPlanName = "free" | "starter" | "professional" | "enterprise";
export type SubscriptionStatus = "trial" | "active" | "suspended" | "cancelled";

export interface Tenant {
  id: number;
  company_name: string;
  slug: string;
  logo?: string | null;
  primary_color?: string | null;
  timezone: string;
  currency: string;
  country?: string | null;
  subscription_plan: SubscriptionPlanName;
  subscription_status: SubscriptionStatus;
  trial_end?: string | null;
  is_active: boolean;
  created_at: string;
}

export interface TenantCreate {
  company_name: string;
  slug: string;
  primary_color?: string | null;
  timezone?: string;
  currency?: string;
  country?: string | null;
  subscription_plan?: SubscriptionPlanName;
  trial_end?: string | null;
  owner_name: string;
  owner_email: string;
  owner_password: string;
}

export interface TenantUpdate {
  company_name?: string;
  primary_color?: string | null;
  timezone?: string;
  currency?: string;
  country?: string | null;
  subscription_plan?: SubscriptionPlanName;
  subscription_status?: SubscriptionStatus;
  trial_end?: string | null;
  is_active?: boolean;
}

export interface TenantUsage {
  tenant_id: number;
  user_count: number;
  active_user_count: number;
  outlet_count: number;
  product_count: number;
  estimated_record_count: number;
}

export interface AuditLogEntry {
  id: number;
  tenant_id?: number | null;
  user_id?: number | null;
  action: string;
  entity_type?: string | null;
  entity_id?: number | null;
  details?: Record<string, unknown> | null;
  created_at: string;
}

// ---- Tenant self-service (the tenant's own users, not Super Admin) ----
export interface TenantSelf {
  id: number;
  company_name: string;
  slug: string;
  logo?: string | null;
  primary_color?: string | null;
  timezone: string;
  currency: string;
  country?: string | null;
  subscription_plan: SubscriptionPlanName;
  subscription_status: SubscriptionStatus;
  trial_end?: string | null;
}

export interface TenantSelfUpdate {
  company_name?: string;
  primary_color?: string | null;
  timezone?: string;
  currency?: string;
  country?: string | null;
}
