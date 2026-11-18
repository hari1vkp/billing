//! CRUD repository. Every function takes a `&rusqlite::Connection` so callers
//! can compose several operations inside one transaction.

use chrono::Datelike;
use rusqlite::{params, params_from_iter, types::Value, Connection, OptionalExtension, Row};

use crate::audit;
use crate::error::{BillflowError, Result};
use crate::models::*;
use crate::util::{self, rb, ro, rs};

const INVOICE_SELECT: &str =
    "SELECT i.*, c.name AS cust_name FROM invoices i \
     LEFT JOIN customers c ON c.id = i.customer_id ";
const PAYMENT_SELECT: &str =
    "SELECT p.*, i.invoice_number AS inv_number, c.name AS cust_name FROM payments p \
     LEFT JOIN invoices i ON i.id = p.invoice_id \
     LEFT JOIN customers c ON c.id = p.customer_id ";

// ---------------------------------------------------------------------------
// Row mappers
// ---------------------------------------------------------------------------

fn business_from_row(row: &Row<'_>) -> rusqlite::Result<Business> {
    Ok(Business {
        id: row.get("id")?,
        name: row.get("name")?,
        legal_name: ro(row, "legal_name")?,
        email: rs(row, "email")?,
        phone: rs(row, "phone")?,
        address: rs(row, "address")?,
        city: rs(row, "city")?,
        state: rs(row, "state")?,
        pincode: rs(row, "pincode")?,
        gstin: rs(row, "gstin")?,
        upi_id: rs(row, "upi_id")?,
        upi_name: rs(row, "upi_name")?,
        logo_url: ro(row, "logo_url")?,
        currency: rs(row, "currency")?,
        invoice_prefix: rs(row, "invoice_prefix")?,
        invoice_footer: ro(row, "invoice_footer")?,
        default_gst_rate: row.get("default_gst_rate")?,
        low_stock_threshold: row.get("low_stock_threshold")?,
        invoice_sequence: row.get("invoice_sequence")?,
        created_at: row.get("created_at")?,
    })
}

fn customer_from_row(row: &Row<'_>) -> rusqlite::Result<Customer> {
    Ok(Customer {
        id: row.get("id")?,
        business_id: row.get("business_id")?,
        name: row.get("name")?,
        phone: rs(row, "phone")?,
        email: rs(row, "email")?,
        address: rs(row, "address")?,
        city: rs(row, "city")?,
        state: rs(row, "state")?,
        pincode: rs(row, "pincode")?,
        gstin: rs(row, "gstin")?,
        notes: ro(row, "notes")?,
        is_active: rb(row, "is_active")?,
        created_at: row.get("created_at")?,
        updated_at: row.get("updated_at")?,
    })
}

fn product_from_row(row: &Row<'_>) -> rusqlite::Result<Product> {
    Ok(Product {
        id: row.get("id")?,
        business_id: row.get("business_id")?,
        name: row.get("name")?,
        sku: rs(row, "sku")?,
        description: rs(row, "description")?,
        hsn_code: rs(row, "hsn_code")?,
        barcode: ro(row, "barcode")?,
        price: row.get("price")?,
        gst_rate: row.get("gst_rate")?,
        stock: row.get("stock")?,
        track_inventory: rb(row, "track_inventory")?,
        is_service: rb(row, "is_service")?,
        low_stock_threshold: row.get("low_stock_threshold")?,
        discount_type: rs(row, "discount_type")?,
        discount_value: row.get("discount_value")?,
        is_active: rb(row, "is_active")?,
        created_at: row.get("created_at")?,
        updated_at: row.get("updated_at")?,
    })
}

fn invoice_from_row(row: &Row<'_>) -> rusqlite::Result<Invoice> {
    Ok(Invoice {
        id: row.get("id")?,
        business_id: row.get("business_id")?,
        customer_id: row.get("customer_id")?,
        customer_name: ro(row, "cust_name")?.or_else(|| ro(row, "customer_name").ok().flatten()),
        invoice_number: row.get("invoice_number")?,
        transaction_ref: ro(row, "transaction_ref")?,
        issue_date: row.get("issue_date")?,
        due_date: ro(row, "due_date")?,
        status: InvoiceStatus::from_str(&rs(row, "status")?),
        subtotal: row.get("subtotal")?,
        discount_percent: row.get("discount_percent")?,
        discount_amount: row.get("discount_amount")?,
        taxable_amount: row.get("taxable_amount")?,
        tax_amount: row.get("tax_amount")?,
        total_amount: row.get("total_amount")?,
        paid_amount: row.get("paid_amount")?,
        balance_amount: row.get("balance_amount")?,
        notes: ro(row, "notes")?,
        created_at: row.get("created_at")?,
        updated_at: row.get("updated_at")?,
    })
}

