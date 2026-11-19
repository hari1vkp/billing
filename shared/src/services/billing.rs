//! Cart maths and the atomic point-of-sale checkout.

use rusqlite::{params, Connection};

use crate::audit;
use crate::error::{BillflowError, Result};
use crate::money::round2;
use crate::models::*;
use crate::repo;
use crate::services::payments;
use crate::util::{self, today};

/// One product in a cart.
#[derive(Clone, Debug, PartialEq)]
pub struct CartLine {
    pub product: Product,
    pub quantity: f64,
    pub discount_percent: f64,
}

/// Aggregated cart totals (the invoice-level discount is applied last).
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Totals {
    pub subtotal: f64,
    pub discount: f64,
    pub tax: f64,
    pub total: f64,
    pub units: f64,
}

#[derive(Clone, Debug, PartialEq)]
pub(crate) struct LineCalc {
    pub(crate) base: f64,
    pub(crate) discount: f64,
    pub(crate) taxable: f64,
    pub(crate) tax: f64,
    pub(crate) line_total: f64,
}

/// Mirror of the backend's per-line Decimal calculation, rounded at each step.
pub(crate) fn compute_lines(lines: &[CartLine], invoice_discount_percent: f64) -> (Totals, Vec<LineCalc>) {
    let mut subtotal = 0.0;
    let mut item_discount = 0.0;
    let mut taxable_sum = 0.0;
    let mut tax_sum = 0.0;
    let mut units = 0.0;
    let mut calculated = Vec::with_capacity(lines.len());

    for line in lines {
        let base = round2(line.quantity * line.product.price);
        let discount = round2(base * line.discount_percent / 100.0);
        let taxable = round2(base - discount);
        let tax = round2(taxable * line.product.gst_rate / 100.0);
        let line_total = round2(taxable + tax);
        subtotal = round2(subtotal + base);
        item_discount = round2(item_discount + discount);
        taxable_sum = round2(taxable_sum + taxable);
        tax_sum = round2(tax_sum + tax);
        units += line.quantity;
        calculated.push(LineCalc {
            base,
            discount,
            taxable,
            tax,
            line_total,
        });
    }

    let after_tax = round2(taxable_sum + tax_sum);
    let invoice_discount = round2(after_tax * invoice_discount_percent / 100.0);
    let total = round2(after_tax - invoice_discount);
    let totals = Totals {
        subtotal,
        discount: round2(item_discount + invoice_discount),
        tax: tax_sum,
        total,
        units,
    };
    (totals, calculated)
}

/// Calculate cart totals without persisting anything (used by the QR preview).
pub fn calculate(lines: &[CartLine], invoice_discount_percent: f64) -> Totals {
    compute_lines(lines, invoice_discount_percent).0
}

