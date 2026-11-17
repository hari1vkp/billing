use billflow_shared::db::default_db_path;

use crate::{database::state, models::LocalDbStatus};

/// `local_db_status` — existence, path and user-table count of the local DB.
#[tauri::command]
pub fn local_db_status() -> LocalDbStatus {
    let path = default_db_path();
    let exists = path.exists();
    let tables = state()
        .db
        .conn()
        .query_row(
            "SELECT COUNT(*) FROM sqlite_master \
             WHERE type = 'table' AND name NOT LIKE 'sqlite_%'",
            [],
            |row| row.get::<_, i64>(0),
        )
        .unwrap_or(0) as usize;

    LocalDbStatus {
        exists,
        path: path.to_string_lossy().into_owned(),
        tables,
    }
}
