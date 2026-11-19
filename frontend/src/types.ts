// Shared domain types for the BillFlow frontend.

export type Role = 'owner' | 'staff' | string;

export interface AuthUser {
  id: string;
  business_id: string;
  full_name: string;
  email: string;
  phone?: string | null;
  role: Role;
  business_name?: string | null;
  is_active?: boolean;
  created_at?: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  access_token_expires_in: number;
  user: AuthUser;
}

export interface RegisterPayload {
  business_name: string;
  owner_name: string;
  email: string;
  phone?: string;
  password: string;
  upi_id?: string;
  gstin?: string;
}

export interface Business {
  id: string;
  name: string;
  legal_name?: string | null;
  email?: string | null;
  phone?: string | null;
  address?: string | null;
  city?: string | null;
  state?: string | null;
  pincode?: string | null;
  gstin?: string | null;
  logo_url?: string | null;
  upi_id?: string | null;
  upi_name?: string | null;
  currency: string;
  invoice_prefix: string;
  invoice_footer?: string | null;
  default_gst_rate: number;
  low_stock_threshold: number;
  created_at?: string;
}

export type BusinessUpdate = Partial<Pick<
  Business,
  | 'name'
  | 'legal_name'
  | 'email'
  | 'phone'
  | 'address'
  | 'city'
  | 'state'
  | 'pincode'
  | 'gstin'
  | 'upi_id'
  | 'upi_name'
  | 'currency'
  | 'invoice_prefix'
  | 'invoice_footer'
  | 'default_gst_rate'
  | 'low_stock_threshold'
>>;

