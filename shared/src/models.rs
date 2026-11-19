//! Plain data models returned by the repository and service layers.

use std::str::FromStr;

use serde::{Deserialize, Serialize};

/// Tenant-level role. Stored as `"owner"` / `"staff"` in SQLite.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Role {
    Owner,
    Staff,
}

impl Role {
    pub fn as_str(&self) -> &'static str {
        match self {
            Role::Owner => "owner",
            Role::Staff => "staff",
        }
    }

    pub fn label(&self) -> &'static str {
        match self {
            Role::Owner => "Owner",
            Role::Staff => "Staff",
        }
    }

    pub fn from_str(s: &str) -> Self {
        match s.trim().to_ascii_lowercase().as_str() {
            "owner" => Role::Owner,
            _ => Role::Staff,
        }
    }
}

impl FromStr for Role {
    type Err = ();

    fn from_str(s: &str) -> std::result::Result<Self, Self::Err> {
        Ok(Role::from_str(s))
    }
}

/// Payment methods exposed by the point-of-sale screen.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum PaymentMethod {
    Upi,
    Cash,
}

impl PaymentMethod {
    pub fn as_str(&self) -> &'static str {
        match self {
            PaymentMethod::Upi => "upi",
            PaymentMethod::Cash => "cash",
        }
    }

    pub fn label(&self) -> &'static str {
        match self {
            PaymentMethod::Upi => "UPI",
            PaymentMethod::Cash => "Cash",
        }
    }

    pub fn from_str(s: &str) -> Self {
        match s.trim().to_ascii_lowercase().as_str() {
            "cash" => PaymentMethod::Cash,
            _ => PaymentMethod::Upi,
        }
    }
}

impl FromStr for PaymentMethod {
    type Err = ();

    fn from_str(s: &str) -> std::result::Result<Self, Self::Err> {
        Ok(PaymentMethod::from_str(s))
    }
}

/// Lifecycle state of an invoice.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum InvoiceStatus {
    Draft,
    Unpaid,
    PartiallyPaid,
    Paid,
    Cancelled,
}

impl InvoiceStatus {
    pub fn as_str(&self) -> &'static str {
        match self {
            InvoiceStatus::Draft => "draft",
            InvoiceStatus::Unpaid => "unpaid",
            InvoiceStatus::PartiallyPaid => "partially_paid",
            InvoiceStatus::Paid => "paid",
            InvoiceStatus::Cancelled => "cancelled",
        }
    }

    pub fn label(&self) -> &'static str {
        match self {
            InvoiceStatus::Draft => "Draft",
            InvoiceStatus::Unpaid => "Unpaid",
            InvoiceStatus::PartiallyPaid => "Partially Paid",
            InvoiceStatus::Paid => "Paid",
            InvoiceStatus::Cancelled => "Cancelled",
        }
    }

    /// Parse a stored status string. Unknown values safely fall back to Draft.
    pub fn from_str(s: &str) -> Self {
        match s.trim().to_ascii_lowercase().replace([' ', '-'], "_").as_str() {
            "draft" => InvoiceStatus::Draft,
            "unpaid" => InvoiceStatus::Unpaid,
            "partially_paid" | "partial" => InvoiceStatus::PartiallyPaid,
            "paid" => InvoiceStatus::Paid,
            "cancelled" | "canceled" => InvoiceStatus::Cancelled,
            _ => InvoiceStatus::Draft,
        }
    }
}

impl FromStr for InvoiceStatus {
    type Err = ();

