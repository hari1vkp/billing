//! CSV product onboarding for the local (SQLite / Tauri) mode.
//!
//! The whole batch is committed in one transaction. Rows are validated before
//! any write; invalid rows are reported and skipped, while a database failure
//! rolls back everything. Stock history is always written to `stock_movements`
//! so imports are indistinguishable from other real inventory changes.

use std::collections::HashMap;

use rusqlite::{params, Connection};

use crate::audit;
use crate::error::{BillflowError, Result};
use crate::models::Product;
use crate::repo::{self, ProductInput};
use crate::util;

pub use crate::models::{ImportRow, ImportSummary};

/// CSV template also served by the optional `import_template_csv` command.
pub const IMPORT_TEMPLATE: &str =
    "name,barcode,cost_price,selling_price,quantity,category,gst_rate\n\
     # Example: A4 Notebook,8901234567890,80,120,25,Stationery,12\n";

/// Canonicalise a header cell: case, spaces, hyphens, underscores and symbols
/// are ignored so `GST %`, `bar-code` and `Bar Code` all resolve correctly.
fn normalize_header(raw: &str) -> String {
    raw.chars()
        .filter(|c| c.is_ascii_alphanumeric())
        .flat_map(|c| c.to_lowercase())
        .collect()
}

fn canonical_header(raw: &str) -> Option<&'static str> {
    match normalize_header(raw).as_str() {
        "name" | "product" | "productname" | "item" | "itemname" | "description" => Some("name"),
        "barcode" | "ean" | "upc" | "isbn" => Some("barcode"),
        "cost" | "costprice" | "purchaseprice" | "buyingprice" | "mrpcost" => Some("cost_price"),
        "price" | "sellingprice" | "saleprice" | "retailprice" | "rate" | "mrp" => {
            Some("selling_price")
        }
        "quantity" | "qty" | "stock" | "openingstock" | "openingqty" | "closingstock" => {
            Some("quantity")
        }
        "category" | "group" | "productgroup" | "brand" => Some("category"),
        "gst" | "tax" | "taxrate" => Some("gst_rate"),
        _ => None,
    }
}

/// Minimal RFC-4180 reader: quoted fields, escaped quotes and BOM are handled
/// without pulling in another dependency. Each record carries its physical
/// (1-based) line number, which is used for error reporting.
fn read_records(text: &str) -> Vec<(usize, Vec<String>)> {
    let text = text.strip_prefix('\u{feff}').unwrap_or(text);
    let mut records = Vec::new();
    let mut record: Vec<String> = Vec::new();
    let mut field = String::new();
    let mut in_quotes = false;
    let mut line = 1usize;
    let mut chars = text.chars().peekable();

    while let Some(c) = chars.next() {
        if in_quotes {
            if c == '"' {
                if chars.peek() == Some(&'"') {
                    chars.next();
                    field.push('"');
                } else {
                    in_quotes = false;
                }
            } else {
                if c == '\n' {
                    line += 1;
                }
                field.push(c);
            }
            continue;
        }
        match c {
            '"' => in_quotes = true,
            ',' => record.push(std::mem::take(&mut field)),
            '\n' => {
                record.push(std::mem::take(&mut field));
                if let Some(last) = record.last_mut() {
                    if last.ends_with('\r') {
                        last.pop();
                    }
                }
                if record.iter().any(|f| !f.trim().is_empty()) {
                    records.push((line, std::mem::take(&mut record)));
                } else {
                    record.clear();
                }
                line += 1;
            }
            _ => field.push(c),
        }
    }
    if !field.is_empty() || !record.is_empty() {
        record.push(field);
        if let Some(last) = record.last_mut() {
            if last.ends_with('\r') {
                last.pop();
            }
        }
        if record.iter().any(|f| !f.trim().is_empty()) {
            records.push((line, record));
        }
    }
    records
}

