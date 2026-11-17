# BillFlow — Tauri 2 layer

This crate is the thin native shell around the existing React frontend. It does
not contain business logic: persistence, migrations, repositories, billing math
and demo data all come from the `billflow-shared` crate. The FastAPI backend
remains the central data service; the local SQLite file is used for offline /
native features and backups.

`settings.json` (backend URL) and the SQLite file live in the shared app data
directory reported by `billflow-shared::db::app_data_dir()` (for example
`~/.local/share/billflow` on Linux). The backend URL is cached in Rust state and
persisted on change; DB credentials are never exposed to the frontend.

## Commands

Registered in `src/lib.rs` under these exact invoke names:

| Invoke name | Rust signature | Purpose |
| --- | --- | --- |
| `app_info` | `() -> AppInfo` | Version, data dir, DB path and platform |
| `get_backend_url` | `() -> String` | Persisted FastAPI base URL (default `http://127.0.0.1:8000/api/v1`) |
| `set_backend_url` | `(String) -> Result<(), String>` | Validate (http/https), trim trailing `/`, persist |
| `backup_database` | `(Option<String>) -> Result<String, String>` | `Database::backup`; default `<data_dir>/backups/billflow-<timestamp>.sqlite3` |
| `restore_database` | `(String) -> Result<(), String>` | `Database::restore` |
| `save_export_bytes` | `(String, Vec<u8>) -> Result<String, String>` | Native save dialog + `std::fs` write; returns full path or `Err("Cancelled")` |
| `print_file` | `(String) -> Result<(), String>` | Linux `xdg-open`/`gio open`, Windows `powershell -Verb Print` |
| `local_db_status` | `() -> LocalDbStatus` | `{ exists, path, tables }` for the local SQLite DB |

## Layout

- `src/lib.rs` — builder, plugins, setup (DB migrate/bootstrap/seed via shared crate), command registration.
- `src/main.rs` — delegates to `billflow_tauri_lib::run()`.
- `src/commands/` — one module per command group.
- `src/database/mod.rs` — `AppState`, global handle and DB init helper.
- `src/services/config.rs` — `settings.json` load/save and URL validation.
- `src/models/mod.rs` — serializable `AppInfo` / `LocalDbStatus` payloads.
- `capabilities/default.json` — minimal permissions (`core:default`, `dialog:allow-save`, `shell:allow-open`); no broad filesystem scope.
- `icons/` — generated from `assets/icon.png`.

## Build

From `frontend/` run `npm run tauri:dev` or `npm run tauri:build`. The config
expects the Vite dev server at `http://localhost:5173` and the production bundle
at `../frontend/dist`.
