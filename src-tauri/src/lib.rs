#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

//! Tauri 2 shell for BillFlow.
//!
//! The React frontend remains the visual source of truth; this crate only adds
//! native capabilities (local SQLite bootstrap, backup/restore, save dialogs
//! and OS printing). All business logic comes from `billflow-shared`.

pub mod commands;
pub mod database;
pub mod models;
pub mod services;

use std::io::Error as IoError;
use std::sync::OnceLock;

use tauri::Manager;

/// Capture the handle once so commands can keep the exact signatures declared
/// in `TAURI_CONTRACT.md` (no injected `AppHandle` parameter).
static APP_HANDLE: OnceLock<tauri::AppHandle> = OnceLock::new();

pub(crate) fn app_handle() -> &'static tauri::AppHandle {
    APP_HANDLE
        .get()
        .expect("application handle not initialized")
}

/// Entry point used by both `main.rs` and integration tests.
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let state = std::sync::Arc::new(
                database::init().map_err(|e| IoError::new(std::io::ErrorKind::Other, e))?,
            );

            // Register with Tauri's state manager and keep a shared reference
            // available to the (signature-stable) command functions below.
            app.manage(state.clone());
            database::APP_STATE.set(state).map_err(|_| {
                IoError::new(std::io::ErrorKind::Other, "state already initialized")
            })?;
            APP_HANDLE.set(app.handle().clone()).map_err(|_| {
                IoError::new(std::io::ErrorKind::Other, "app handle already initialized")
            })?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::app::app_info,
            commands::backend::get_backend_url,
            commands::backend::set_backend_url,
            commands::backup::backup_database,
            commands::backup::restore_database,
            commands::export::save_export_bytes,
            commands::print::print_file,
            commands::local_db::local_db_status,
        ])
        .run(tauri::generate_context!())
        .expect("error while running BillFlow");
}
