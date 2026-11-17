use std::path::PathBuf;

use tauri_plugin_dialog::DialogExt;

use crate::app_handle;

/// `save_export_bytes` — ask the user where to save an export, then write the
/// bytes. A cancelled dialog is reported as the exact string `Cancelled`.
#[tauri::command]
pub fn save_export_bytes(name: String, bytes: Vec<u8>) -> Result<String, String> {
    let chosen = app_handle()
        .dialog()
        .file()
        .set_file_name(&name)
        .blocking_save_file()
        .ok_or_else(|| "Cancelled".to_string())?;

    let path: PathBuf = chosen.into_path().map_err(|e| e.to_string())?;
    std::fs::write(&path, &bytes).map_err(|e| format!("Could not write file: {e}"))?;
    Ok(path.to_string_lossy().into_owned())
}
