//! Native CSV import fallback used when the FastAPI backend is unavailable.

use billflow_shared::models::ImportSummary;
use billflow_shared::repo;
use billflow_shared::services::imports::{import_rows, parse_csv, IMPORT_TEMPLATE};

use crate::database::state;

const DEFAULT_GST_RATE: f64 = 18.0;

/// `import_products_csv` — parse and atomically import a CSV string into the
/// local SQLite database. Invalid rows are reported in the summary and skipped;
/// a database failure rolls the whole batch back.
#[tauri::command]
pub fn import_products_csv(csv: String, overwrite_stock: bool) -> Result<ImportSummary, String> {
    let db = state();
    let conn = db.db.conn();

    let (rows, parse_errors) = parse_csv(&csv, DEFAULT_GST_RATE).map_err(|e| e.to_string())?;
    let (business, owner) = repo::bootstrap(&conn).map_err(|e| e.to_string())?;

    let mut summary = import_rows(
        &conn,
        &business.id,
        Some(&owner.id),
        &rows,
        overwrite_stock,
        DEFAULT_GST_RATE,
    )
    .map_err(|e| e.to_string())?;

    if !parse_errors.is_empty() {
        summary.skipped += parse_errors.len() as i64;
        summary.errors.extend(parse_errors);
        summary.errors.sort_by_key(|(row, _)| *row);
    }
    Ok(summary)
}

/// `import_template_csv` — the canonical CSV header plus a commented example.
#[tauri::command]
pub fn import_template_csv() -> String {
    IMPORT_TEMPLATE.to_string()
}