fn item_from_row(row: &Row<'_>) -> rusqlite::Result<InvoiceItem> {
    Ok(InvoiceItem {
        id: row.get("id")?,
        invoice_id: row.get("invoice_id")?,
        product_id: ro(row, "product_id")?,
        description: row.get("description")?,
        quantity: row.get("quantity")?,
        unit_price: row.get("unit_price")?,
        discount_percent: row.get("discount_percent")?,
        discount_amount: row.get("discount_amount")?,
        taxable_amount: row.get("taxable_amount")?,
        gst_rate: row.get("gst_rate")?,
        tax_amount: row.get("tax_amount")?,
        line_total: row.get("line_total")?,
        sort_order: row.get("sort_order")?,
    })
}

fn payment_from_row(row: &Row<'_>) -> rusqlite::Result<Payment> {
    Ok(Payment {
        id: row.get("id")?,
        business_id: row.get("business_id")?,
        invoice_id: row.get("invoice_id")?,
        invoice_number: ro(row, "inv_number")?.or_else(|| ro(row, "invoice_number").ok().flatten()),
        customer_id: row.get("customer_id")?,
        customer_name: ro(row, "cust_name")?.or_else(|| ro(row, "customer_name").ok().flatten()),
        amount: row.get("amount")?,
        method: PaymentMethod::from_str(&rs(row, "method")?),
        status: rs(row, "status")?,
        reference: ro(row, "reference")?,
        payment_date: ro(row, "payment_date")?,
        notes: ro(row, "notes")?,
        confirmed_at: ro(row, "confirmed_at")?,
        created_at: row.get("created_at")?,
    })
}

fn movement_from_row(row: &Row<'_>) -> rusqlite::Result<StockMovement> {
    Ok(StockMovement {
        id: row.get("id")?,
        business_id: row.get("business_id")?,
        product_id: row.get("product_id")?,
        product_name: row.get("product_name")?,
        sku: ro(row, "sku")?,
        barcode: ro(row, "barcode")?,
        quantity_change: row.get("quantity_change")?,
        quantity_before: row.get("quantity_before")?,
        quantity_after: row.get("quantity_after")?,
        reason: row.get("reason")?,
        reference: ro(row, "reference")?,
        performed_by_name: rs(row, "performed_by_name")?,
        notes: ro(row, "notes")?,
        created_at: row.get("created_at")?,
    })
}

fn activity_from_row(row: &Row<'_>) -> rusqlite::Result<ActivityLog> {
    Ok(ActivityLog {
        id: row.get("id")?,
        business_id: row.get("business_id")?,
        user_id: ro(row, "user_id")?,
        user_name: row.get("user_name")?,
        action: row.get("action")?,
        category: row.get("category")?,
        reference: ro(row, "reference")?,
        details: ro(row, "details")?,
        created_at: row.get("created_at")?,
    })
}

// ---------------------------------------------------------------------------
// Business
// ---------------------------------------------------------------------------

pub fn get_business(conn: &Connection, business_id: &str) -> Result<Business> {
    conn.query_row(
        "SELECT * FROM businesses WHERE id = ?1",
        params![business_id],
        business_from_row,
    )
    .map_err(|e| match e {
        rusqlite::Error::QueryReturnedNoRows => {
            BillflowError::NotFound("Business not found".into())
        }
        other => BillflowError::Db(other),
    })
}

/// Editable business settings.
#[derive(Clone, Debug, PartialEq)]
pub struct BusinessInput {
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
    pub currency: String,
    pub invoice_prefix: String,
    pub invoice_footer: Option<String>,
    pub default_gst_rate: f64,
    pub low_stock_threshold: f64,
}

