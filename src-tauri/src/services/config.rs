//! Persistence for native-only settings.
//!
//! `settings.json` lives next to the local SQLite file in the app data dir.
//! It never leaves the Rust layer: frontend commands only see the validated
//! backend URL returned by `get_backend_url`.

use std::fs;
use std::path::PathBuf;

use billflow_shared::db::app_data_dir;
use serde::{Deserialize, Serialize};

pub const DEFAULT_BACKEND_URL: &str = "http://127.0.0.1:8000/api/v1";

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AppConfig {
    pub backend_url: String,
}

impl Default for AppConfig {
    fn default() -> Self {
        Self {
            backend_url: DEFAULT_BACKEND_URL.to_string(),
        }
    }
}

/// Full path of the on-disk settings file.
pub fn config_path() -> PathBuf {
    app_data_dir().join("settings.json")
}

/// Load settings, falling back to defaults for a missing or malformed file.
pub fn load_config() -> AppConfig {
    let contents = match fs::read_to_string(config_path()) {
        Ok(contents) => contents,
        Err(_) => return AppConfig::default(),
    };
    serde_json::from_str::<AppConfig>(&contents).unwrap_or_default()
}

/// Persist settings, creating the app data directory when needed.
pub fn save_config(config: &AppConfig) -> Result<(), String> {
    let path = config_path();
    if let Some(parent) = path.parent() {
        if !parent.as_os_str().is_empty() {
            fs::create_dir_all(parent)
                .map_err(|e| format!("Could not create app data directory: {e}"))?;
        }
    }
    let json = serde_json::to_string_pretty(config).map_err(|e| e.to_string())?;
    fs::write(&path, json).map_err(|e| format!("Could not write settings.json: {e}"))
}

/// Validate the backend URL and normalise it by trimming whitespace and any
/// trailing slashes. Only `http://` and `https://` URLs with a host are allowed.
pub fn validate_backend_url(raw: &str) -> Result<String, String> {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return Err("Backend URL must not be empty".into());
    }
    let (scheme, rest) = trimmed
        .split_once("://")
        .ok_or_else(|| "Backend URL must start with http:// or https://".to_string())?;
    if !scheme.eq_ignore_ascii_case("http") && !scheme.eq_ignore_ascii_case("https") {
        return Err("Backend URL must use http or https".into());
    }
    let authority = rest.split(['/', '?', '#']).next().unwrap_or("");
    if authority.is_empty() {
        return Err("Backend URL must include a host".into());
    }
    Ok(trimmed.trim_end_matches('/').to_string())
}
