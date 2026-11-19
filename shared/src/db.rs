//! SQLite storage: connection lifecycle, schema migrations and backup/restore.

use std::env;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use rusqlite::{Connection, DatabaseName};

use crate::error::Result;

/// Thread-safe handle to the application database.
pub struct Database {
    conn: Mutex<Connection>,
}

impl Database {
    /// Open (or create) a database at `path` and migrate it to the current schema.
    pub fn open(path: &Path) -> Result<Self> {
        if let Some(parent) = path.parent() {
            if !parent.as_os_str().is_empty() {
                std::fs::create_dir_all(parent)?;
            }
        }
        let conn = Connection::open(path)?;
        migrate(&conn)?;
        Ok(Self {
            conn: Mutex::new(conn),
        })
    }

    /// A throwaway, fully migrated in-memory database (handy for tests).
    pub fn in_memory() -> Result<Self> {
        let conn = Connection::open_in_memory()?;
        migrate(&conn)?;
        Ok(Self {
            conn: Mutex::new(conn),
        })
    }

    /// Lock the connection. The guard lets callers perform several operations
    /// (including an explicit transaction) atomically.
    pub fn conn(&self) -> std::sync::MutexGuard<'_, Connection> {
        self.conn.lock().expect("database mutex poisoned")
    }

    /// Write a consistent online backup to `target`.
    pub fn backup(&self, target: &Path) -> Result<()> {
        let guard = self.conn();
        guard.backup(DatabaseName::Main, target, None)?;
        Ok(())
    }

    /// Replace the contents of the current database with those of `source`.
    pub fn restore(&self, source: &Path) -> Result<()> {
        let mut guard = self.conn();
        guard.restore(DatabaseName::Main, source, None::<fn(rusqlite::backup::Progress)>)?;
        // Schema/busy settings are per-connection; make sure the restored
        // database still honours our invariants.
        guard.execute_batch("PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL;")?;
        Ok(())
    }
}

/// Platform-specific directory for application data.
pub fn app_data_dir() -> PathBuf {
    #[cfg(target_os = "windows")]
    {
        if let Ok(appdata) = env::var("APPDATA") {
            return PathBuf::from(appdata).join("BillFlow");
        }
        PathBuf::from(env::var("USERPROFILE").unwrap_or_else(|_| "C:\\".into()))
            .join("AppData")
            .join("Roaming")
            .join("BillFlow")
    }
    #[cfg(not(target_os = "windows"))]
    {
        if let Ok(home) = env::var("HOME") {
            return PathBuf::from(home).join(".local").join("share").join("billflow");
        }
        PathBuf::from(".local").join("share").join("billflow")
    }
}

/// Default on-disk location of the SQLite file.
pub fn default_db_path() -> PathBuf {
    app_data_dir().join("billflow.sqlite3")
}

/// True when `table` already exposes `column` (used to keep ALTERs idempotent).
fn has_column(conn: &Connection, table: &str, column: &str) -> Result<bool> {
    let mut stmt = conn.prepare(&format!("PRAGMA table_info({table})"))?;
    let names = stmt.query_map([], |row| row.get::<_, String>(1))?;
    for name in names {
        if name? == column {
            return Ok(true);
        }
    }
    Ok(false)
}

