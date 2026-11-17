//! Idempotent demo data for a fresh installation.

use chrono::{Duration, Utc};
use rusqlite::{params, Connection, OptionalExtension};

use crate::error::Result;
use crate::models::PaymentMethod;
use crate::repo::{self, CustomerInput, ProductInput};
use crate::services::{billing, payments};
use crate::util;

struct SeedProduct {
    name: &'static str,
    sku: &'static str,
    description: &'static str,
    hsn: &'static str,
    price: f64,
    gst: f64,
    stock: f64,
}

struct SeedCustomer {
    name: &'static str,
    phone: &'static str,
    email: &'static str,
    city: &'static str,
}

/// Populate a handful of real products, customers, invoices and confirmed
/// payments. Running this twice never duplicates anything.
pub fn seed_demo(conn: &Connection) -> Result<()> {
    let (business, owner) = repo::bootstrap(conn)?;

    let already: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM invoices WHERE business_id=?1 AND transaction_ref LIKE 'SEED-%'",
            params![business.id],
            |row| row.get(0),
        )
        .unwrap_or(0);
    if already > 0 {
        return Ok(());
    }

    let products = [
        SeedProduct { name: "Cadbury Dairy Milk", sku: "GROC-001", description: "Milk chocolate 50g", hsn: "1704", price: 50.0, gst: 18.0, stock: 120.0 },
        SeedProduct { name: "Tata Tea Gold", sku: "GROC-002", description: "Assam tea 500g", hsn: "0902", price: 275.0, gst: 5.0, stock: 60.0 },
        SeedProduct { name: "A4 Notebook", sku: "STAT-001", description: "200-page ruled notebook", hsn: "4820", price: 120.0, gst: 12.0, stock: 85.0 },
        SeedProduct { name: "Ball Pen (Blue)", sku: "STAT-002", description: "0.7mm gel pen", hsn: "9608", price: 20.0, gst: 18.0, stock: 250.0 },
        SeedProduct { name: "Domestic Courier", sku: "SERV-001", description: "Same-day parcel delivery", hsn: "", price: 180.0, gst: 18.0, stock: 0.0 },
        SeedProduct { name: "Amul Butter", sku: "GROC-003", description: "Salted butter 500g", hsn: "0405", price: 285.0, gst: 12.0, stock: 8.0 },
    ];
    let mut product_ids: Vec<String> = Vec::new();
    for item in &products {
        let existing: Option<String> = conn
            .query_row(
                "SELECT id FROM products WHERE business_id=?1 AND sku=?2 LIMIT 1",
                params![business.id, item.sku],
                |row| row.get(0),
            )
            .optional()?;
        let id = match existing {
            Some(id) => id,
            None => {
                let created = repo::insert_product(
                    conn,
                    &business.id,
                    &ProductInput {
                        name: item.name.to_string(),
                        sku: item.sku.to_string(),
                        description: item.description.to_string(),
                        hsn_code: item.hsn.to_string(),
                        barcode: None,
                        price: item.price,
                        gst_rate: item.gst,
                        stock: item.stock,
                        track_inventory: item.sku != "SERV-001",
                        is_service: item.sku == "SERV-001",
                        low_stock_threshold: 10.0,
                    },
                )?;
                created.id
            }
        };
        product_ids.push(id);
    }

    let customers = [
        SeedCustomer { name: "Asha Sharma", phone: "9876500001", email: "asha@example.com", city: "Mumbai" },
        SeedCustomer { name: "Rahul Verma", phone: "9876500002", email: "rahul@example.com", city: "Delhi" },
        SeedCustomer { name: "Meena Iyer", phone: "9876500003", email: "meena@example.com", city: "Bengaluru" },
    ];
    let mut customer_ids: Vec<String> = Vec::new();
    for customer in &customers {
        let existing: Option<String> = conn
            .query_row(
                "SELECT id FROM customers WHERE business_id=?1 AND name=?2 LIMIT 1",
                params![business.id, customer.name],
                |row| row.get(0),
            )
            .optional()?;
        let id = match existing {
            Some(id) => id,
            None => {
                let created = repo::insert_customer(
                    conn,
                    &business.id,
                    &CustomerInput {
                        name: customer.name.to_string(),
                        phone: Some(customer.phone.to_string()),
                        email: Some(customer.email.to_string()),
                        city: Some(customer.city.to_string()),
                        state: Some("Maharashtra".to_string()),
                        ..CustomerInput::default()
                    },
                )?;
                created.id
            }
        };
        customer_ids.push(id);
    }

    let today = Utc::now().date_naive();
    // (days ago, customer index, product index, qty, qty, invoice discount, pay fraction)
    let plan: [(i64, usize, usize, f64, f64, f64, f64); 7] = [
        (1, 0, 0, 3.0, 1.0, 0.0, 1.0),
        (6, 1, 1, 2.0, 2.0, 5.0, 1.0),
        (18, 2, 2, 4.0, 3.0, 0.0, 1.0),
        (34, 0, 3, 5.0, 2.0, 10.0, 1.0),
        (52, 1, 4, 1.0, 1.0, 0.0, 1.0),
        (3, 2, 0, 2.0, 0.0, 0.0, 0.5),
        (0, 0, 5, 1.0, 0.0, 0.0, 0.0),
    ];

    for (index, spec) in plan.iter().enumerate() {
        let (days_ago, cust_idx, prod_idx, qty1, qty2, inv_discount, pay_fraction) = *spec;
        let customer_id = &customer_ids[cust_idx];
        let customer = repo::get_customer(conn, &business.id, customer_id)?.unwrap();
        let first = repo::get_product(conn, &business.id, &product_ids[prod_idx])?.unwrap();
        let second = repo::get_product(conn, &business.id, &product_ids[(prod_idx + 1) % product_ids.len()])?.unwrap();

        let mut lines = vec![billing::CartLine {
            product: first.clone(),
            quantity: qty1,
            discount_percent: 0.0,
        }];
        if qty2 > 0.0 {
            lines.push(billing::CartLine {
                product: second.clone(),
                quantity: qty2,
                discount_percent: 0.0,
            });
        }
        let (totals, calcs) = billing::compute_lines(&lines, inv_discount);
        let taxable = round2_sum(&calcs.iter().map(|c| c.taxable).collect::<Vec<_>>());
        let issue_date = (today - Duration::days(days_ago)).format("%Y-%m-%d").to_string();
        let due_date = (today - Duration::days(days_ago) + Duration::days(15))
            .format("%Y-%m-%d")
            .to_string();
        let invoice_number = repo::next_invoice_number(conn, &business.id)?;
        let transaction_ref = format!("SEED-{:04}", index + 1);
        let invoice_id = util::uuid();
        let now = util::now_iso();
        // Invoices start unpaid; `confirm_inner` derives paid_amount, balance
        // and status from the recorded payment so nothing is double-counted.
        let paid = crate::money::round2(totals.total * pay_fraction);

        conn.execute(
            "INSERT INTO invoices (id, business_id, customer_id, customer_name, invoice_number, \
             transaction_ref, issue_date, due_date, status, subtotal, discount_percent, \
             discount_amount, taxable_amount, tax_amount, total_amount, paid_amount, \
             balance_amount, notes, created_at, updated_at) \
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, \
             ?17, ?18, ?19, ?19)",
            params![
                invoice_id,
                business.id,
                customer_id,
                customer.name,
                invoice_number,
                transaction_ref,
                issue_date,
                due_date,
                "unpaid",
                totals.subtotal,
                inv_discount,
                totals.discount,
                taxable,
                totals.tax,
                totals.total,
                0.0,
                totals.total,
                "Sample invoice",
                now,
            ],
        )?;

        for (sort_order, (line, calc)) in lines.iter().zip(calcs.iter()).enumerate() {
            conn.execute(
                "INSERT INTO invoice_items (id, invoice_id, product_id, description, quantity, \
                 unit_price, discount_percent, discount_amount, taxable_amount, gst_rate, \
                 tax_amount, line_total, sort_order) \
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13)",
                params![
                    util::uuid(),
                    invoice_id,
                    line.product.id,
                    line.product.name,
                    line.quantity,
                    crate::money::round2(line.product.price),
                    line.discount_percent,
                    calc.discount,
                    calc.taxable,
                    line.product.gst_rate,
                    calc.tax,
                    calc.line_total,
                    sort_order as i64,
                ],
            )?;
        }

        if pay_fraction > 0.0 {
            let payment_id = util::uuid();
            conn.execute(
                "INSERT INTO payments (id, business_id, invoice_id, invoice_number, customer_id, \
                 customer_name, amount, method, status, reference, payment_date, notes, created_at) \
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, 'pending', ?9, ?10, ?11, ?12)",
                params![
                    payment_id,
                    business.id,
                    invoice_id,
                    invoice_number,
                    customer_id,
                    customer.name,
                    paid,
                    PaymentMethod::Upi.as_str(),
                    format!("SEEDUTR-{:04}", index + 1),
                    issue_date,
                    "Seeded demo payment",
                    now,
                ],
            )?;
            payments::confirm_inner(
                conn,
                &business.id,
                &payment_id,
                Some(&owner.id),
                &format!("SEEDUTR-{:04}", index + 1),
            )?;
        }
    }

    crate::audit::log(
        conn,
        &business.id,
        Some(&owner.id),
        "system.seed",
        "system",
        None,
        Some("Demo data seeded"),
    )?;
    Ok(())
}

fn round2_sum(values: &[f64]) -> f64 {
    let mut total = 0.0;
    for value in values {
        total = crate::money::round2(total + value);
    }
    total
}
