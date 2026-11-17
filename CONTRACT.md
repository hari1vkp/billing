# BillFlow Rust migration — shared API contract

Both implementation tracks MUST use these exact signatures. Do not rename or
change types. Anything missing should be added in `billflow-shared` without
breaking the listed API.

Crate name: `billflow_shared` (lib), binary crate: `billflow`.

## models.rs
```rust
pub enum Role { Owner, Staff }
pub enum PaymentMethod { Upi, Cash }          // as_str() -> "upi"|"cash", label() -> "UPI"|"Cash"
pub enum InvoiceStatus { Draft, Unpaid, PartiallyPaid, Paid, Cancelled } // as_str(), label(), from_str

pub struct Business { pub id, name, legal_name:Option<String>, email, phone, address, city, state, pincode, gstin, upi_id, upi_name, logo_url:Option<String>, currency:String, invoice_prefix:String, invoice_footer:Option<String>, default_gst_rate:f64, low_stock_threshold:f64, invoice_sequence:i64, created_at:String }
pub struct User { pub id, business_id, full_name, email, phone:Option<String>, role:Role, is_active:bool, created_at:String }  // role stored as string in DB
pub struct Customer { pub id, business_id, name, phone,email,address,city,state,pincode,gstin,notes:Option<String>, is_active:bool, created_at, updated_at:String }
pub struct Product { pub id, business_id, name, sku,description,hsn_code,barcode:Option<String>, price:f64, gst_rate:f64, stock:f64, track_inventory:bool, is_service:bool, low_stock_threshold:f64, is_active:bool, created_at, updated_at:String }
pub struct Invoice { pub id, business_id, customer_id, customer_name:Option<String>, invoice_number, transaction_ref:Option<String>, issue_date:String, due_date:Option<String>, status:InvoiceStatus, subtotal:f64, discount_percent:f64, discount_amount:f64, taxable_amount:f64, tax_amount:f64, total_amount:f64, paid_amount:f64, balance_amount:f64, notes:Option<String>, created_at, updated_at:String }
pub struct InvoiceItem { pub id, invoice_id, product_id:Option<String>, description, quantity:f64, unit_price:f64, discount_percent:f64, discount_amount:f64, taxable_amount:f64, gst_rate:f64, tax_amount:f64, line_total:f64, sort_order:i64 }
pub struct Payment { pub id, business_id, invoice_id, invoice_number:Option<String>, customer_id, customer_name:Option<String>, amount:f64, method:PaymentMethod, status:String, reference:Option<String>, payment_date:Option<String>, notes:Option<String>, confirmed_at:Option<String>, created_at:String }
pub struct StockMovement { pub id, business_id, product_id, product_name, sku:Option<String>, barcode:Option<String>, quantity_change:f64, quantity_before:f64, quantity_after:f64, reason:String, reference:Option<String>, performed_by_name:String, notes:Option<String>, created_at:String }
pub struct ActivityLog { pub id, business_id, user_id:Option<String>, user_name:String, action:String, category:String, reference:Option<String>, details:Option<String>, created_at:String }
pub struct CustomerStats { total_purchases:f64, invoice_count:i64, outstanding_balance:f64, last_transaction_date:Option<String>, last_invoice_date:Option<String> }
pub struct InvoiceDetail { pub invoice:Invoice, pub items:Vec<InvoiceItem>, pub payments:Vec<Payment> }
```
All structs derive `Clone, Debug` (and `PartialEq` where easy).

## Result alias
`pub type Result<T> = std::result::Result<T, BillflowError>;` with `thiserror` `BillflowError` variants: `Db(rusqlite::Error)`, `NotFound(String)`, `Validation(String)`, `Io(std::io::Error)`, `Qr(String)`, `Pdf(String)`, `Auth(String)`. Implement `From` conversions.

## db.rs
```rust
pub struct Database { /* private Mutex<Connection> */ }
impl Database {
  pub fn open(path:&Path) -> Result<Self>;
  pub fn in_memory() -> Result<Self>;
  pub fn conn(&self) -> std::sync::MutexGuard<'_, rusqlite::Connection>;
  pub fn backup(&self, target:&Path) -> Result<()>;
  pub fn restore(&self, source:&Path) -> Result<()>;
}
pub fn app_data_dir() -> PathBuf;          // Linux ~/.local/share/billflow, Windows %APPDATA%\BillFlow
pub fn default_db_path() -> PathBuf;        // app_data_dir()/billflow.sqlite3
pub fn migrate(conn:&rusqlite::Connection) -> Result<()>;
```
`migrate` runs `CREATE TABLE IF NOT EXISTS` for all tables and inserts PRAGMA foreign_keys/journal_mode=WAL.

## money.rs
`pub fn round2(v:f64)->f64`, `pub fn format_inr(v:f64)->String` (en-IN style `₹1,23,456.78`).

