use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::database::state;

fn default_backup_path() -> PathBuf {
    let stamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    billflow_shared::db::app_data_dir()
        .join("backups")
        .join(format!("billflow-{stamp}.sqlite3"))
}

/// `backup_database` — consistent online backup via `Database::backup`.
#[tauri::command]
pub fn backup_database(path: Option<String>) -> Result<String, String> {
    let target = match path {
        Some(path) => PathBuf::from(path),
        None => default_backup_path(),
    };

    if let Some(parent) = target.parent() {
        if !parent.as_os_str().is_empty() {
            std::fs::create_dir_all(parent)
                .map_err(|e| format!("Could not create backup directory: {e}"))?;
        }
    }

    state()
        .db
        .backup(&target)
        .map_err(|e| format!("Backup failed: {e}"))?;
    Ok(target.to_string_lossy().into_owned())
}

/// `restore_database` — replace local data via `Database::restore`.
#[tauri::command]
pub fn restore_database(path: String) -> Result<(), String> {
    let source = Path::new(&path).to_path_buf();
    if !source.exists() {
        return Err(format!("Backup file not found: {}", source.display()));
    }
    state()
        .db
        .restore(&source)
        .map_err(|e| format!("Restore failed: {e}"))
}
