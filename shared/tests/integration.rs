use billflow_shared::auth::{authenticate, is_owner};
use billflow_shared::db::Database;
use billflow_shared::models::PaymentMethod;
use billflow_shared::repo::{self, ProductInput};
use billflow_shared::services::{analytics, billing, reports, seed};
use billflow_shared::Result;

fn setup() -> Result<Database> {
    let db = Database::in_memory()?;
    let (business, owner) = repo::bootstrap(&db.conn())?;
    assert_eq!(business.name, "BillFlow Demo");
    assert!(is_owner(&owner));
    let user = authenticate(&db.conn(), "demo@billingapp.com", "Demo@1234")?;
    assert_eq!(user.id, owner.id);
    Ok(db)
}

#[test]
fn checkout_is_atomic_and_moves_stock_once() -> Result<()> {
    let db = setup()?;
    let conn = db.conn();
    let business = repo::bootstrap(&conn)?.0;
    let user = authenticate(&conn, "demo@billingapp.com", "Demo@1234")?;
    let product = repo::insert_product(
        &conn,
        &business.id,
        &ProductInput {
            name: "Test Product".into(),
            sku: "TEST-1".into(),
            description: String::new(),
            hsn_code: String::new(),
            barcode: Some("TESTBARCODE".into()),
            price: 100.0,
            gst_rate: 18.0,
            stock: 10.0,
            track_inventory: true,
            is_service: false,
            low_stock_threshold: 2.0,
        },
    )?;

    let result = billing::checkout(
        &conn,
        &business.id,
        &user.id,
        billing::CheckoutInput {
            customer_id: None,
            items: vec![billing::CartItemInput {
                product_id: product.id.clone(),
                quantity: 2.0,
                discount_percent: 0.0,
            }],
            discount_percent: 0.0,
            transaction_ref: Some("TXN-1".into()),
            method: PaymentMethod::Cash,
            notes: None,
        },
    )?;

    assert_eq!(result.invoice.status, billflow_shared::models::InvoiceStatus::Paid);
    assert_eq!(result.invoice.total_amount, 236.0);
    assert_eq!(result.invoice.paid_amount, 236.0);
    assert_eq!(result.invoice.balance_amount, 0.0);
    assert_eq!(result.payment.status, "confirmed");
    assert_eq!(result.payment.method, PaymentMethod::Cash);
    assert_eq!(result.payment.reference.as_deref(), Some("TXN-1"));

    let after = repo::get_product(&conn, &business.id, &product.id)?.unwrap();
    assert_eq!(after.stock, 8.0);

    let (movements, movement_count) = repo::list_movements(&conn, &business.id, Some(&product.id), 20, 0)?;
    assert_eq!(movement_count, 1);
    assert_eq!(movements[0].reason, "sale");
    assert_eq!(movements[0].quantity_change, -2.0);
    assert_eq!(movements[0].reference, Some(result.invoice.invoice_number.clone()));

    let (actions, _) = repo::list_activity(&conn, &business.id, "", "", 50, 0)?;
    let names: Vec<&str> = actions.iter().map(|a| a.action.as_str()).collect();
    assert!(names.contains(&"invoice.create"));
    assert!(names.contains(&"payment.confirm"));
    assert!(names.contains(&"pos.checkout"));

    // Confirming again is idempotent and must not decrement stock twice.
    let _ = billflow_shared::services::payments::confirm_payment(
        &conn,
        &business.id,
        &result.payment.id,
        &user.id,
        "TXN-1",
    )?;
    let after_again = repo::get_product(&conn, &business.id, &product.id)?.unwrap();
    assert_eq!(after_again.stock, 8.0);
    Ok(())
}

#[test]
fn seed_is_idempotent_and_analytics_are_real() -> Result<()> {
    let db = setup()?;
    let conn = db.conn();
    seed::seed_demo(&conn)?;
    let (business, _) = repo::bootstrap(&conn)?;
    let (invoices, n1) = repo::list_invoices(&conn, &business.id, "", "", 100, 0)?;
    let (_, c1) = repo::list_customers(&conn, &business.id, "", 100, 0)?;
    let (_, p1) = repo::list_products(&conn, &business.id, "", false, 100, 0)?;
    assert!(n1 >= 7 && c1 >= 3 && p1 >= 6);

    let report = analytics::load(&conn, &business.id, None, None)?;
    assert!(report.year_sales > 0.0);
    assert!(report.outstanding > 0.0);
    assert!(report.pending_invoices >= 2);
    assert!(!report.methods.is_empty());
    assert!(!report.top_products.is_empty());
    assert!(!report.top_customers.is_empty());
    assert!(!report.recent_invoices.is_empty());
    assert_eq!(report.sales_trend.len(), 12);
    assert!(report.recent_payments.iter().any(|p| p.status == "confirmed"));

    let csv = reports::sales_csv(&conn, &business.id, None, None)?;
    assert!(csv.starts_with("Invoice Number,Date,Customer,Status"));
    assert!(csv.lines().count() > 1);

    let pdf = reports::invoice_pdf_for(&conn, &business.id, &invoices[0].id)?;
    assert_eq!(&pdf[..5], b"%PDF-");

    seed::seed_demo(&conn)?;
    let (_, n2) = repo::list_invoices(&conn, &business.id, "", "", 100, 0)?;
    assert_eq!(n1, n2);
    Ok(())
}

#[test]
fn backup_and_restore_round_trip() -> Result<()> {
    let db = setup()?;
    let business_id = {
        let conn = db.conn();
        seed::seed_demo(&conn)?;
        repo::bootstrap(&conn)?.0.id
    };

    let dir = std::path::Path::new("/tmp/opencode");
    std::fs::create_dir_all(dir)?;
    let target = dir.join("billflow-shared-test-backup.sqlite3");
    let _ = std::fs::remove_file(&target);
    // Important: release the connection guard before calling Database methods
    // that lock it again, otherwise the same thread deadlocks on the mutex.
    db.backup(&target)?;
    assert!(target.exists());

    let before = {
        let conn = db.conn();
        repo::list_products(&conn, &business_id, "", false, 100, 0)?.1
    };
    db.restore(&target)?;
    let after = {
        let conn = db.conn();
        repo::list_products(&conn, &business_id, "", false, 100, 0)?.1
    };
    assert_eq!(before, after);
    let _ = std::fs::remove_file(&target);
    Ok(())
}