pub fn update_business(
    conn: &Connection,
    business_id: &str,
    input: &BusinessInput,
) -> Result<Business> {
    let changed = conn.execute(
        "UPDATE businesses SET name=?1, legal_name=?2, email=?3, phone=?4, address=?5, \
         city=?6, state=?7, pincode=?8, gstin=?9, upi_id=?10, upi_name=?11, currency=?12, \
         invoice_prefix=?13, invoice_footer=?14, default_gst_rate=?15, \
         low_stock_threshold=?16, updated_at=?17 WHERE id=?18",
        params![
            input.name,
            input.legal_name,
            input.email,
            input.phone,
            input.address,
            input.city,
            input.state,
            input.pincode,
            input.gstin,
            input.upi_id,
            input.upi_name,
            input.currency,
            input.invoice_prefix,
            input.invoice_footer,
            input.default_gst_rate,
            input.low_stock_threshold,
            util::now_iso(),
            business_id,
        ],
    )?;
    if changed == 0 {
        return Err(BillflowError::NotFound("Business not found".into()));
    }
    get_business(conn, business_id)
}

/// Create the default tenant + owner on a fresh database. Safe to call twice.
pub fn bootstrap(conn: &Connection) -> Result<(Business, User)> {
    let mut stmt = conn.prepare("SELECT * FROM businesses ORDER BY created_at ASC LIMIT 1")?;
    let existing = stmt
        .query_map([], business_from_row)?
        .next()
        .transpose()?;
    drop(stmt);

    let business = match existing {
        Some(b) => b,
        None => {
            let id = util::uuid();
            let now = util::now_iso();
            conn.execute(
                "INSERT INTO businesses (id, name, legal_name, email, phone, address, city, \
                 state, pincode, gstin, upi_id, upi_name, logo_url, currency, invoice_prefix, \
                 invoice_footer, default_gst_rate, low_stock_threshold, invoice_sequence, \
                 is_active, created_at, updated_at) \
                 VALUES (?1, 'BillFlow Demo', 'BillFlow Demo', 'demo@billingapp.com', '', '', '', \
                 '', '', '', 'billflowdemo@upi', 'BillFlow Demo', NULL, 'INR', 'INV', \
                 'Thank you for your business!', 18.0, 10.0, 0, 1, ?2, ?2)",
                params![id, now],
            )?;
            get_business(conn, &id)?
        }
    };

    let owner: Option<User> = conn
        .prepare(
            "SELECT * FROM users WHERE business_id = ?1 AND role = 'owner' \
             ORDER BY created_at ASC LIMIT 1",
        )?
        .query_map(params![business.id], crate::auth::user_from_row)?
        .next()
        .transpose()?;

    let user = match owner {
        Some(u) => u,
        None => crate::auth::create_user(
            conn,
            &business.id,
            "Demo Owner",
            "demo@billingapp.com",
            None,
            "Demo@1234",
            Role::Owner,
        )?,
    };
    Ok((business, user))
}

// ---------------------------------------------------------------------------
// Products
// ---------------------------------------------------------------------------

pub fn list_products(
    conn: &Connection,
    business_id: &str,
    query: &str,
    low_stock_only: bool,
    limit: i64,
    offset: i64,
) -> Result<(Vec<Product>, i64)> {
    let mut where_clause = String::from("business_id = ?1 AND is_active = 1");
    let mut vals: Vec<Value> = vec![Value::Text(business_id.to_string())];
    if !query.trim().is_empty() {
        vals.push(Value::Text(format!("%{}%", query.trim())));
        let p = vals.len();
        where_clause.push_str(&format!(
            " AND (name LIKE ?{p} OR sku LIKE ?{p} OR barcode LIKE ?{p} OR hsn_code LIKE ?{p})"
        ));
    }
    if low_stock_only {
        where_clause.push_str(" AND track_inventory = 1 AND stock <= low_stock_threshold");
    }
    let sql = format!("SELECT * FROM products WHERE {where_clause}");
    let total: i64 = conn.query_row(
        &format!("SELECT COUNT(*) FROM products WHERE {where_clause}"),
        params_from_iter(vals.iter()),
        |row| row.get(0),
    )?;

    vals.push(Value::Integer(limit));
    vals.push(Value::Integer(offset));
    let p = vals.len();
    let mut stmt = conn.prepare(&format!(
        "{sql} ORDER BY created_at DESC, name ASC LIMIT ?{} OFFSET ?{}",
        p - 1, p
    ))?;
    let rows = stmt.query(params_from_iter(vals.iter()))?;
    Ok((util::all(rows, product_from_row)?, total))
}