## auth.rs
```rust
pub fn hash_password(password:&str)->Result<String>;        // PBKDF2-SHA256, salted, "pbkdf2$<salt>$<hash>"
pub fn verify_password(password:&str, stored:&str)->bool;
pub fn authenticate(conn:&Connection,email:&str,password:&str)->Result<User>;
pub fn create_user(conn:&Connection,business_id:&str,full_name:&str,email:&str,phone:Option<&str>,password:&str,role:Role)->Result<User>;
pub fn list_users(conn:&Connection,business_id:&str)->Result<Vec<User>>;
pub fn set_user_active(conn:&Connection,user_id:&str,active:bool)->Result<()>;
pub fn is_owner(user:&User)->bool;
```

## audit.rs
`pub fn log(conn:&Connection,business_id:&str,user_id:Option<&str>,action:&str,category:&str,reference:Option<&str>,details:Option<&str>)->Result<()>;`

## repo.rs (all take `&rusqlite::Connection`)
```rust
pub fn get_business(conn,business_id)->Result<Business>;
pub struct BusinessInput { pub name, legal_name, email, phone, address, city, state, pincode, gstin, upi_id, upi_name, currency, invoice_prefix, invoice_footer, default_gst_rate:f64, low_stock_threshold:f64 }
pub fn update_business(conn,business_id,&BusinessInput)->Result<Business>;
pub fn bootstrap(conn)->Result<(Business,User)>;   // first run: create business + owner demo@billingapp.com / Demo@1234

pub fn list_products(conn,business_id,query:&str,low_stock_only:bool,limit:i64,offset:i64)->Result<(Vec<Product>,i64)>;
pub fn get_product(conn,business_id,id)->Result<Option<Product>>;
pub fn get_product_by_barcode(conn,business_id,barcode)->Result<Option<Product>>;
pub struct ProductInput { name,sku,description,hsn_code,barcode:Option<String>,price:f64,gst_rate:f64,stock:f64,track_inventory:bool,is_service:bool,low_stock_threshold:f64 }
pub fn insert_product(conn,business_id,&ProductInput)->Result<Product>;
pub fn update_product(conn,business_id,id,&ProductInput)->Result<Product>;
pub fn archive_product(conn,business_id,id)->Result<()>;

pub fn list_customers(conn,business_id,query:&str,limit:i64,offset:i64)->Result<(Vec<Customer>,i64)>;
pub fn get_customer(conn,business_id,id)->Result<Option<Customer>>;
pub fn insert_customer(conn,business_id,name,&str fields...)->Result<Customer>;  // use CustomerInput struct with Option<String> fields
pub struct CustomerInput { name:String, phone:Option<String>, email:Option<String>, address:Option<String>, city:Option<String>, state:Option<String>, pincode:Option<String>, gstin:Option<String>, notes:Option<String> }
pub fn update_customer(conn,business_id,id,&CustomerInput)->Result<Customer>;
pub fn customer_stats(conn,business_id,customer_id)->Result<CustomerStats>;
pub fn list_interactions(conn,business_id,customer_id)->Result<Vec<(String,String,String)>>; // (type, content, created_at)
pub fn add_interaction(conn,business_id,customer_id,user_id,type_: &str,content:&str)->Result<()>;

pub fn list_invoices(conn,business_id,query:&str,status:&str,limit:i64,offset:i64)->Result<(Vec<Invoice>,i64)>;
pub fn get_invoice(conn,business_id,id)->Result<InvoiceDetail>;
pub fn next_invoice_number(conn,business_id)->Result<String>;
pub fn set_invoice_status(conn,business_id,id,status:InvoiceStatus,user_id:Option<&str>)->Result<Invoice>;

pub fn list_payments(conn,business_id,query:&str,status:&str,limit:i64,offset:i64)->Result<(Vec<Payment>,i64)>;
pub fn get_payment(conn,business_id,id)->Result<Payment>;
pub fn list_payments_for_invoice(conn,business_id,invoice_id)->Result<Vec<Payment>>;

pub fn list_movements(conn,business_id,product_id:Option<&str>,limit:i64,offset:i64)->Result<(Vec<StockMovement>,i64)>;
pub fn list_activity(conn,business_id,category:&str,query:&str,limit:i64,offset:i64)->Result<(Vec<ActivityLog>,i64)>;
```

