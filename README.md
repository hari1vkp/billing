# BillFlow — billing, CRM & business analytics

BillFlow is a **Tauri 2** desktop app: a thin Rust shell around the **existing
React frontend** (`frontend/`, reused unchanged). The Rust layer handles native
operations and keeps credentials out of the browser; a WebView renders the same
UI as the web app. There is no bundled Chromium — the OS WebView is used
(WebKit2GTK on Linux, WebView2 on Windows).

## Architecture

| Path | Role |
| --- | --- |
| `frontend/` | Existing React + TypeScript + Vite UI — the visual source of truth, reused unchanged |
| `src-tauri/` | Tauri 2 shell: Rust commands, config, capabilities and icons; bundles `frontend/dist` |
| `shared/` | `billflow-shared` library — SQLite models, migrations, repositories and services reused by `src-tauri` |
| `backend/` | Original FastAPI backend — centralized PostgreSQL data service |
| `linux-app/`, `windows-app/` | Platform build scripts and packaging |
| `assets/` | Source icon and generated PNG/ICO files |
| `desktop/` | Legacy egui attempt — retained but not built |

The Tauri integration contract is in [TAURI_CONTRACT.md](TAURI_CONTRACT.md).
The Rust workspace members are `shared` and `src-tauri`.

## Hybrid data model

- **Centralized data** — the React UI calls the existing FastAPI backend for
  shared business data backed by PostgreSQL. The backend URL is configurable
  in Settings → Desktop connection and defaults to `http://127.0.0.1:8000/api/v1`.
- **Local SQLite** — `billflow-shared` powers offline/native operations such as
  local database status, backup and restore, native save dialogs and printing.
- **Credentials stay in Rust** — privileged native work is exposed as a small
  set of Tauri commands; the frontend never handles secrets directly.

This is not a fully offline multi-user mode: shared operations still require a
running backend.

## Features

- **Point of sale** — multi-item cart with quantity and discount controls,
  GST totals and a two-tab checkout (UPI QR / cash).
- **Barcode lookup** — scan or type a barcode to add a product to the cart.
- **UPI QR payments** — amount-locked `upi://pay` QR from the business VPA.
- **Inventory** — products and services, SKU/HSN, stock tracking, low-stock
  alerts and audited adjustments.
- **Customers** — profiles, purchase history, outstanding balances and notes.
- **Analytics** — sales, collections, growth, trends, payment-method split and
  top products/customers.
- **Roles and audit** — owner/staff roles and an activity log.
- **Reports** — CSV exports and PDF invoices via native save/print commands.

## Quick start

With Node/npm and Rust installed:

```bash
npm install
npm run tauri:dev
```

The backend must be running for shared data features. Sign in with the demo
account `demo@billingapp.com` / `Demo@1234`.

## Build

- [Linux build](linux-app/README.md) and [Linux packaging](linux-app/packaging/README.md)
- [Windows build](windows-app/README.md) and [Windows packaging](windows-app/packaging/README.md)

`npm run tauri:build` produces installers under
`src-tauri/target/release/bundle/`; the platform scripts stage them into
`linux-app/packaging/dist/` or `windows-app/packaging/dist/`.

## Data locations

| Platform | Local SQLite | Backend URL setting |
| --- | --- | --- |
| Linux | `~/.local/share/billflow/billflow.sqlite3` | `~/.local/share/billflow/settings.json` |
| Windows | `%APPDATA%\BillFlow\billflow.sqlite3` | `%APPDATA%\BillFlow\settings.json` |

## Legacy

`desktop/` holds the earlier egui/Rust prototype. It is retained as a reference
but is not a workspace member and is not built. `backend/` and `frontend/`
remain the original full-stack web app; see their own folders for that setup.