export interface AppUser extends AuthUser {
  is_active: boolean;
  created_at?: string;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface MessageResponse {
  message: string;
}

export interface Customer {
  id: string;
  business_id: string;
  name: string;
  phone?: string | null;
  email?: string | null;
  address?: string | null;
  city?: string | null;
  state?: string | null;
  pincode?: string | null;
  gstin?: string | null;
  notes?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CustomerStats {
  total_purchases: number;
  invoice_count: number;
  outstanding_balance: number;
  total_paid: number;
  last_transaction_date?: string | null;
  last_invoice_date?: string | null;
}

export interface Interaction {
  id: string;
  type: 'note' | 'call' | 'email' | 'meeting' | 'other' | string;
  content: string;
  created_by?: string | null;
  created_at: string;
}

export type CustomerDetail = Customer & {
  stats: CustomerStats;
  interactions: Interaction[];
};

export type CustomerInput = Partial<Pick<
  Customer,
  | 'name'
  | 'phone'
  | 'email'
  | 'address'
  | 'city'
  | 'state'
  | 'pincode'
  | 'gstin'
  | 'notes'
  | 'is_active'
>>;

/** The pricing mode selected for a sale / recorded on an invoice. */
export type PricingMode = 'retail' | 'wholesale';

export interface Product {
  id: string;
  business_id: string;
  name: string;
  sku?: string | null;
  barcode?: string | null;
  description?: string | null;
  hsn_code?: string | null;
  price: number;
  /** Discount applied to the retail price when billing in wholesale mode (0..100). */
  wholesale_discount_percent: number;
  /** Derived by the backend: round2(price * (1 - wholesale_discount_percent / 100)). */
  wholesale_price?: number;
  gst_rate: number;
  stock: number;
  track_inventory: boolean;
  is_service: boolean;
  low_stock_threshold: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  is_low_stock?: boolean;
}

export type ProductInput = Partial<Pick<
  Product,
  | 'name'
  | 'sku'
  | 'barcode'
  | 'description'
  | 'hsn_code'
  | 'price'
  | 'wholesale_discount_percent'
  | 'wholesale_price'
  | 'gst_rate'
  | 'stock'
  | 'track_inventory'
  | 'is_service'
  | 'low_stock_threshold'
  | 'is_active'
>>;

export type InvoiceStatus =
  | 'draft'
  | 'unpaid'
  | 'partially_paid'
  | 'paid'
  | 'cancelled'
  | string;

export interface InvoiceListItem {
  id: string;
  invoice_number: string;
  customer_id: string;
  customer_name?: string | null;
  issue_date: string;
  due_date?: string | null;
  status: InvoiceStatus;
  pricing_mode: PricingMode;
  total_amount: number;
  paid_amount: number;
  balance_amount: number;
  created_at: string;
}

export interface InvoiceItem {
  id: string;
  invoice_id: string;
  product_id?: string | null;
  description: string;
  quantity: number;
  unit_price: number;
  discount_percent: number;
  discount_amount: number;
  taxable_amount: number;
  gst_rate: number;
  tax_amount: number;
  line_total: number;
  sort_order: number;
}

export interface Invoice {
  id: string;
  business_id: string;
  customer_id: string;
  customer_name?: string | null;
  customer_phone?: string | null;
  customer_email?: string | null;
  invoice_number: string;
  issue_date: string;
  due_date?: string | null;
  status: InvoiceStatus;
  pricing_mode: PricingMode;
  subtotal: number;
  discount_percent: number;
  discount_amount: number;
  taxable_amount: number;
  tax_amount: number;
  total_amount: number;
  paid_amount: number;
  balance_amount: number;
  notes?: string | null;
  public_token: string;
  transaction_ref?: string | null;
  created_at: string;
  updated_at: string;
  items: InvoiceItem[];
}

export interface InvoiceItemInput {
  product_id?: string | null;
  barcode?: string;
  description?: string;
  quantity: number;
  unit_price?: number;
  discount_percent?: number;
  gst_rate?: number;
}

export interface InvoiceInput {
  customer_id: string | null;
  issue_date?: string;
  due_date?: string;
  items: InvoiceItemInput[];
  discount_percent?: number;
  notes?: string;
  status?: 'draft' | 'unpaid';
}

export type InvoiceUpdate = Partial<InvoiceInput>;

export interface QrResponse {
  upi_uri: string;
  qr_data_url: string;
  amount: number;
  upi_id: string;
  payee_name: string;
  invoice_number?: string;
  transaction_ref?: string | null;
  currency?: string;
}

/** An auditable change to a product's stock level. */
export interface StockMovement {
  id: string;
  business_id: string;
  product_id: string;
  product_name: string;
  sku?: string | null;
  barcode?: string | null;
  quantity_change: number;
  quantity_before: number;
  quantity_after: number;
  reason: string;
  reference?: string | null;
  performed_by: string;
  performed_by_name?: string | null;
  notes?: string | null;
  created_at: string;
}

/** An owner-only audit log entry. */
export interface ActivityLog {
  id: string;
  business_id: string;
  user_id: string;
  user_name: string;
  action: string;
  category: string;
  reference?: string | null;
  entity_type?: string | null;
  entity_id?: string | null;
  details?: unknown;
  created_at: string;
}

export type PaymentMethod =
  | 'upi'
  | 'cash'
  | 'card'
  | 'bank_transfer'
  | 'netbanking'
  | 'other'
  | string;

export type PaymentStatus =
  | 'submitted'
  | 'pending'
  | 'confirmed'
  | 'failed'
  | 'refunded'
  | string;

export interface Payment {
  id: string;
  business_id: string;
  invoice_id: string;
  invoice_number?: string | null;
  customer_id: string;
  customer_name?: string | null;
  amount: number;
  method: PaymentMethod;
  status: PaymentStatus;
  reference?: string | null;
  payer_vpa?: string | null;
  payment_date?: string | null;
  notes?: string | null;
  confirmed_at?: string | null;
  confirmed_by?: string | null;
  created_at: string;
}

export interface PaymentInput {
  invoice_id: string;
  amount: number;
  method: PaymentMethod;
  reference?: string;
  payer_vpa?: string;
  payment_date?: string;
  notes?: string;
  confirm?: boolean;
}

export interface TrendPoint {
  period: string;
  sales: number;
  collections: number;
  invoices: number;
}

export interface MethodBreakdown {
  method: string;
  amount: number;
  count: number;
  percentage: number;
}

export interface TopProduct {
  product_id?: string | null;
  name: string;
  quantity_sold: number;
  revenue: number;
  invoice_count: number;
}

export interface TopCustomer {
  customer_id: string;
  name: string;
  total_purchases: number;
  invoice_count: number;
  outstanding: number;
}

export interface StatusBreakdown {
  status: string;
  count: number;
  amount: number;
}

export interface AnalyticsSummary {
  total_sales: number;
  total_collections: number;
  total_invoices: number;
  total_transactions: number;
  outstanding: number;
  growth_percent: number;
  average_invoice_value: number;
}

export interface AnalyticsResponse {
  from_date?: string | null;
  to_date?: string | null;
  summary: AnalyticsSummary;
  today_sales: number;
  today_transactions: number;
  today_collections: number;
  month_sales: number;
  month_collections: number;
  year_sales: number;
  pending_amount: number;
  pending_invoices: number;
  low_stock_products: number;
  total_customers: number;
  active_customers: number;
  sales_trend: TrendPoint[];
  payment_methods: MethodBreakdown[];
  top_products: TopProduct[];
  top_customers: TopCustomer[];
  status_breakdown: StatusBreakdown[];
  recent_invoices: InvoiceListItem[];
  recent_payments: Payment[];
}

export interface PublicInvoiceItem {
  description: string;
  quantity: number;
  unit_price: number;
  line_total: number;
}

export interface PublicPayment {
  id: string;
  method: string;
  status: string;
  amount: number;
  reference?: string | null;
  created_at: string;
}

export interface PublicInvoice {
  invoice_number: string;
  issue_date: string;
  due_date?: string | null;
  status: InvoiceStatus;
  total_amount: number;
  paid_amount: number;
  balance_amount: number;
  customer_name?: string | null;
  business_name: string;
  business_upi_id?: string | null;
  business_upi_name?: string | null;
  currency: string;
  items: PublicInvoiceItem[];
  payments: PublicPayment[];
}

export interface PublicPaymentInput {
  amount: number;
  method: PaymentMethod;
  reference: string;
  payer_vpa?: string;
  notes?: string;
}

export type QueryValue = string | number | boolean | null | undefined;

/* ------------------------------------------------------------------ */
/* Simplified POS checkout                                              */
/* ------------------------------------------------------------------ */

export interface PosCartLineInput {
  product_id: string;
  quantity: number;
  discount_percent: number;
}

export interface PosQuoteRequest {
  customer_id: string | null;
  items: PosCartLineInput[];
  discount_percent: number;
  transaction_ref: string;
  /** Retail is the default; the backend computes authoritative prices from it. */
  pricing_mode: PricingMode;
}

/** Body sent by `POST /pos/checkout`. The backend re-derives unit prices. */
export interface PosCheckoutPayload extends PosQuoteRequest {
  method: 'upi' | 'cash';
}

export interface PosQRResponse {
  qr_data_url: string;
  upi_uri: string;
  amount: number;
  upi_id: string;
  upi_name: string;
  business_name: string;
  transaction_ref: string;
  currency: string;
  quote: {
    subtotal: number;
    discount_amount: number;
    taxable_amount: number;
    tax_amount: number;
    total_amount: number;
  };
}

export interface PosReceipt {
  invoice_number: string;
  transaction_ref?: string | null;
  business_name: string;
  customer_name?: string | null;
  amount: number;
  method: string;
  reference?: string | null;
  payment_date?: string | null;
  status: string;
  note: string;
}

export interface PosCheckoutResponse {
  invoice: Invoice;
  payment: Payment;
  receipt: PosReceipt;
}

/* ------------------------------------------------------------------ */
/* Product import (owner onboarding)                                   */
/* ------------------------------------------------------------------ */

/** One editable row returned by the file / photo parser. */
export interface ProductImportRow {
  row_number: number;
  name: string;
  barcode: string | null;
  cost_price: number | null;
  selling_price: number | null;
  quantity: number;
  category: string | null;
  gst_rate: number;
  errors: string[];
  warnings: string[];
  valid: boolean;
  /* Extended 14-column template fields (optional for legacy files). */
  brand?: string | null;
  subcategory?: string | null;
  variant?: string | null;
  size_pack?: string | null;
  barcode_type?: string | null;
  sku?: string | null;
  discount_type?: string | null;
  discount_value?: number | null;
}

/** Response from `POST /products/import/parse`. */
export interface ProductImportParseResponse {
  recognized_columns: Record<string, string | null>;
  unsupported_columns: string[];
  total_rows: number;
  error_count: number;
  rows: ProductImportRow[];
}

/** A row accepted by `POST /products/import/commit`. */
export interface ProductImportCommitRow {
  name: string;
  barcode?: string | null;
  cost_price?: number | null;
  selling_price: number;
  quantity: number;
  category?: string | null;
  gst_rate?: number;
  /* Extended 14-column template fields. */
  brand?: string | null;
  subcategory?: string | null;
  variant?: string | null;
  size_pack?: string | null;
  barcode_type?: string | null;
  sku?: string | null;
  discount_type?: string | null;
  discount_value?: number | null;
}

/** Response from `POST /products/import/commit`. */
export interface ProductImportCommitResponse {
  created: number;
  updated: number;
  skipped: number;
  errors: Array<{ row: number; message: string }>;
  stock_movements: number;
  activity_entries: number;
}

/** One candidate row returned by the photo / PDF reader. */
export interface ProductOcrRow {
  name: string;
  quantity: number | null;
  confidence: number;
  uncertain_fields: string[];
  raw_line: string;
}

/** Response from `POST /products/import/ocr`. */
export interface ProductOcrResponse {
  rows: ProductOcrRow[];
  source: string;
  warnings: string[];
}

/** Response from `GET /products/barcode/lookup/{barcode}`. */
export interface BarcodeLookupResponse {
  found: boolean;
  source: string;
  barcode: string;
  name?: string;
  brand?: string;
  category?: string;
  image_url?: string;
  price: null;
  message: string;
}

/* ------------------------------------------------------------------ */
/* AI-assisted catalogue onboarding (guided, external-AI workflow)     */
/* ------------------------------------------------------------------ */

/** One selectable business type from `GET /products/ai/categories`. */
export interface AICategory {
  id: string;
  label: string;
  description: string;
}

/** Response from `GET /products/ai/categories`. */
export interface AICategoriesResponse {
  categories: AICategory[];
}

/** Request body for `POST /products/ai/prompt`. */
export interface AIPromptRequest {
  category_id: string;
  business_name?: string;
  extra_notes?: string;
}

/** Response from `POST /products/ai/prompt`. */
export interface AIPromptResponse {
  prompt: string;
}

/* ------------------------------------------------------------------ */
/* Supplier management (owner-only, additive)                          */
/* ------------------------------------------------------------------ */

/** A supplier / vendor. All text taxonomy fields are user-defined. */
export interface Supplier {
  id: string;
  business_id?: string;
  name: string;
  contact_person?: string | null;
  phone?: string | null;
  whatsapp?: string | null;
  email?: string | null;
  address?: string | null;
  category?: string | null;
  brands?: string | null;
  notes?: string | null;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
  /** Derived by the supplier list endpoint. */
  product_count?: number;
  product_type?: string | null;
}

/** Only the name is required; every other field is optional. */
export type SupplierInput = Partial<Pick<
  Supplier,
  | 'name'
  | 'contact_person'
  | 'phone'
  | 'whatsapp'
  | 'email'
  | 'address'
  | 'category'
  | 'brands'
  | 'notes'
  | 'is_active'
>>;

/**
 * Suggestions returned by `GET /suppliers/categories`. These are derived from
 * data owners have already entered — never a hardcoded industry list.
 */
export interface SupplierCategorySuggestions {
  categories?: string[];
  brands?: string[];
  product_types?: string[];
  /** Some API envelopes wrap the payload in `data`. */
  data?: SupplierCategorySuggestions;
}

/** A link between a supplier and an existing product or a custom item name. */
export interface SupplierProduct {
  id: string;
  supplier_id: string;
  product_id?: string | null;
  product_name?: string | null;
  product_sku?: string | null;
  custom_name?: string | null;
  supplier_sku?: string | null;
  supplier_price?: number | null;
  notes?: string | null;
}

export interface SupplierProductInput {
  /** Existing BillFlow product id, or null/empty for a custom name. */
  product_id?: string | null;
  custom_name?: string | null;
  supplier_sku?: string | null;
  supplier_price?: number | null;
  notes?: string | null;
}

export type ReminderListStatus = 'pending' | 'converted' | string;

/** A purchaser's reminder list for a supplier; multiple per supplier. */
export interface PurchaseReminderList {
  id: string;
  supplier_id: string;
  title: string;
  status: ReminderListStatus;
  notes?: string | null;
  created_at?: string;
  /** Some detail payloads embed the items; others expose a separate endpoint. */
  items?: PurchaseReminderItem[];
}

/** One line on a reminder list. Ticking purchased never mutates stock. */
export interface PurchaseReminderItem {
  id: string;
  list_id: string;
  product_id?: string | null;
  product_name?: string | null;
  name: string;
  quantity: number;
  unit?: string | null;
  expected_price?: number | null;
  notes?: string | null;
  is_purchased: boolean;
}

export interface PurchaseReminderItemInput {
  product_id?: string | null;
  custom_name?: string | null;
  name?: string | null;
  quantity?: number;
  unit?: string | null;
  expected_price?: number | null;
  notes?: string | null;
  is_purchased?: boolean;
}

export interface SupplierVisit {
  id: string;
  supplier_id: string;
  visit_date: string;
  discussion_notes?: string | null;
  items_discussed?: string | null;
  items_requested?: string | null;
  follow_up?: string | null;
  next_visit_date?: string | null;
  notes?: string | null;
  created_by?: string | null;
  created_at?: string;
}

export interface SupplierVisitInput {
  visit_date?: string;
  discussion_notes?: string | null;
  items_discussed?: string | null;
  items_requested?: string | null;
  follow_up?: string | null;
  next_visit_date?: string | null;
  notes?: string | null;
}

/** `GET /suppliers/{id}` — detail payload with related records. */
export type SupplierDetail = Supplier & {
  products?: SupplierProduct[];
  supplier_products?: SupplierProduct[];
  reminder_lists?: PurchaseReminderList[];
  reminders?: PurchaseReminderList[];
  visits?: SupplierVisit[];
};

/** Response from `POST /suppliers/reminders/{list_id}/convert-to-purchase`. */
export interface SupplierPurchaseConversion {
  message?: string;
  purchase_number?: string;
  purchase_date?: string;
  purchase?: {
    id?: string;
    purchase_number?: string;
    purchase_date?: string;
    notes?: string | null;
  } | null;
  items_created?: number;
  stock_movements?: number;
  movements_created?: number;
  custom_items_skipped?: number;
  skipped_custom_items?: number;
  total_amount?: number;
}
