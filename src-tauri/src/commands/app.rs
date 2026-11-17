use billflow_shared::db::{app_data_dir, default_db_path};

use crate::models::AppInfo;

/// `app_info` — version, data directory, database path and OS platform.
#[tauri::command]
pub fn app_info() -> AppInfo {
    AppInfo {
        version: env!("CARGO_PKG_VERSION").to_string(),
        data_dir: app_data_dir().to_string_lossy().into_owned(),
        db_path: default_db_path().to_string_lossy().into_owned(),
        platform: std::env::consts::OS.to_string(),
    }
}