pub fn get_product(conn: &Connection, business_id: &str, id: &str) -> Result<Option<Product>> {
    conn.query_row(
        "SELECT * FROM products WHERE business_id = ?1 AND id = ?2",
        params![business_id, id],
        product_from_row,
    )
    .optional()
    .map_err(BillflowError::Db)
}

pub fn get_product_by_barcode(
    conn: &Connection,
    business_id: &str,
    barcode: &str,
) -> Result<Option<Product>> {
    conn.query_row(
        "SELECT * FROM products WHERE business_id = ?1 AND barcode = ?2 AND is_active = 1 \
         ORDER BY created_at ASC LIMIT 1",
        params![business_id, barcode],
        product_from_row,
    )
    .optional()
    .map_err(BillflowError::Db)
}

#[derive(Clone, Debug, PartialEq)]
pub struct ProductInput {
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
}

pub fn insert_product(
    conn: &Connection,
    business_id: &str,
    input: &ProductInput,
) -> Result<Product> {
    let id = util::uuid();
    let now = util::now_iso();
    conn.execute(
        "INSERT INTO products (id, business_id, name, sku, description, hsn_code, barcode, \
         price, gst_rate, stock, track_inventory, is_service, low_stock_threshold, is_active, \
         created_at, updated_at) \
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, 1, ?14, ?14)",
        params![
            id,
            business_id,
            input.name,
            input.sku,
            input.description,
            input.hsn_code,
            input.barcode,
            input.price,
            input.gst_rate,
            input.stock,
            input.track_inventory as i64,
            input.is_service as i64,
            input.low_stock_threshold,
            now,
        ],
    )?;
    Ok(get_product(conn, business_id, &id)?.expect("just inserted"))
}

pub fn update_product(
    conn: &Connection,
    business_id: &str,
    id: &str,
    input: &ProductInput,
) -> Result<Product> {
    let changed = conn.execute(
        "UPDATE products SET name=?1, sku=?2, description=?3, hsn_code=?4, barcode=?5, \
         price=?6, gst_rate=?7, stock=?8, track_inventory=?9, is_service=?10, \
         low_stock_threshold=?11, updated_at=?12 WHERE id=?13 AND business_id=?14",
        params![
            input.name,
            input.sku,
            input.description,
            input.hsn_code,
            input.barcode,
            input.price,
            input.gst_rate,
            input.stock,
            input.track_inventory as i64,
            input.is_service as i64,
            input.low_stock_threshold,
            util::now_iso(),
            id,
            business_id,
        ],
    )?;
    if changed == 0 {
        return Err(BillflowError::NotFound("Product not found".into()));
    }
    Ok(get_product(conn, business_id, id)?.expect("just updated"))
}