fn parse_number(value: &str, field: &str) -> std::result::Result<f64, String> {
    let value = value.trim();
    let number = value
        .parse::<f64>()
        .map_err(|_| format!("{field} must be a number"))?;
    if !number.is_finite() {
        return Err(format!("{field} must be a finite number"));
    }
    Ok(number)
}

fn valid_gst(rate: f64) -> bool {
    rate.is_finite() && (0.0..=100.0).contains(&rate)
}

/// Parse CSV text into validated rows plus `(row, message)` errors.
///
/// Header aliases are documented in `IMPORT_CONTRACT.md`; a BOM and `#`
/// comment rows are accepted. Missing values are never invented: only quantity
/// (0) and GST (the supplied default) have defined fallbacks.
pub fn parse_csv(
    text: &str,
    default_gst_rate: f64,
) -> Result<(Vec<ImportRow>, Vec<(usize, String)>)> {
    if !valid_gst(default_gst_rate) {
        return Err(BillflowError::Validation(
            "default_gst_rate must be between 0 and 100".into(),
        ));
    }

    let records = read_records(text);
    let Some((_, header)) = records.first() else {
        return Ok((Vec::new(), Vec::new()));
    };
    let mut columns: HashMap<&'static str, usize> = HashMap::new();
    for (index, cell) in header.iter().enumerate() {
        if let Some(canonical) = canonical_header(cell) {
            columns.entry(canonical).or_insert(index);
        }
    }
    for required in ["name", "selling_price"] {
        if !columns.contains_key(required) {
            return Err(BillflowError::Validation(format!(
                "CSV is missing the required column: {required}"
            )));
        }
    }

    let mut rows = Vec::new();
    let mut errors: Vec<(usize, String)> = Vec::new();
    let mut seen_barcodes: HashMap<String, usize> = HashMap::new();

    for (line, fields) in records.iter().skip(1) {
        let value = |key: &str| -> &str {
            columns
                .get(key)
                .and_then(|&i| fields.get(i))
                .map(|s| s.trim())
                .unwrap_or("")
        };

        let name = value("name").to_string();
        if name.is_empty() {
            errors.push((*line, "name is required".into()));
            continue;
        }
        if name.starts_with('#') {
            continue;
        }

        let barcode = {
            let raw = value("barcode");
            if raw.is_empty() {
                None
            } else {
                Some(raw.to_string())
            }
        };
        if let Some(code) = &barcode {
            if seen_barcodes.contains_key(code) {
                errors.push((*line, format!("duplicate barcode '{code}' in file")));
                continue;
            }
            seen_barcodes.insert(code.clone(), *line);
        }

        let raw_selling = value("selling_price");
        if raw_selling.is_empty() {
            errors.push((*line, "selling_price is required".into()));
            continue;
        }
        let selling_price = match parse_number(raw_selling, "selling_price") {
            Ok(n) => n,
            Err(message) => {
                errors.push((*line, message));
                continue;
            }
        };
        if selling_price < 0.0 {
            errors.push((*line, "selling_price must be >= 0".into()));
            continue;
        }

        let quantity = if value("quantity").is_empty() {
            0.0
        } else {
            match parse_number(value("quantity"), "quantity") {
                Ok(n) => n,
                Err(message) => {
                    errors.push((*line, message));
                    continue;
                }
            }
        };
        if quantity < 0.0 {
            errors.push((*line, "quantity must be >= 0".into()));
            continue;
        }

        let cost_price = if value("cost_price").is_empty() {
            None
        } else {
            match parse_number(value("cost_price"), "cost_price") {
                Ok(n) => Some(n),
                Err(message) => {
                    errors.push((*line, message));
                    continue;
                }
            }
        };

        let gst_rate = if value("gst_rate").is_empty() {
            Some(default_gst_rate)
        } else {
            let raw = value("gst_rate").trim_end_matches('%').trim();
            match parse_number(raw, "gst_rate") {
                Ok(n) => Some(n),
                Err(message) => {
                    errors.push((*line, message));
                    continue;
                }
            }
        };
        if let Some(rate) = gst_rate {
            if !valid_gst(rate) {
                errors.push((*line, "gst_rate must be between 0 and 100".into()));
                continue;
            }
        }

        let category = {
            let raw = value("category");
            if raw.is_empty() {
                None
            } else {
                Some(raw.to_string())
            }
        };

        rows.push(ImportRow {
            name,
            barcode,
            cost_price,
            selling_price,
            quantity,
            category,
            gst_rate,
        });
    }

    Ok((rows, errors))
}

