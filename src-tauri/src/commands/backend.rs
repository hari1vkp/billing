use crate::{database::state, services::config};

/// `get_backend_url` — return the persisted (or default) FastAPI base URL.
#[tauri::command]
pub fn get_backend_url() -> String {
    match state().config.lock() {
        Ok(cfg) => cfg.backend_url.clone(),
        Err(_) => config::load_config().backend_url,
    }
}

/// `set_backend_url` — validate, persist and cache a new FastAPI base URL.
#[tauri::command]
pub fn set_backend_url(url: String) -> Result<(), String> {
    let validated = config::validate_backend_url(&url)?;
    let mut cfg = state()
        .config
        .lock()
        .map_err(|_| "Configuration lock poisoned".to_string())?;
    cfg.backend_url = validated;
    config::save_config(&cfg)
}