pub fn archive_product(conn: &Connection, business_id: &str, id: &str) -> Result<()> {
    let changed = conn.execute(
        "UPDATE products SET is_active = 0, updated_at = ?1 \
         WHERE id = ?2 AND business_id = ?3",
        params![util::now_iso(), id, business_id],
    )?;
    if changed == 0 {
        return Err(BillflowError::NotFound("Product not found".into()));
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Customers
// ---------------------------------------------------------------------------

#[derive(Clone, Debug, Default, PartialEq)]
pub struct CustomerInput {
    pub name: String,
    pub phone: Option<String>,
    pub email: Option<String>,
    pub address: Option<String>,
    pub city: Option<String>,
    pub state: Option<String>,
    pub pincode: Option<String>,
    pub gstin: Option<String>,
    pub notes: Option<String>,
}

pub fn list_customers(
    conn: &Connection,
    business_id: &str,
    query: &str,
    limit: i64,
    offset: i64,
) -> Result<(Vec<Customer>, i64)> {
    let mut clause = String::from("business_id = ?1 AND is_active = 1");
    let mut vals: Vec<Value> = vec![Value::Text(business_id.to_string())];
    if !query.trim().is_empty() {
        vals.push(Value::Text(format!("%{}%", query.trim())));
        let p = vals.len();
        clause.push_str(&format!(
            " AND (name LIKE ?{p} OR phone LIKE ?{p} OR email LIKE ?{p} OR gstin LIKE ?{p})"
        ));
    }
    let total: i64 = conn.query_row(
        &format!("SELECT COUNT(*) FROM customers WHERE {clause}"),
        params_from_iter(vals.iter()),
        |row| row.get(0),
    )?;
    vals.push(Value::Integer(limit));
    vals.push(Value::Integer(offset));
    let p = vals.len();
    let mut stmt = conn.prepare(&format!(
        "SELECT * FROM customers WHERE {clause} \
         ORDER BY created_at DESC, name ASC LIMIT ?{} OFFSET ?{}",
        p - 1, p
    ))?;
    let rows = stmt.query(params_from_iter(vals.iter()))?;
    Ok((util::all(rows, customer_from_row)?, total))
}

pub fn get_customer(conn: &Connection, business_id: &str, id: &str) -> Result<Option<Customer>> {
    conn.query_row(
        "SELECT * FROM customers WHERE business_id = ?1 AND id = ?2",
        params![business_id, id],
        customer_from_row,
    )
    .optional()
    .map_err(BillflowError::Db)
}

fn insert_customer_with(
    conn: &Connection,
    business_id: &str,
    input: &CustomerInput,
    name: &str,
) -> Result<Customer> {
    let id = util::uuid();
    let now = util::now_iso();
    conn.execute(
        "INSERT INTO customers (id, business_id, name, phone, email, address, city, state, \
         pincode, gstin, notes, is_active, created_at, updated_at) \
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, 1, ?12, ?12)",
        params![
            id,
            business_id,
            name,
            input.phone.as_deref().unwrap_or(""),
            input.email.as_deref().unwrap_or(""),
            input.address.as_deref().unwrap_or(""),
            input.city.as_deref().unwrap_or(""),
            input.state.as_deref().unwrap_or(""),
            input.pincode.as_deref().unwrap_or(""),
            input.gstin.as_deref().unwrap_or(""),
            input.notes,
            now,
        ],
    )?;
    Ok(get_customer(conn, business_id, &id)?.expect("just inserted"))
}

pub fn insert_customer(
    conn: &Connection,
    business_id: &str,
    input: &CustomerInput,
) -> Result<Customer> {
    insert_customer_with(conn, business_id, input, &input.name)
}

pub fn update_customer(
    conn: &Connection,
    business_id: &str,
    id: &str,
    input: &CustomerInput,
) -> Result<Customer> {
    let changed = conn.execute(
        "UPDATE customers SET name=?1, phone=?2, email=?3, address=?4, city=?5, state=?6, \
         pincode=?7, gstin=?8, notes=?9, updated_at=?10 WHERE id=?11 AND business_id=?12",
        params![
            input.name,
            input.phone.as_deref().unwrap_or(""),
            input.email.as_deref().unwrap_or(""),
            input.address.as_deref().unwrap_or(""),
            input.city.as_deref().unwrap_or(""),
            input.state.as_deref().unwrap_or(""),
            input.pincode.as_deref().unwrap_or(""),
            input.gstin.as_deref().unwrap_or(""),
            input.notes,
            util::now_iso(),
            id,
            business_id,
        ],
    )?;
    if changed == 0 {
        return Err(BillflowError::NotFound("Customer not found".into()));
    }
    Ok(get_customer(conn, business_id, id)?.expect("just updated"))
}

pub fn customer_stats(
    conn: &Connection,
    business_id: &str,
    customer_id: &str,
) -> Result<CustomerStats> {
    let stats = conn.query_row(
        "SELECT \
           COALESCE(SUM(CASE WHEN status != 'cancelled' THEN total_amount ELSE 0 END), 0), \
           COUNT(CASE WHEN status != 'cancelled' THEN 1 END), \
           COALESCE(SUM(CASE WHEN status IN ('unpaid','partially_paid') THEN balance_amount ELSE 0 END), 0), \
           MAX(issue_date) \
         FROM invoices WHERE business_id = ?1 AND customer_id = ?2",
        params![business_id, customer_id],
        |row| {
            Ok(CustomerStats {
                total_purchases: row.get(0)?,
                invoice_count: row.get(1)?,
                outstanding_balance: row.get(2)?,
                last_invoice_date: row.get(3)?,
                last_transaction_date: None,
            })
        },
    )?;
    let last_payment: Option<String> = conn
        .query_row(
            "SELECT MAX(COALESCE(payment_date, substr(created_at, 1, 10))) FROM payments \
             WHERE business_id = ?1 AND customer_id = ?2",
            params![business_id, customer_id],
            |row| row.get(0),
        )?;
    Ok(CustomerStats {
        last_transaction_date: last_payment,
        ..stats
    })
}

pub fn list_interactions(
    conn: &Connection,
    business_id: &str,
    customer_id: &str,
) -> Result<Vec<(String, String, String)>> {
    let mut stmt = conn.prepare(
        "SELECT \"type\", content, created_at FROM customer_interactions \
         WHERE business_id = ?1 AND customer_id = ?2 ORDER BY created_at DESC",
    )?;
    let mut rows = stmt.query(params![business_id, customer_id])?;
    let mut out = Vec::new();
    while let Some(row) = rows.next()? {
        out.push((row.get(0)?, row.get(1)?, row.get(2)?));
    }
    Ok(out)
}

pub fn add_interaction(
    conn: &Connection,
    business_id: &str,
    customer_id: &str,
    user_id: Option<&str>,
    type_: &str,
    content: &str,
) -> Result<()> {
    conn.execute(
        "INSERT INTO customer_interactions \
         (id, business_id, customer_id, created_by, \"type\", content, created_at) \
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
        params![
            util::uuid(),
            business_id,
            customer_id,
            user_id,
            type_,
            content,
            util::now_iso(),
        ],
    )?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Invoices
// ---------------------------------------------------------------------------

pub fn list_invoices(
    conn: &Connection,
    business_id: &str,
    query: &str,
    status: &str,
    limit: i64,
    offset: i64,
) -> Result<(Vec<Invoice>, i64)> {
    let mut clause = String::from("i.business_id = ?1");
    let mut vals: Vec<Value> = vec![Value::Text(business_id.to_string())];
    if !query.trim().is_empty() {
        vals.push(Value::Text(format!("%{}%", query.trim())));
        let p = vals.len();
        clause.push_str(&format!(
            " AND (i.invoice_number LIKE ?{p} OR COALESCE(c.name, '') LIKE ?{p} \
             OR COALESCE(i.transaction_ref, '') LIKE ?{p})"
        ));
    }
    if !status.trim().is_empty() {
        vals.push(Value::Text(status.trim().to_string()));
        clause.push_str(&format!(" AND i.status = ?{}", vals.len()));
    }
    let from = format!("FROM invoices i LEFT JOIN customers c ON c.id = i.customer_id WHERE {clause}");
    let total: i64 = conn.query_row(&format!("SELECT COUNT(*) {from}"), params_from_iter(vals.iter()), |row| row.get(0))?;
    vals.push(Value::Integer(limit));
    vals.push(Value::Integer(offset));
    let p = vals.len();
    let mut stmt = conn.prepare(&format!(
        "SELECT i.*, c.name AS cust_name {from} \
         ORDER BY i.issue_date DESC, i.created_at DESC LIMIT ?{} OFFSET ?{}",
        p - 1, p
    ))?;
    let rows = stmt.query(params_from_iter(vals.iter()))?;
    Ok((util::all(rows, invoice_from_row)?, total))
}

pub fn get_invoice(conn: &Connection, business_id: &str, id: &str) -> Result<InvoiceDetail> {
    let invoice: Invoice = conn
        .query_row(
            &format!("{INVOICE_SELECT} WHERE i.business_id = ?1 AND i.id = ?2"),
            params![business_id, id],
            invoice_from_row,
        )
        .map_err(|e| match e {
            rusqlite::Error::QueryReturnedNoRows => {
                BillflowError::NotFound("Invoice not found".into())
            }
            other => BillflowError::Db(other),
        })?;

    let mut stmt = conn.prepare(
        "SELECT * FROM invoice_items WHERE invoice_id = ?1 ORDER BY sort_order ASC, id ASC",
    )?;
    let items = util::all(stmt.query(params![id])?, item_from_row)?;
    drop(stmt);

    let mut stmt = conn.prepare(&format!(
        "{PAYMENT_SELECT} WHERE p.business_id = ?1 AND p.invoice_id = ?2 ORDER BY p.created_at ASC"
    ))?;
    let payments = util::all(stmt.query(params![business_id, id])?, payment_from_row)?;
    Ok(InvoiceDetail {
        invoice,
        items,
        payments,
    })
}

/// Allocate and persist the next invoice number for a tenant.
pub fn next_invoice_number(conn: &Connection, business_id: &str) -> Result<String> {
    let (prefix, sequence): (String, i64) = conn.query_row(
        "SELECT invoice_prefix, invoice_sequence FROM businesses WHERE id = ?1",
        params![business_id],
        |row| Ok((rs(row, "invoice_prefix")?, row.get("invoice_sequence")?)),
    )?;
    let year = chrono::Utc::now().year();
    let mut next = sequence + 1;
    loop {
        let number = format!("{}-{}-{:05}", prefix, year, next);
        let used: i64 = conn.query_row(
            "SELECT COUNT(*) FROM invoices WHERE business_id = ?1 AND invoice_number = ?2",
            params![business_id, number],
            |row| row.get(0),
        )?;
        if used == 0 {
            conn.execute(
                "UPDATE businesses SET invoice_sequence = ?1, updated_at = ?2 WHERE id = ?3",
                params![next, util::now_iso(), business_id],
            )?;
            return Ok(number);
        }
        next += 1;
    }
}

pub fn set_invoice_status(
    conn: &Connection,
    business_id: &str,
    id: &str,
    status: InvoiceStatus,
    user_id: Option<&str>,
) -> Result<Invoice> {
    let changed = conn.execute(
        "UPDATE invoices SET status = ?1, updated_at = ?2 WHERE id = ?3 AND business_id = ?4",
        params![status.as_str(), util::now_iso(), id, business_id],
    )?;
    if changed == 0 {
        return Err(BillflowError::NotFound("Invoice not found".into()));
    }
    audit::log(
        conn,
        business_id,
        user_id,
        if status == InvoiceStatus::Cancelled {
            "invoice.cancel"
        } else {
            "invoice.status"
        },
        "invoice",
        None,
        Some(status.as_str()),
    )?;
    Ok(get_invoice(conn, business_id, id)?.invoice)
}

// ---------------------------------------------------------------------------
// Payments
// ---------------------------------------------------------------------------

pub fn list_payments(
    conn: &Connection,
    business_id: &str,
    query: &str,
    status: &str,
    limit: i64,
    offset: i64,
) -> Result<(Vec<Payment>, i64)> {
    let mut clause = String::from("p.business_id = ?1");
    let mut vals: Vec<Value> = vec![Value::Text(business_id.to_string())];
    if !query.trim().is_empty() {
        vals.push(Value::Text(format!("%{}%", query.trim())));
        let p = vals.len();
        clause.push_str(&format!(
            " AND (COALESCE(p.reference, '') LIKE ?{p} OR COALESCE(i.invoice_number, '') LIKE ?{p} \
             OR COALESCE(c.name, '') LIKE ?{p})"
        ));
    }
    if !status.trim().is_empty() {
        vals.push(Value::Text(status.trim().to_string()));
        clause.push_str(&format!(" AND p.status = ?{}", vals.len()));
    }
    let from = format!(
        "FROM payments p LEFT JOIN invoices i ON i.id = p.invoice_id \
         LEFT JOIN customers c ON c.id = p.customer_id WHERE {clause}"
    );
    let total: i64 = conn.query_row(
        &format!("SELECT COUNT(*) {from}"),
        params_from_iter(vals.iter()),
        |row| row.get(0),
    )?;
    vals.push(Value::Integer(limit));
    vals.push(Value::Integer(offset));
    let p = vals.len();
    let mut stmt = conn.prepare(&format!(
        "SELECT p.*, i.invoice_number AS inv_number, c.name AS cust_name {from} \
         ORDER BY p.created_at DESC LIMIT ?{} OFFSET ?{}",
        p - 1, p
    ))?;
    let rows = stmt.query(params_from_iter(vals.iter()))?;
    Ok((util::all(rows, payment_from_row)?, total))
}

pub fn get_payment(conn: &Connection, business_id: &str, id: &str) -> Result<Payment> {
    conn.query_row(
        &format!("{PAYMENT_SELECT} WHERE p.business_id = ?1 AND p.id = ?2"),
        params![business_id, id],
        payment_from_row,
    )
    .map_err(|e| match e {
        rusqlite::Error::QueryReturnedNoRows => BillflowError::NotFound("Payment not found".into()),
        other => BillflowError::Db(other),
    })
}

pub fn list_payments_for_invoice(
    conn: &Connection,
    business_id: &str,
    invoice_id: &str,
) -> Result<Vec<Payment>> {
    let mut stmt = conn.prepare(&format!(
        "{PAYMENT_SELECT} WHERE p.business_id = ?1 AND p.invoice_id = ?2 ORDER BY p.created_at ASC"
    ))?;
    let rows = stmt.query(params![business_id, invoice_id])?;
    let payments = util::all(rows, payment_from_row)?;
    Ok(payments)
}

// ---------------------------------------------------------------------------
// Stock movements & activity
// ---------------------------------------------------------------------------

pub fn list_movements(
    conn: &Connection,
    business_id: &str,
    product_id: Option<&str>,
    limit: i64,
    offset: i64,
) -> Result<(Vec<StockMovement>, i64)> {
    let mut clause = String::from("business_id = ?1");
    let mut vals: Vec<Value> = vec![Value::Text(business_id.to_string())];
    if let Some(pid) = product_id {
        vals.push(Value::Text(pid.to_string()));
        clause.push_str(&format!(" AND product_id = ?{}", vals.len()));
    }
    let total: i64 = conn.query_row(
        &format!("SELECT COUNT(*) FROM stock_movements WHERE {clause}"),
        params_from_iter(vals.iter()),
        |row| row.get(0),
    )?;
    vals.push(Value::Integer(limit));
    vals.push(Value::Integer(offset));
    let p = vals.len();
    let mut stmt = conn.prepare(&format!(
        "SELECT * FROM stock_movements WHERE {clause} \
         ORDER BY created_at DESC, id DESC LIMIT ?{} OFFSET ?{}",
        p - 1, p
    ))?;
    let rows = stmt.query(params_from_iter(vals.iter()))?;
    Ok((util::all(rows, movement_from_row)?, total))
}

pub fn list_activity(
    conn: &Connection,
    business_id: &str,
    category: &str,
    query: &str,
    limit: i64,
    offset: i64,
) -> Result<(Vec<ActivityLog>, i64)> {
    let mut clause = String::from("business_id = ?1");
    let mut vals: Vec<Value> = vec![Value::Text(business_id.to_string())];
    if !category.trim().is_empty() {
        vals.push(Value::Text(category.trim().to_string()));
        clause.push_str(&format!(" AND category = ?{}", vals.len()));
    }
    if !query.trim().is_empty() {
        vals.push(Value::Text(format!("%{}%", query.trim())));
        let p = vals.len();
        clause.push_str(&format!(
            " AND (user_name LIKE ?{p} OR action LIKE ?{p} OR category LIKE ?{p} \
             OR COALESCE(reference, '') LIKE ?{p})"
        ));
    }
    let total: i64 = conn.query_row(
        &format!("SELECT COUNT(*) FROM activity_logs WHERE {clause}"),
        params_from_iter(vals.iter()),
        |row| row.get(0),
    )?;
    vals.push(Value::Integer(limit));
    vals.push(Value::Integer(offset));
    let p = vals.len();
    let mut stmt = conn.prepare(&format!(
        "SELECT * FROM activity_logs WHERE {clause} \
         ORDER BY created_at DESC, id DESC LIMIT ?{} OFFSET ?{}",
        p - 1, p
    ))?;
    let rows = stmt.query(params_from_iter(vals.iter()))?;
    Ok((util::all(rows, activity_from_row)?, total))
}

/// Public helper used by the services to create the walk-in customer.
pub(crate) fn resolve_or_create_walk_in(conn: &Connection, business_id: &str) -> Result<Customer> {
    let mut stmt = conn.prepare(
        "SELECT * FROM customers WHERE business_id = ?1 AND name = 'Walk-in Customer' \
         AND is_active = 1 ORDER BY created_at ASC LIMIT 1",
    )?;
    let found = stmt
        .query_map(params![business_id], customer_from_row)?
        .next()
        .transpose()?;
    drop(stmt);
    match found {
        Some(c) => Ok(c),
        None => insert_customer_with(
            conn,
            business_id,
            &CustomerInput::default(),
            "Walk-in Customer",
        ),
    }
}