/// Insert a real stock movement with the same columns as the manual adjustment
/// and payment paths. `reference` mirrors `inventory::adjust_stock` (the SKU).
fn record_movement(
    conn: &Connection,
    business_id: &str,
    user_id: Option<&str>,
    product: &Product,
    change: f64,
    before: f64,
    after: f64,
    reason: &str,
    notes: Option<&str>,
) -> Result<()> {
    let now = util::now_iso();
    let actor = audit::actor_name(conn, user_id);
    conn.execute(
        "INSERT INTO stock_movements (id, business_id, product_id, product_name, sku, barcode, \
         quantity_change, quantity_before, quantity_after, reason, reference, \
         performed_by_name, notes, created_at) \
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14)",
        params![
            util::uuid(),
            business_id,
            product.id,
            product.name,
            product.sku,
            product.barcode,
            change,
            before,
            after,
            reason,
            product.sku,
            actor,
            notes,
            now,
        ],
    )?;
    Ok(())
}

/// Import staged rows atomically. Barcode matches win; without a barcode an
/// exact name match is only used when it is unambiguous. Existing prices are
/// never changed, and stock is only replaced when `overwrite_stock` is true.
pub fn import_rows(
    conn: &Connection,
    business_id: &str,
    user_id: Option<&str>,
    rows: &[ImportRow],
    overwrite_stock: bool,
    default_gst_rate: f64,
) -> Result<ImportSummary> {
    if !valid_gst(default_gst_rate) {
        return Err(BillflowError::Validation(
            "default_gst_rate must be between 0 and 100".into(),
        ));
    }

    let mut summary = ImportSummary::default();
    let tx = conn.unchecked_transaction()?;
    let business = repo::get_business(&tx, business_id)?;

    for (index, row) in rows.iter().enumerate() {
        let row_no = index + 1;
        let name = row.name.trim();
        if name.is_empty() {
            summary.skipped += 1;
            summary.errors.push((row_no, "name is required".into()));
            continue;
        }
        if !row.selling_price.is_finite() || row.selling_price < 0.0 {
            summary.skipped += 1;
            summary.errors.push((row_no, "selling_price must be >= 0".into()));
            continue;
        }
        if !row.quantity.is_finite() || row.quantity < 0.0 {
            summary.skipped += 1;
            summary.errors.push((row_no, "quantity must be >= 0".into()));
            continue;
        }
        let gst = row.gst_rate.unwrap_or(default_gst_rate);
        if !valid_gst(gst) {
            summary.skipped += 1;
            summary
                .errors
                .push((row_no, "gst_rate must be between 0 and 100".into()));
            continue;
        }
        let barcode = row
            .barcode
            .as_deref()
            .map(str::trim)
            .filter(|code| !code.is_empty());
        let category = row
            .category
            .as_deref()
            .map(str::trim)
            .filter(|value| !value.is_empty());

        let existing = match barcode {
            Some(code) => repo::get_product_by_barcode(&tx, business_id, code)?,
            None => {
                let ids: Vec<String> = {
                    let mut stmt = tx.prepare(
                        "SELECT id FROM products WHERE business_id = ?1 AND name = ?2 \
                         AND is_active = 1 ORDER BY created_at ASC",
                    )?;
                    let found = stmt.query_map(params![business_id, name], |r| r.get::<_, String>(0))?;
                    let mut ids = Vec::new();
                    for id in found {
                        ids.push(id?);
                    }
                    ids
                };
                if ids.len() > 1 {
                    summary.skipped += 1;
                    summary.errors.push((
                        row_no,
                        format!("'{name}' matches more than one product; supply a barcode"),
                    ));
                    continue;
                }
                match ids.first() {
                    Some(id) => repo::get_product(&tx, business_id, id)?,
                    None => None,
                }
            }
        };

        if let Some(product) = existing {
            if overwrite_stock {
                let before = product.stock;
                let after = row.quantity;
                tx.execute(
                    "UPDATE products SET stock = ?1, updated_at = ?2 \
                     WHERE id = ?3 AND business_id = ?4",
                    params![after, util::now_iso(), product.id, business_id],
                )?;
                record_movement(
                    &tx,
                    business_id,
                    user_id,
                    &product,
                    after - before,
                    before,
                    after,
                    "correction",
                    Some(&format!("CSV import row {row_no}")),
                )?;
                audit::log(
                    &tx,
                    business_id,
                    user_id,
                    "product.update",
                    "product",
                    Some(&product.id),
                    Some(&format!("CSV import: stock {before} -> {after}")),
                )?;
                summary.updated += 1;
                summary.stock_movements += 1;
                summary.activity_entries += 1;
            } else {
                // Never silently change an existing product.
                summary.skipped += 1;
            }
            continue;
        }

        let created = repo::insert_product(
            &tx,
            business_id,
            &ProductInput {
                name: name.to_string(),
                sku: barcode.unwrap_or("").to_string(),
                description: category.unwrap_or("").to_string(),
                hsn_code: String::new(),
                barcode: barcode.map(str::to_string),
                price: row.selling_price,
                gst_rate: gst,
                stock: row.quantity,
                track_inventory: true,
                is_service: false,
                low_stock_threshold: business.low_stock_threshold,
            },
        )?;
        record_movement(
            &tx,
            business_id,
            user_id,
            &created,
            row.quantity,
            0.0,
            row.quantity,
            "opening_stock",
            Some(&format!("CSV import row {row_no}")),
        )?;
        audit::log(
            &tx,
            business_id,
            user_id,
            "product.create",
            "product",
            Some(&created.id),
            Some(&format!("CSV import: {} (stock {})", created.name, row.quantity)),
        )?;
        summary.created += 1;
        summary.stock_movements += 1;
        summary.activity_entries += 1;
    }

    audit::log(
        &tx,
        business_id,
        user_id,
        "product.import",
        "product",
        None,
        Some(&format!(
            "created={} updated={} skipped={} errors={}",
            summary.created,
            summary.updated,
            summary.skipped,
            summary.errors.len()
        )),
    )?;
    summary.activity_entries += 1;
    tx.commit()?;
    Ok(summary)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::db::Database;

    fn row(name: &str, barcode: Option<&str>, price: f64, quantity: f64) -> ImportRow {
        ImportRow {
            name: name.into(),
            barcode: barcode.map(str::to_string),
            cost_price: None,
            selling_price: price,
            quantity,
            category: None,
            gst_rate: None,
        }
    }

    #[test]
    fn csv_aliases_bom_comments_and_validation() {
        let text = "\u{feff}Product Name,Bar Code,Purchase Price,Retail Price,Opening Qty,Brand,GST %\n\
                    # example,BC0,10,20,5,Other,18\n\
                    Widget,BC1,10.5,25.5,4,Tools,12\n\
                    Broken,,10,-1,3,Tools,18\n\
                    Widget,BC1,10,30,1,Tools,18\n";
        let (rows, errors) = parse_csv(text, 18.0).expect("parse");
        assert_eq!(rows.len(), 1);
        let row = &rows[0];
        assert_eq!(row.name, "Widget");
        assert_eq!(row.barcode.as_deref(), Some("BC1"));
        assert_eq!(row.cost_price, Some(10.5));
        assert_eq!(row.selling_price, 25.5);
        assert_eq!(row.quantity, 4.0);
        assert_eq!(row.category.as_deref(), Some("Tools"));
        assert_eq!(row.gst_rate, Some(12.0));
        assert_eq!(errors.len(), 2);
        assert_eq!(errors[0].0, 4);
        assert!(errors[0].1.contains("selling_price"));
        assert_eq!(errors[1].0, 5);
        assert!(errors[1].1.contains("duplicate barcode"));
    }

    #[test]
    fn import_rows_is_atomic_and_records_real_history() {
        let db = Database::in_memory().expect("in-memory database");
        let conn = db.conn();
        let (business, owner) = repo::bootstrap(&conn).expect("bootstrap");

        let summary = import_rows(
            &conn,
            &business.id,
            Some(&owner.id),
            &[row("Tea", Some("T1"), 100.0, 10.0)],
            false,
            18.0,
        )
        .expect("first import");
        assert_eq!(summary.created, 1);
        assert_eq!(summary.stock_movements, 1);
        assert_eq!(summary.activity_entries, 2);

        let summary = import_rows(
            &conn,
            &business.id,
            Some(&owner.id),
            &[row("Tea", Some("T1"), 999.0, 25.0)],
            false,
            18.0,
        )
        .expect("second import without overwrite");
        assert_eq!(summary.created, 0);
        assert_eq!(summary.updated, 0);
        assert_eq!(summary.skipped, 1);

        let product = repo::get_product_by_barcode(&conn, &business.id, "T1")
            .expect("lookup")
            .expect("product");
        assert_eq!(product.stock, 10.0, "stock must not be silently overwritten");
        assert_eq!(product.price, 100.0, "price must never be overwritten");

        let summary = import_rows(
            &conn,
            &business.id,
            Some(&owner.id),
            &[row("Tea", Some("T1"), 999.0, 25.0)],
            true,
            18.0,
        )
        .expect("overwrite import");
        assert_eq!(summary.updated, 1);
        assert_eq!(summary.stock_movements, 1);
        let product = repo::get_product_by_barcode(&conn, &business.id, "T1")
            .expect("lookup")
            .expect("product");
        assert_eq!(product.stock, 25.0);
        assert_eq!(product.price, 100.0);

        let reasons: Vec<String> = {
            let mut stmt = conn
                .prepare("SELECT reason FROM stock_movements ORDER BY created_at ASC, id ASC")
                .expect("prepare");
            let found = stmt
                .query_map([], |r| r.get::<_, String>(0))
                .expect("query");
            let mut out = Vec::new();
            for reason in found {
                out.push(reason.expect("reason"));
            }
            out
        };
        let mut sorted = reasons.clone();
        sorted.sort();
        assert_eq!(sorted, vec!["correction", "opening_stock"]);
    }

    #[test]
    fn failed_row_rolls_back_the_whole_batch() {
        let db = Database::in_memory().expect("in-memory database");
        let conn = db.conn();
        let (business, owner) = repo::bootstrap(&conn).expect("bootstrap");
        conn.execute_batch(
            "CREATE TRIGGER block_boom BEFORE INSERT ON products \
             WHEN NEW.name = 'Boom' BEGIN SELECT RAISE(ABORT, 'boom'); END;",
        )
        .expect("trigger");

        let result = import_rows(
            &conn,
            &business.id,
            Some(&owner.id),
            &[row("Tea", Some("T1"), 100.0, 10.0), row("Boom", Some("B1"), 5.0, 1.0)],
            false,
            18.0,
        );
        assert!(result.is_err());

        let products: i64 = conn
            .query_row("SELECT COUNT(*) FROM products WHERE business_id = ?1", params![business.id], |r| {
                r.get(0)
            })
            .expect("count products");
        assert_eq!(products, 0, "the valid row must be rolled back too");
    }
}