#[derive(Clone, Debug, PartialEq)]
pub struct CartItemInput {
    pub product_id: String,
    pub quantity: f64,
    pub discount_percent: f64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct CheckoutInput {
    pub customer_id: Option<String>,
    pub items: Vec<CartItemInput>,
    pub discount_percent: f64,
    pub transaction_ref: Option<String>,
    pub method: PaymentMethod,
    pub notes: Option<String>,
    /// `retail` (default) or `wholesale`. Missing/unknown values are retail.
    pub pricing_mode: String,
}

impl Default for CheckoutInput {
    fn default() -> Self {
        Self {
            customer_id: None,
            items: Vec::new(),
            discount_percent: 0.0,
            transaction_ref: None,
            method: PaymentMethod::Upi,
            notes: None,
            pricing_mode: default_pricing_mode(),
        }
    }
}

/// Keep legacy callers (and blank payload fields) on the retail path.
fn default_pricing_mode() -> String {
    "retail".to_string()
}

fn normalize_pricing_mode(mode: &str) -> String {
    if mode.trim().eq_ignore_ascii_case("wholesale") {
        "wholesale".to_string()
    } else {
        "retail".to_string()
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct CheckoutResult {
    pub invoice: Invoice,
    pub payment: Payment,
}

/// Complete a cashier sale. Invoice, items, payment, invoice status, stock
/// movements and audit logs are committed together or rolled back together.
pub fn checkout(
    conn: &Connection,
    business_id: &str,
    user_id: &str,
    input: CheckoutInput,
) -> Result<CheckoutResult> {
    if input.items.is_empty() {
        return Err(BillflowError::Validation("Cart is empty".into()));
    }
    let business = repo::get_business(conn, business_id)?;

    // Resolve the customer before opening the write transaction: a supplied id
    // must belong to this business.
    let customer = match input.customer_id.as_deref() {
        Some(id) if !id.trim().is_empty() => repo::get_customer(conn, business_id, id)?
            .ok_or_else(|| BillflowError::Validation(format!("Customer {} not found", id)))?,
        _ => repo::resolve_or_create_walk_in(conn, business_id)?,
    };

    let pricing_mode = normalize_pricing_mode(&input.pricing_mode);
    let mut lines = Vec::with_capacity(input.items.len());
    let mut wholesale_discounts = Vec::with_capacity(input.items.len());
    for item in &input.items {
        if !item.quantity.is_finite() || item.quantity <= 0.0 {
            return Err(BillflowError::Validation(
                "Item quantity must be greater than zero".into(),
            ));
        }
        let mut product = repo::get_product(conn, business_id, &item.product_id)?.ok_or_else(|| {
            BillflowError::Validation(format!("Product {} not found", item.product_id))
        })?;
        if item.discount_percent < 0.0 || item.discount_percent > 100.0 {
            return Err(BillflowError::Validation(
                "Item discount must be between 0 and 100".into(),
            ));
        }

        // Product-backed lines take their authoritative unit price from the
        // selected mode. Wholesale is derived from the product's discount;
        // retail (and any unknown mode) keeps the stored retail price.
        let applied_wholesale = if pricing_mode == "wholesale" {
            product.wholesale_discount_percent.clamp(0.0, 100.0)
        } else {
            0.0
        };
        if applied_wholesale > 0.0 {
            product.price = round2(product.price * (1.0 - applied_wholesale / 100.0));
        }
        wholesale_discounts.push(applied_wholesale);
        lines.push(CartLine {
            product,
            quantity: item.quantity,
            discount_percent: item.discount_percent,
        });
    }
    if !(0.0..=100.0).contains(&input.discount_percent) {
        return Err(BillflowError::Validation(
            "Invoice discount must be between 0 and 100".into(),
        ));
    }

    let (totals, line_calcs) = compute_lines(&lines, input.discount_percent);
    let issue_date = today();
    let due_date = {
        let d = chrono::NaiveDate::parse_from_str(&issue_date, "%Y-%m-%d")
            .unwrap_or_else(|_| chrono::Utc::now().date_naive())
            + chrono::Duration::days(15);
        Some(d.format("%Y-%m-%d").to_string())
    };
    let transaction_ref = input
        .transaction_ref
        .filter(|s| !s.trim().is_empty())
        .unwrap_or_else(|| format!("POS-{}", uuid::Uuid::new_v4().simple().to_string()[..10].to_uppercase()));

    let tx = conn.unchecked_transaction()?;
    let invoice_id = util::uuid();
    let number = repo::next_invoice_number(&tx, business_id)?;
    let now = util::now_iso();
    tx.execute(
        "INSERT INTO invoices (id, business_id, customer_id, customer_name, invoice_number, \
         transaction_ref, issue_date, due_date, status, subtotal, discount_percent, \
         discount_amount, taxable_amount, tax_amount, total_amount, paid_amount, balance_amount, \
         notes, created_at, updated_at, pricing_mode) \
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, 'unpaid', ?9, ?10, ?11, ?12, ?13, ?14, 0, ?15, \
         ?16, ?17, ?17, ?18)",
        params![
            invoice_id,
            business_id,
            customer.id,
            customer.name,
            number,
            transaction_ref,
            issue_date,
            due_date,
            totals.subtotal,
            input.discount_percent,
            totals.discount,
            round2(totals.subtotal - {
                let mut d = 0.0;
                for c in &line_calcs {
                    d = round2(d + c.discount);
                }
                d
            }),
            totals.tax,
            totals.total,
            totals.total,
            input.notes,
            now,
            pricing_mode,
        ],
    )?;

    for (index, (line, calc)) in lines.iter().zip(line_calcs.iter()).enumerate() {
        tx.execute(
            "INSERT INTO invoice_items (id, invoice_id, product_id, description, quantity, \
             unit_price, discount_percent, discount_amount, taxable_amount, gst_rate, \
             tax_amount, line_total, sort_order, wholesale_discount_percent) \
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14)",
            params![
                util::uuid(),
                invoice_id,
                line.product.id,
                line.product.name,
                line.quantity,
                round2(line.product.price),
                line.discount_percent,
                calc.discount,
                calc.taxable,
                line.product.gst_rate,
                calc.tax,
                calc.line_total,
                index as i64,
                wholesale_discounts[index],
            ],
        )?;
    }

    audit::log(
        &tx,
        business_id,
        Some(user_id),
        "invoice.create",
        "invoice",
        Some(&number),
        Some(&format!("total={:.2}", totals.total)),
    )?;

    // Insert the pending payment, then confirm through the shared payment path
    // so stock is decremented exactly once with a "sale" movement.
    let payment_id = util::uuid();
    tx.execute(
        "INSERT INTO payments (id, business_id, invoice_id, invoice_number, customer_id, \
         customer_name, amount, method, status, reference, payment_date, notes, created_at) \
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, 'pending', ?9, ?10, ?11, ?12)",
        params![
            payment_id,
            business_id,
            invoice_id,
            number,
            customer.id,
            customer.name,
            totals.total,
            input.method.as_str(),
            transaction_ref,
            issue_date,
            "Manually confirmed by cashier at POS (no independent bank verification)",
            now,
        ],
    )?;
    let payment = payments::confirm_inner(&tx, business_id, &payment_id, Some(user_id), &transaction_ref)?;

    audit::log(
        &tx,
        business_id,
        Some(user_id),
        "pos.checkout",
        "billing",
        Some(&number),
        Some(&format!("method={} total={:.2}", input.method.as_str(), totals.total)),
    )?;

    // Sanity-check business reference still exists (keeps `business` used and
    // guarantees the tenant was resolved before we started writing).
    debug_assert_eq!(business.id, business_id);
    tx.commit()?;

    let detail = repo::get_invoice(conn, business_id, &invoice_id)?;
    Ok(CheckoutResult {
        invoice: detail.invoice,
        payment,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn product(name: &str, price: f64, gst: f64) -> Product {
        Product {
            id: name.into(),
            business_id: "b".into(),
            name: name.into(),
            sku: String::new(),
            description: String::new(),
            hsn_code: String::new(),
            barcode: None,
            price,
            gst_rate: gst,
            stock: 100.0,
            track_inventory: true,
            is_service: false,
            low_stock_threshold: 10.0,
            discount_type: "none".into(),
            discount_value: 0.0,
            wholesale_discount_percent: 0.0,
            is_active: true,
            created_at: String::new(),
            updated_at: String::new(),
        }
    }

    #[test]
    fn cart_calculation_matches_backend_formula() {
        let lines = vec![
            CartLine {
                product: product("Tea", 100.0, 18.0),
                quantity: 2.0,
                discount_percent: 10.0,
            },
            CartLine {
                product: product("Book", 250.0, 5.0),
                quantity: 1.0,
                discount_percent: 0.0,
            },
        ];
        let totals = calculate(&lines, 5.0);
        // Line 1: base 200, disc 20, taxable 180, tax 32.40, total 212.40
        // Line 2: base 250, disc 0, taxable 250, tax 12.50, total 262.50
        // after tax = 474.90, invoice disc = 23.745 -> 23.75, total = 451.15
        assert_eq!(totals.subtotal, 450.0);
        assert_eq!(totals.tax, 44.9);
        assert_eq!(totals.discount, 43.75);
        assert_eq!(totals.total, 451.15);
        assert_eq!(totals.units, 3.0);
    }

    fn priced_product(conn: &Connection, business_id: &str, discount: f64) -> Product {
        let product = repo::insert_product(
            conn,
            business_id,
            &repo::ProductInput {
                name: "Priced Item".into(),
                sku: "PRICED-1".into(),
                description: String::new(),
                hsn_code: String::new(),
                barcode: None,
                price: 200.0,
                gst_rate: 0.0,
                stock: 10.0,
                track_inventory: true,
                is_service: false,
                low_stock_threshold: 1.0,
            },
        )
        .unwrap();
        conn.execute(
            "UPDATE products SET wholesale_discount_percent = ?1 WHERE id = ?2",
            params![discount, &product.id],
        )
        .unwrap();
        product
    }

    #[test]
    fn checkout_defaults_to_retail_and_keeps_retail_price() {
        let db = crate::db::Database::in_memory().unwrap();
        let conn = db.conn();
        let (business, user) = repo::bootstrap(&conn).unwrap();
        let product = priced_product(&conn, &business.id, 10.0);

        let result = checkout(
            &conn,
            &business.id,
            &user.id,
            CheckoutInput {
                items: vec![CartItemInput {
                    product_id: product.id,
                    quantity: 2.0,
                    discount_percent: 0.0,
                }],
                ..CheckoutInput::default()
            },
        )
        .unwrap();

        assert_eq!(result.invoice.pricing_mode, "retail");
        assert_eq!(result.invoice.total_amount, 400.0);
        let detail = repo::get_invoice(&conn, &business.id, &result.invoice.id).unwrap();
        assert_eq!(detail.items[0].unit_price, 200.0);
        assert_eq!(detail.items[0].wholesale_discount_percent, 0.0);
    }

    #[test]
    fn wholesale_checkout_derives_price_and_records_mode_and_discount() {
        let db = crate::db::Database::in_memory().unwrap();
        let conn = db.conn();
        let (business, user) = repo::bootstrap(&conn).unwrap();
        let product = priced_product(&conn, &business.id, 10.0);

        let result = checkout(
            &conn,
            &business.id,
            &user.id,
            CheckoutInput {
                items: vec![CartItemInput {
                    product_id: product.id,
                    quantity: 2.0,
                    discount_percent: 0.0,
                }],
                pricing_mode: "wholesale".into(),
                ..CheckoutInput::default()
            },
        )
        .unwrap();

        assert_eq!(result.invoice.pricing_mode, "wholesale");
        // 200 * (1 - 10/100) = 180 per unit, 2 units = 360, GST 0.
        assert_eq!(result.invoice.total_amount, 360.0);
        let detail = repo::get_invoice(&conn, &business.id, &result.invoice.id).unwrap();
        assert_eq!(detail.items[0].unit_price, 180.0);
        assert_eq!(detail.items[0].wholesale_discount_percent, 10.0);
        // Stock movement is still driven by quantity, not the discounted price.
        let after = repo::get_product(&conn, &business.id, &detail.items[0].product_id.clone().unwrap()).unwrap();
        assert_eq!(after.unwrap().stock, 8.0);
    }
}
