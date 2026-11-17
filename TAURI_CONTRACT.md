# BillFlow Tauri 2 integration contract

The React frontend under `frontend/` is the **visual source of truth** and must
not be redesigned. Tauri adds a thin Rust layer for native operations; the
existing FastAPI backend remains the centralized PostgreSQL data service.

## Root workspace
`Cargo.toml` members become `["shared", "src-tauri"]`. The `desktop/` egui crate
is retained on disk as legacy but is no longer a workspace member and is not
built. `src-tauri` depends on `billflow-shared` (path `../shared`) so SQLite
models, migrations, repositories and business services are reused.

## Tauri commands (invoke names must match exactly)
All are registered in `src-tauri/src/lib.rs` via `invoke_handler`.

```rust
#[tauri::command] fn app_info() -> AppInfo
// AppInfo { version: String, data_dir: String, db_path: String, platform: String }

#[tauri::command] fn get_backend_url() -> String
// Default "http://127.0.0.1:8000/api/v1"; persisted in <data_dir>/settings.json

#[tauri::command] fn set_backend_url(url: String) -> Result<(), String>
// Trim trailing '/'; reject non-http(s) URLs; persist.

#[tauri::command] fn backup_database(path: Option<String>) -> Result<String, String>
// Uses billflow_shared::db::Database::backup; default path <data_dir>/backups/billflow-<timestamp>.sqlite3

#[tauri::command] fn restore_database(path: String) -> Result<(), String>
// Uses Database::restore.

#[tauri::command] fn save_export_bytes(name: String, bytes: Vec<u8>) -> Result<String, String>
// Native save dialog (tauri-plugin-dialog), write bytes with std::fs, return full path.
// Cancelled dialog returns Err("Cancelled").

#[tauri::command] fn print_file(path: String) -> Result<(), String>
// Linux: xdg-open / gio open; Windows: powershell Start-Process -Verb Print.

#[tauri::command] fn local_db_status() -> LocalDbStatus
// LocalDbStatus { exists: bool, path: String, tables: usize }
```

## Frontend integration
- Add `@tauri-apps/api`, `@tauri-apps/plugin-dialog`, `@tauri-apps/plugin-shell`
  as dependencies and `@tauri-apps/cli` as a devDependency.
- Add `npm` scripts: `"tauri": "tauri"`, `"tauri:dev": "tauri dev"`,
  `"tauri:build": "tauri build"`.
- Detect Tauri with `'__TAURI_INTERNALS__' in window`.
- In Tauri mode, `src/api/client.ts` must use the configured backend URL as the
  base: `await invoke('get_backend_url')` (cached after first call) instead of
  the relative `/api/v1`. In browser mode keep the current relative `/api/v1`.
  No other frontend file should need changes to keep the UI identical.
- Add `src/tauri.ts` exporting typed wrappers for the commands above, and a
  `downloadNative(name, bytes)` helper that calls `save_export_bytes` in Tauri
  and falls back to the existing browser blob download otherwise.
- Update only the two download call sites (POS/invoice PDF and analytics CSV)
  to use `downloadNative` if needed; do not alter their JSX/layout.
- Settings page may show a "Desktop connection" section with backend URL and
  backup/restore buttons, using existing styling primitives (optional).

## Tauri config
- `src-tauri/tauri.conf.json`: identifier `com.billflow.desktop`, productName
  `BillFlow`, version `1.0.0`, `build.frontendDist: "../frontend/dist"`,
  `build.devUrl: "http://localhost:5173"`, main window 1440×900, min 1024×680,
  title "BillFlow", `withGlobalTauri: false`.
- `capabilities/default.json`: `core:default`, `dialog:allow-save`,
  `shell:allow-open`, and no broad filesystem scopes. Custom commands handle
  all privileged work.
- Icons generated from `assets/icon.png` (32, 128, 128@2x, ICO).

## Packaging
- `linux-app/build.sh` uses `npm run tauri:build` and packages
  `src-tauri/target/release/bundle/appimage` or `deb` as before.
- `windows-app/build.ps1` uses `npm run tauri:build` and packages the NSIS/MSI
  output from `src-tauri/target/release/bundle`.
- Both keep their existing README guidance, updated for Tauri.
