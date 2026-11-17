//! Serializable payloads returned by the native commands.

use serde::Serialize;

/// Metadata about the running desktop application.
#[derive(Debug, Clone, Serialize)]
pub struct AppInfo {
    pub version: String,
    pub data_dir: String,
    pub db_path: String,
    pub platform: String,
}

/// Health summary of the local SQLite database.
#[derive(Debug, Clone, Serialize)]
pub struct LocalDbStatus {
    pub exists: bool,
    pub path: String,
    pub tables: usize,
}