/// Idempotent, additive schema migration. Never drops or rewrites existing data.
pub fn migrate(conn: &Connection) -> Result<()> {
    conn.execute_batch(
        "PRAGMA foreign_keys = ON;
         PRAGMA journal_mode = WAL;
         PRAGMA synchronous = NORMAL;
         PRAGMA busy_timeout = 5000;
         CREATE TABLE IF NOT EXISTS businesses (
             id TEXT PRIMARY KEY,
             name TEXT NOT NULL,
             legal_name TEXT,
             email TEXT NOT NULL DEFAULT '',
             phone TEXT NOT NULL DEFAULT '',
             address TEXT NOT NULL DEFAULT '',
             city TEXT NOT NULL DEFAULT '',
             state TEXT NOT NULL DEFAULT '',
             pincode TEXT NOT NULL DEFAULT '',
             gstin TEXT NOT NULL DEFAULT '',
             upi_id TEXT NOT NULL DEFAULT '',
             upi_name TEXT NOT NULL DEFAULT '',
             logo_url TEXT,
             currency TEXT NOT NULL DEFAULT 'INR',
             invoice_prefix TEXT NOT NULL DEFAULT 'INV',
             invoice_footer TEXT,
             default_gst_rate REAL NOT NULL DEFAULT 18.0,
             low_stock_threshold REAL NOT NULL DEFAULT 10.0,
             invoice_sequence INTEGER NOT NULL DEFAULT 0,
             is_active INTEGER NOT NULL DEFAULT 1,
             created_at TEXT NOT NULL,
             updated_at TEXT NOT NULL
         );
         CREATE TABLE IF NOT EXISTS users (
             id TEXT PRIMARY KEY,
             business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
             full_name TEXT NOT NULL,
             email TEXT NOT NULL UNIQUE COLLATE NOCASE,
             phone TEXT,
             hashed_password TEXT NOT NULL,
             role TEXT NOT NULL DEFAULT 'staff',
             is_active INTEGER NOT NULL DEFAULT 1,
             last_login_at TEXT,
             created_at TEXT NOT NULL,
             updated_at TEXT NOT NULL
         );
         CREATE TABLE IF NOT EXISTS customers (
             id TEXT PRIMARY KEY,
             business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
             name TEXT NOT NULL,
             phone TEXT NOT NULL DEFAULT '',
             email TEXT NOT NULL DEFAULT '',
             address TEXT NOT NULL DEFAULT '',
             city TEXT NOT NULL DEFAULT '',
             state TEXT NOT NULL DEFAULT '',
             pincode TEXT NOT NULL DEFAULT '',
             gstin TEXT NOT NULL DEFAULT '',
             notes TEXT,
             is_active INTEGER NOT NULL DEFAULT 1,
             created_at TEXT NOT NULL,
             updated_at TEXT NOT NULL
         );
         CREATE TABLE IF NOT EXISTS products (
             id TEXT PRIMARY KEY,
             business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
             name TEXT NOT NULL,
             sku TEXT NOT NULL DEFAULT '',
             description TEXT NOT NULL DEFAULT '',
             unit TEXT NOT NULL DEFAULT 'pcs',
             hsn_code TEXT NOT NULL DEFAULT '',
             barcode TEXT,
             price REAL NOT NULL DEFAULT 0,
             gst_rate REAL NOT NULL DEFAULT 18.0,
             stock REAL NOT NULL DEFAULT 0,
             track_inventory INTEGER NOT NULL DEFAULT 1,
             is_service INTEGER NOT NULL DEFAULT 0,
              wholesale_discount_percent REAL NOT NULL DEFAULT 0,
             low_stock_threshold REAL NOT NULL DEFAULT 10.0,
             is_active INTEGER NOT NULL DEFAULT 1,
             created_at TEXT NOT NULL,
             updated_at TEXT NOT NULL
         );
         CREATE TABLE IF NOT EXISTS invoices (
             id TEXT PRIMARY KEY,
             business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
             customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
             customer_name TEXT,
             invoice_number TEXT NOT NULL,
             transaction_ref TEXT,
             issue_date TEXT NOT NULL,
             due_date TEXT,
             status TEXT NOT NULL DEFAULT 'unpaid',
              pricing_mode TEXT NOT NULL DEFAULT 'retail',
             subtotal REAL NOT NULL DEFAULT 0,
             discount_percent REAL NOT NULL DEFAULT 0,
             discount_amount REAL NOT NULL DEFAULT 0,
             taxable_amount REAL NOT NULL DEFAULT 0,
             tax_amount REAL NOT NULL DEFAULT 0,
             total_amount REAL NOT NULL DEFAULT 0,
             paid_amount REAL NOT NULL DEFAULT 0,
             balance_amount REAL NOT NULL DEFAULT 0,
             notes TEXT,
             created_at TEXT NOT NULL,
             updated_at TEXT NOT NULL,
             UNIQUE (business_id, invoice_number)
         );
         CREATE TABLE IF NOT EXISTS invoice_items (
             id TEXT PRIMARY KEY,
             invoice_id TEXT NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
             product_id TEXT REFERENCES products(id) ON DELETE SET NULL,
             description TEXT NOT NULL,
             quantity REAL NOT NULL,
             unit_price REAL NOT NULL,
              wholesale_discount_percent REAL NOT NULL DEFAULT 0,
             discount_percent REAL NOT NULL DEFAULT 0,
             discount_amount REAL NOT NULL DEFAULT 0,
             taxable_amount REAL NOT NULL DEFAULT 0,
             gst_rate REAL NOT NULL DEFAULT 0,
             tax_amount REAL NOT NULL DEFAULT 0,
             line_total REAL NOT NULL,
             sort_order INTEGER NOT NULL DEFAULT 0
         );
         CREATE TABLE IF NOT EXISTS payments (
             id TEXT PRIMARY KEY,
             business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
             invoice_id TEXT NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
             invoice_number TEXT,
             customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
             customer_name TEXT,
             amount REAL NOT NULL,
             method TEXT NOT NULL DEFAULT 'upi',
             status TEXT NOT NULL DEFAULT 'pending',
             reference TEXT,
             payment_date TEXT,
             notes TEXT,
             confirmed_at TEXT,
             confirmed_by TEXT,
             stock_adjusted INTEGER NOT NULL DEFAULT 0,
             created_at TEXT NOT NULL
         );
         CREATE TABLE IF NOT EXISTS stock_movements (
             id TEXT PRIMARY KEY,
             business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
             product_id TEXT REFERENCES products(id) ON DELETE SET NULL,
             product_name TEXT NOT NULL,
             sku TEXT,
             barcode TEXT,
             quantity_change REAL NOT NULL,
             quantity_before REAL NOT NULL,
             quantity_after REAL NOT NULL,
             reason TEXT NOT NULL,
             reference TEXT,
             performed_by_name TEXT NOT NULL DEFAULT 'system',
             notes TEXT,
             created_at TEXT NOT NULL
         );
         CREATE TABLE IF NOT EXISTS activity_logs (
             id TEXT PRIMARY KEY,
             business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
             user_id TEXT,
             user_name TEXT NOT NULL,
             action TEXT NOT NULL,
             category TEXT NOT NULL,
             reference TEXT,
             details TEXT,
             created_at TEXT NOT NULL
         );
         CREATE TABLE IF NOT EXISTS customer_interactions (
             id TEXT PRIMARY KEY,
             business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
             customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
             created_by TEXT,
             type TEXT NOT NULL DEFAULT 'note',
             content TEXT NOT NULL,
             created_at TEXT NOT NULL
         );
         CREATE INDEX IF NOT EXISTS ix_users_business ON users(business_id);
         CREATE INDEX IF NOT EXISTS ix_customers_business ON customers(business_id);
         CREATE INDEX IF NOT EXISTS ix_customers_phone ON customers(phone);
         CREATE INDEX IF NOT EXISTS ix_products_business ON products(business_id);
         CREATE INDEX IF NOT EXISTS ix_products_sku ON products(sku);
         CREATE INDEX IF NOT EXISTS ix_products_barcode ON products(barcode);
         CREATE INDEX IF NOT EXISTS ix_invoices_business ON invoices(business_id);
         CREATE INDEX IF NOT EXISTS ix_invoices_number ON invoices(invoice_number);
         CREATE INDEX IF NOT EXISTS ix_invoices_issue_date ON invoices(issue_date);
         CREATE INDEX IF NOT EXISTS ix_invoices_status ON invoices(status);
         CREATE INDEX IF NOT EXISTS ix_invoice_items_invoice ON invoice_items(invoice_id);
         CREATE INDEX IF NOT EXISTS ix_payments_business ON payments(business_id);
         CREATE INDEX IF NOT EXISTS ix_payments_invoice ON payments(invoice_id);
         CREATE INDEX IF NOT EXISTS ix_payments_status ON payments(status);
         CREATE INDEX IF NOT EXISTS ix_payments_reference ON payments(reference);
         CREATE INDEX IF NOT EXISTS ix_movements_business ON stock_movements(business_id);
         CREATE INDEX IF NOT EXISTS ix_movements_product ON stock_movements(product_id);
         CREATE INDEX IF NOT EXISTS ix_movements_created ON stock_movements(created_at);
         CREATE INDEX IF NOT EXISTS ix_activity_business ON activity_logs(business_id);
         CREATE INDEX IF NOT EXISTS ix_activity_category ON activity_logs(category);
         CREATE INDEX IF NOT EXISTS ix_activity_created ON activity_logs(created_at);
         CREATE INDEX IF NOT EXISTS ix_interactions_customer ON customer_interactions(customer_id);
         ",
    )?;

    // Additive supplier module schema. All statements are idempotent and
    // non-destructive: CREATE TABLE/INDEX IF NOT EXISTS only, with no ALTERs
    // or rewrites to any pre-existing table or row.
    conn.execute_batch(
        "CREATE TABLE IF NOT EXISTS suppliers (
             id TEXT PRIMARY KEY,
             business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
             name TEXT NOT NULL,
             contact_person TEXT,
             phone TEXT,
             whatsapp TEXT,
             email TEXT,
             address TEXT,
             category TEXT,
             brands TEXT,
             notes TEXT,
             is_active INTEGER NOT NULL DEFAULT 1,
             created_at TEXT NOT NULL,
             updated_at TEXT NOT NULL
         );
         CREATE TABLE IF NOT EXISTS supplier_products (
             id TEXT PRIMARY KEY,
             business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
             supplier_id TEXT NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
             product_id TEXT REFERENCES products(id) ON DELETE SET NULL,
             custom_name TEXT,
             supplier_sku TEXT,
             supplier_price REAL NOT NULL DEFAULT 0,
             unit TEXT,
             notes TEXT
         );
         CREATE TABLE IF NOT EXISTS purchase_reminder_lists (
             id TEXT PRIMARY KEY,
             business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
             supplier_id TEXT NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
             title TEXT NOT NULL,
             status TEXT NOT NULL DEFAULT 'pending',
             notes TEXT,
             created_by TEXT,
             created_at TEXT NOT NULL,
             updated_at TEXT NOT NULL
         );
         CREATE TABLE IF NOT EXISTS purchase_reminder_items (
             id TEXT PRIMARY KEY,
             list_id TEXT NOT NULL REFERENCES purchase_reminder_lists(id) ON DELETE CASCADE,
             product_id TEXT REFERENCES products(id) ON DELETE SET NULL,
             name TEXT NOT NULL,
             quantity REAL NOT NULL DEFAULT 0,
             unit TEXT,
             expected_price REAL,
             notes TEXT,
             is_purchased INTEGER NOT NULL DEFAULT 0,
             created_at TEXT NOT NULL,
             updated_at TEXT NOT NULL
         );
         CREATE TABLE IF NOT EXISTS supplier_visits (
             id TEXT PRIMARY KEY,
             business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
             supplier_id TEXT NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
             visit_date TEXT NOT NULL,
             discussion_notes TEXT,
             items_discussed TEXT,
             items_requested TEXT,
             follow_up TEXT,
             next_visit_date TEXT,
             notes TEXT,
             created_by TEXT,
             created_at TEXT NOT NULL,
             updated_at TEXT NOT NULL
         );
         CREATE TABLE IF NOT EXISTS supplier_purchases (
             id TEXT PRIMARY KEY,
             business_id TEXT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
             supplier_id TEXT NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
             purchase_number TEXT NOT NULL,
             purchase_date TEXT NOT NULL,
             reminder_list_id TEXT REFERENCES purchase_reminder_lists(id) ON DELETE SET NULL,
             notes TEXT,
             created_by TEXT,
             created_at TEXT NOT NULL,
             updated_at TEXT NOT NULL,
             UNIQUE (business_id, purchase_number)
         );
         CREATE TABLE IF NOT EXISTS supplier_purchase_items (
             id TEXT PRIMARY KEY,
             purchase_id TEXT NOT NULL REFERENCES supplier_purchases(id) ON DELETE CASCADE,
             product_id TEXT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
             quantity REAL NOT NULL,
             unit_price REAL NOT NULL,
             line_total REAL NOT NULL,
             reminder_item_id TEXT REFERENCES purchase_reminder_items(id) ON DELETE SET NULL
         );
         CREATE INDEX IF NOT EXISTS ix_suppliers_business ON suppliers(business_id);
         CREATE INDEX IF NOT EXISTS ix_suppliers_category ON suppliers(category);
         CREATE INDEX IF NOT EXISTS ix_supplier_products_business ON supplier_products(business_id);
         CREATE INDEX IF NOT EXISTS ix_supplier_products_supplier ON supplier_products(supplier_id);
         CREATE INDEX IF NOT EXISTS ix_supplier_products_product ON supplier_products(product_id);
         CREATE INDEX IF NOT EXISTS ix_reminder_lists_business ON purchase_reminder_lists(business_id);
         CREATE INDEX IF NOT EXISTS ix_reminder_lists_supplier ON purchase_reminder_lists(supplier_id);
         CREATE INDEX IF NOT EXISTS ix_reminder_items_list ON purchase_reminder_items(list_id);
         CREATE INDEX IF NOT EXISTS ix_reminder_items_product ON purchase_reminder_items(product_id);
         CREATE INDEX IF NOT EXISTS ix_supplier_visits_business ON supplier_visits(business_id);
         CREATE INDEX IF NOT EXISTS ix_supplier_visits_supplier ON supplier_visits(supplier_id);
         CREATE INDEX IF NOT EXISTS ix_supplier_purchases_business ON supplier_purchases(business_id);
         CREATE INDEX IF NOT EXISTS ix_supplier_purchases_supplier ON supplier_purchases(supplier_id);
         CREATE INDEX IF NOT EXISTS ix_supplier_purchase_items_purchase ON supplier_purchase_items(purchase_id);
         ",
     )?;

    // Additive upgrade for databases created before `confirmed_by` existed.
    let mut stmt = conn.prepare("PRAGMA table_info(payments)")?;
    let rows = stmt.query_map([], |row| row.get::<_, String>(1))?;
    let mut has_confirmed_by = false;
    for name in rows {
        if name? == "confirmed_by" {
            has_confirmed_by = true;
        }
    }
    drop(stmt);
    if !has_confirmed_by {
        conn.execute_batch("ALTER TABLE payments ADD COLUMN confirmed_by TEXT;")?;
    }

    // Additive upgrade: product-level discounts. Only add the two columns when
    // they are absent so existing rows (and repeated migrations) are untouched.
    let mut stmt = conn.prepare("PRAGMA table_info(products)")?;
    let rows = stmt.query_map([], |row| row.get::<_, String>(1))?;
    let mut has_discount_type = false;
    let mut has_discount_value = false;
    for name in rows {
        match name?.as_str() {
            "discount_type" => has_discount_type = true,
            "discount_value" => has_discount_value = true,
            _ => {}
        }
    }
    drop(stmt);
    if !has_discount_type {
        conn.execute_batch(
            "ALTER TABLE products ADD COLUMN discount_type TEXT NOT NULL DEFAULT 'none';",
        )?;
    }
    if !has_discount_value {
        conn.execute_batch(
            "ALTER TABLE products ADD COLUMN discount_value REAL NOT NULL DEFAULT 0;",
        )?;
    }

    // Additive upgrade: wholesale/retail pricing. Each column is added only
    // when absent, so repeated migrations and existing rows are never touched.
    if !has_column(conn, "products", "wholesale_discount_percent")? {
        conn.execute_batch(
            "ALTER TABLE products ADD COLUMN wholesale_discount_percent REAL NOT NULL DEFAULT 0;",
        )?;
    }
    if !has_column(conn, "invoices", "pricing_mode")? {
        conn.execute_batch(
            "ALTER TABLE invoices ADD COLUMN pricing_mode TEXT NOT NULL DEFAULT 'retail';",
        )?;
    }
    if !has_column(conn, "invoice_items", "wholesale_discount_percent")? {
        conn.execute_batch(
            "ALTER TABLE invoice_items ADD COLUMN wholesale_discount_percent REAL NOT NULL DEFAULT 0;",
        )?;
    }

    // Additive upgrade: free-text product unit and optional supplier-product
    // unit override. Both columns are added only when missing, so existing rows
    // and repeated migrations are never touched.
    if !has_column(conn, "products", "unit")? {
        conn.execute_batch(
            "ALTER TABLE products ADD COLUMN unit TEXT NOT NULL DEFAULT 'pcs';",
        )?;
    }
    if !has_column(conn, "supplier_products", "unit")? {
        conn.execute_batch("ALTER TABLE supplier_products ADD COLUMN unit TEXT;")?;
    }

    // One supplier cannot link the same real product twice. Custom-name items
    // (product_id IS NULL) are exempt. Deduplicate historical rows first, then
    // add a partial unique index. Reminder items keep their own snapshots, so
    // this cannot damage historical records.
    conn.execute_batch(
        "DELETE FROM supplier_products WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY business_id, supplier_id, product_id
                    ORDER BY id) AS rn
                FROM supplier_products WHERE product_id IS NOT NULL
            ) WHERE rn > 1
         );
         CREATE UNIQUE INDEX IF NOT EXISTS uq_supplier_product_link
           ON supplier_products (business_id, supplier_id, product_id)
           WHERE product_id IS NOT NULL;",
    )?;
    Ok(())
}
