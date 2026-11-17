//! Manual inventory adjustments with role-based restrictions.

use rusqlite::{params, Connection};

use crate::audit;
use crate::error::{BillflowError, Result};
use crate::models::StockMovement;
use crate::repo;
use crate::util;

const STAFF_ALLOWED_REASONS: [&str; 4] = ["found", "damaged", "return", "correction"];
const STAFF_MAX_ABS_CHANGE: f64 = 20.0;

/// Apply a stock delta and write the matching movement + audit entries.
pub fn adjust_stock(
    conn: &Connection,
    business_id: &str,
    user_id: &str,
    product_id: &str,
    delta: f64,
    reason: &str,
    notes: Option<&str>,
    is_owner: bool,
) -> Result<StockMovement> {
    if !delta.is_finite() || delta == 0.0 {
        return Err(BillflowError::Validation(
            "quantity_change must be a non-zero number".into(),
        ));
    }
    let reason = reason.trim().to_ascii_lowercase();
    if reason.is_empty() {
        return Err(BillflowError::Validation("reason is required".into()));
    }
    if !is_owner {
        if !STAFF_ALLOWED_REASONS.contains(&reason.as_str()) {
            return Err(BillflowError::Validation(format!(
                "Staff may only adjust stock for: {}",
                STAFF_ALLOWED_REASONS.join(", ")
            )));
        }
        if delta.abs() > STAFF_MAX_ABS_CHANGE {
            return Err(BillflowError::Validation(
                "Staff may only adjust up to 20 units at a time".into(),
            ));
        }
    }

    let product = repo::get_product(conn, business_id, product_id)?
        .ok_or_else(|| BillflowError::NotFound("Product not found".into()))?;
    let before = product.stock;
    let after = before + delta;
    if after < 0.0 {
        return Err(BillflowError::Validation("Stock cannot go below zero".into()));
    }

    let tx = conn.unchecked_transaction()?;
    let now = util::now_iso();
    tx.execute(
        "UPDATE products SET stock = ?1, updated_at = ?2 WHERE id = ?3 AND business_id = ?4",
        params![after, now, product_id, business_id],
    )?;

    let id = util::uuid();
    let actor = audit::actor_name(&tx, Some(user_id));
    tx.execute(
        "INSERT INTO stock_movements (id, business_id, product_id, product_name, sku, barcode, \
         quantity_change, quantity_before, quantity_after, reason, reference, \
         performed_by_name, notes, created_at) \
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14)",
        params![
            id,
            business_id,
            product_id,
            product.name,
            product.sku,
            product.barcode,
            delta,
            before,
            after,
            reason,
            product.sku,
            actor,
            notes,
            now,
        ],
    )?;
    audit::log(
        &tx,
        business_id,
        Some(user_id),
        "stock.adjust",
        "stock",
        None,
        Some(&format!(
            "{}: {} -> {} ({})",
            product.name, before, after, reason
        )),
    )?;
    tx.commit()?;

    Ok(StockMovement {
        id,
        business_id: business_id.to_string(),
        product_id: product_id.to_string(),
        product_name: product.name,
        sku: if product.sku.is_empty() { None } else { Some(product.sku) },
        barcode: product.barcode,
        quantity_change: delta,
        quantity_before: before,
        quantity_after: after,
        reason,
        reference: None,
        performed_by_name: actor,
        notes: notes.map(str::to_string),
        created_at: now,
    })
}