    fn from_str(s: &str) -> std::result::Result<Self, Self::Err> {
        Ok(InvoiceStatus::from_str(s))
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Business {
    pub id: String,
    pub name: String,
    pub legal_name: Option<String>,
    pub email: String,
    pub phone: String,
    pub address: String,
    pub city: String,
    pub state: String,
    pub pincode: String,
    pub gstin: String,
    pub upi_id: String,
    pub upi_name: String,
    pub logo_url: Option<String>,
    pub currency: String,
    pub invoice_prefix: String,
    pub invoice_footer: Option<String>,
    pub default_gst_rate: f64,
    pub low_stock_threshold: f64,
    pub invoice_sequence: i64,
    pub created_at: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct User {
    pub id: String,
    pub business_id: String,
    pub full_name: String,
    pub email: String,
    pub phone: Option<String>,
    pub role: Role,
    pub is_active: bool,
    pub created_at: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Customer {
    pub id: String,
    pub business_id: String,
    pub name: String,
    pub phone: String,
    pub email: String,
    pub address: String,
    pub city: String,
    pub state: String,
    pub pincode: String,
    pub gstin: String,
    pub notes: Option<String>,
    pub is_active: bool,
    pub created_at: String,
    pub updated_at: String,
}

fn default_discount_type() -> String {
    "none".to_string()
}

/// Bills are retail unless a caller explicitly opts into wholesale.
fn default_pricing_mode() -> String {
    "retail".to_string()
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Product {
    pub id: String,
    pub business_id: String,
    pub name: String,
    pub sku: String,
    pub description: String,
    pub hsn_code: String,
    pub barcode: Option<String>,
    pub price: f64,
    pub gst_rate: f64,
    pub stock: f64,
    pub track_inventory: bool,
    pub is_service: bool,
    pub low_stock_threshold: f64,
    /// Product-level discount kind (`none`, `percent` or `flat`).
    /// Defaults to `"none"` so older payloads stay deserializable.
    #[serde(default = "default_discount_type")]
    pub discount_type: String,
    /// Product-level discount amount (percent or flat), default `0`.
    #[serde(default)]
    pub discount_value: f64,
    /// Wholesale discount (percent) applied to `price` in wholesale mode.
    /// Derived wholesale price = round2(price * (1 - this / 100)).
    #[serde(default)]
    pub wholesale_discount_percent: f64,
    pub is_active: bool,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Invoice {
    pub id: String,
    pub business_id: String,
    pub customer_id: String,
    pub customer_name: Option<String>,
    pub invoice_number: String,
    pub transaction_ref: Option<String>,
    pub issue_date: String,
    pub due_date: Option<String>,
    pub status: InvoiceStatus,
    /// Pricing mode used for this bill (`retail` or `wholesale`).
    #[serde(default = "default_pricing_mode")]
    pub pricing_mode: String,
    pub subtotal: f64,
    pub discount_percent: f64,
    pub discount_amount: f64,
    pub taxable_amount: f64,
    pub tax_amount: f64,
    pub total_amount: f64,
    pub paid_amount: f64,
    pub balance_amount: f64,
    pub notes: Option<String>,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct InvoiceItem {
    pub id: String,
    pub invoice_id: String,
    pub product_id: Option<String>,
    pub description: String,
    pub quantity: f64,
    pub unit_price: f64,
    /// Wholesale discount actually applied to this line at bill time (0 in retail mode).
    #[serde(default)]
    pub wholesale_discount_percent: f64,
    pub discount_percent: f64,
    pub discount_amount: f64,
    pub taxable_amount: f64,
    pub gst_rate: f64,
    pub tax_amount: f64,
    pub line_total: f64,
    pub sort_order: i64,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Payment {
    pub id: String,
    pub business_id: String,
    pub invoice_id: String,
    pub invoice_number: Option<String>,
    pub customer_id: String,
    pub customer_name: Option<String>,
    pub amount: f64,
    pub method: PaymentMethod,
    pub status: String,
    pub reference: Option<String>,
    pub payment_date: Option<String>,
    pub notes: Option<String>,
    pub confirmed_at: Option<String>,
    pub created_at: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct StockMovement {
    pub id: String,
    pub business_id: String,
    pub product_id: String,
    pub product_name: String,
    pub sku: Option<String>,
    pub barcode: Option<String>,
    pub quantity_change: f64,
    pub quantity_before: f64,
    pub quantity_after: f64,
    pub reason: String,
    pub reference: Option<String>,
    pub performed_by_name: String,
    pub notes: Option<String>,
    pub created_at: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ActivityLog {
    pub id: String,
    pub business_id: String,
    pub user_id: Option<String>,
    pub user_name: String,
    pub action: String,
    pub category: String,
    pub reference: Option<String>,
    pub details: Option<String>,
    pub created_at: String,
}

#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct CustomerStats {
    pub total_purchases: f64,
    pub invoice_count: i64,
    pub outstanding_balance: f64,
    pub last_transaction_date: Option<String>,
    pub last_invoice_date: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct InvoiceDetail {
    pub invoice: Invoice,
    pub items: Vec<InvoiceItem>,
    pub payments: Vec<Payment>,
}

/// One staged product row from a CSV import file.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct ImportRow {
    pub name: String,
    pub barcode: Option<String>,
    pub cost_price: Option<f64>,
    pub selling_price: f64,
    pub quantity: f64,
    pub category: Option<String>,
    pub gst_rate: Option<f64>,
}

/// Outcome of one atomic product import batch.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct ImportSummary {
    pub created: i64,
    pub updated: i64,
    pub skipped: i64,
    /// `(1-based row number, message)` for every invalid row.
    pub errors: Vec<(usize, String)>,
    pub stock_movements: i64,
    pub activity_entries: i64,
}