## services::billing.rs
```rust
pub struct CartLine { pub product:Product, pub quantity:f64, pub discount_percent:f64 }
pub struct Totals { pub subtotal:f64, pub discount:f64, pub tax:f64, pub total:f64, pub units:f64 }
pub fn calculate(lines:&[CartLine], invoice_discount_percent:f64)->Totals;
pub struct CartItemInput { pub product_id:String, pub quantity:f64, pub discount_percent:f64 }
pub struct CheckoutInput { pub customer_id:Option<String>, pub items:Vec<CartItemInput>, pub discount_percent:f64, pub transaction_ref:Option<String>, pub method:PaymentMethod, pub notes:Option<String> }
pub struct CheckoutResult { pub invoice:Invoice, pub payment:Payment }
pub fn checkout(conn:&Connection,business_id:&str,user_id:&str,input:CheckoutInput)->Result<CheckoutResult>;  // BEGIN IMMEDIATE, all-or-nothing
```
Checkout must: resolve walk-in customer when customer_id is None, allocate invoice number, compute totals with the same formula as `calculate`, insert invoice + items, confirm payment (status "confirmed", note "Manually confirmed by cashier"), increment `paid_amount`, set status Paid, decrement stock for tracked products exactly once, write stock movements (reason "sale") and activity logs ("invoice.create", "payment.confirm", "pos.checkout").

## services::inventory.rs
```rust
pub fn adjust_stock(conn:&Connection,business_id:&str,user_id:&str,product_id:&str,delta:f64,reason:&str,notes:Option<&str>,is_owner:bool)->Result<StockMovement>;
```
Staff allowed reasons: found/damaged/return/correction; abs(delta) <= 20; no negative stock. Owner unrestricted.

## services::payments.rs
```rust
pub fn build_upi_uri(vpa:&str,payee:&str,amount:f64,reference:&str,currency:&str)->String;
pub fn qr_matrix(uri:&str)->Result<(usize,Vec<bool>)>;   // (side length, row-major booleans)
pub fn qr_png(uri:&str)->Result<Vec<u8>>;
pub fn confirm_payment(conn:&Connection,business_id:&str,payment_id:&str,user_id:&str,reference:&str)->Result<Payment>;
```

## services::analytics.rs
```rust
pub struct TrendPoint { pub period:String, pub sales:f64, pub collections:f64 }
pub struct MethodRow { pub method:String, pub amount:f64, pub count:i64 }
pub struct TopProduct { pub name:String, pub quantity:f64, pub revenue:f64 }
pub struct TopCustomer { pub name:String, pub purchases:f64, pub count:i64 }
pub struct Analytics { pub today_sales:f64, pub today_transactions:i64, pub month_sales:f64, pub month_collections:f64, pub year_sales:f64, pub outstanding:f64, pub pending_invoices:i64, pub low_stock:i64, pub total_customers:i64, pub active_customers:i64, pub growth_percent:f64, pub sales_trend:Vec<TrendPoint>, pub methods:Vec<MethodRow>, pub top_products:Vec<TopProduct>, pub top_customers:Vec<TopCustomer>, pub recent_invoices:Vec<Invoice>, pub recent_payments:Vec<Payment> }
pub fn load(conn:&Connection,business_id:&str,from:Option<&str>,to:Option<&str>)->Result<Analytics>;
```
All values from SQLite records only, never hardcoded.

## services::reports.rs
```rust
pub fn sales_csv(conn:&Connection,business_id:&str,from:Option<&str>,to:Option<&str>)->Result<String>;
pub fn invoice_pdf(business:&Business,customer:&Customer,invoice:&Invoice,items:&[InvoiceItem])->Result<Vec<u8>>;
```

## services::seed.rs
`pub fn seed_demo(conn:&Connection)->Result<()>;` — idempotent; inserts sample products, customers, invoices and confirmed payments so the UI/analytics have real records.

## UI contract (desktop crate)
`billflow` binary uses eframe/egui 0.31. `main.rs` opens a native window, calls `eframe::run_native` with `App::new(db)`.
All UI code lives under `desktop/src/ui/`. The app must reproduce the existing BillFlow layout:
- **Login**: brand panel + centered form, email/password, eye toggle, demo credentials.
- **Staff POS**: minimal dark top bar (New Bill, Stock, logout), two-column body: left barcode input + product tiles/search, right cart with quantity controls, totals and "Proceed to Payment".
- **Checkout modal**: invoice number, business name, big total, two tabs (UPI QR / Cash), QR image from `qr_matrix`, UPI ID below QR, "Complete Sale" orange primary, "Cancel" secondary. Cancel preserves cart; Complete Sale calls `billing::checkout`, clears cart, shows receipt.
- **Admin**: 248px black sidebar (Overview, Billing, Inventory, Customers, Payments, Analytics, Staff, Activity, Settings), 72px top bar, white/soft-white content. Dashboard cards + charts, tables with pagination, settings, staff, activity, inventory adjustments.
- Colors ONLY: black `#0A0A0A`, white `#FFFFFF`, soft white `#F7F5F0`, orange `#FF6A00` (accent for clickable items). Muted text `#6B6862`, border `#E4E0D8`. No other accents, no gradients, no shadows on cards.
- Keep 6–10px corner radii, 1px borders, tabular numerals for money, 248px sidebar, comfortable spacing.
