//! Local SQLite lifecycle and application state.
//!
//! Migrations, tenant bootstrap and demo seeding all come from
//! `billflow-shared`; no SQL is duplicated here.

use std::sync::{Arc, Mutex, OnceLock};

use billflow_shared::db::{default_db_path, migrate, Database};
use billflow_shared::repo::bootstrap;
use billflow_shared::services::seed::seed_demo;

use crate::services::config::{self, AppConfig};

/// State registered with Tauri and shared with the command functions.
pub struct AppState {
    pub db: Database,
    pub config: Mutex<AppConfig>,
}

/// Shared handle used by commands whose signatures are fixed by the contract.
pub static APP_STATE: OnceLock<Arc<AppState>> = OnceLock::new();

pub fn state() -> &'static AppState {
    APP_STATE
        .get()
        .expect("application state not initialized")
        .as_ref()
}

/// Open (or create) the local database, migrate it, ensure a default tenant
/// exists, seed idempotent demo data and load the native settings file.
pub fn init() -> Result<AppState, String> {
    let db = Database::open(&default_db_path())
        .map_err(|e| format!("Could not open local database: {e}"))?;

    {
        let conn = db.conn();
        migrate(&conn).map_err(|e| format!("Could not migrate local database: {e}"))?;
    }
    {
        let conn = db.conn();
        bootstrap(&conn).map_err(|e| format!("Could not bootstrap local database: {e}"))?;
    }
    {
        let conn = db.conn();
        seed_demo(&conn).map_err(|e| format!("Could not seed local database: {e}"))?;
    }

    Ok(AppState {
        db,
        config: Mutex::new(config::load_config()),
    })
}
