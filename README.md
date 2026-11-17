# BillFlow — native billing, CRM & business analytics

BillFlow is a native Rust desktop application for small and medium businesses
in India. It runs as a single executable with an embedded SQLite database:
**no Node.js, Python, browser, web server or database server is required at
runtime**. It is built with eframe/egui and rusqlite.

## Architecture

| Path | Role |
| --- | --- |
| `shared/` | `billflow-shared` library — models, migrations, repositories, money/auth/audit helpers and billing, inventory, payments, analytics, reports and seed services over SQLite |
| `desktop/` | `billflow` binary crate — the eframe/egui native UI (login, staff POS and admin console) under `desktop/src/ui/` |
| `linux-app/` | Linux build script, freedesktop launcher and AppImage / portable-bundle packaging |
| `windows-app/` | Windows build script, Inno Setup script and portable-ZIP packaging |
| `assets/` | Source icon (`icon.svg`) and generated `icon.png` / `icon.ico` |

The shared API contract lives in [CONTRACT.md](CONTRACT.md). The workspace is
defined in the root `Cargo.toml` (`members = ["shared", "desktop"]`).

## Features

- **Point of sale** — multi-item cart with quantity and discount controls,
  invoice totals with GST, and a two-tab checkout (UPI QR / cash).
- **Barcode lookup** — scan or type a barcode to add a product to the cart.
- **UPI QR payments** — amount-locked `upi://pay` QR generated from the
  business VPA; cash sales are supported as the alternative method.
- **Inventory** — products and services, SKU/HSN, stock tracking, low-stock
  alerts and audited stock adjustments.
- **Customers** — profiles, purchase history, outstanding balances, notes and
  interactions.
- **Analytics** — sales, collections, growth, trends, payment-method split,
  top products and customers — all computed from persisted SQLite records.
- **Roles and audit** — owner/staff roles and an activity log.
- **Reports** — CSV sales exports and PDF invoices.
- **SQLite storage** — one local database file with WAL journalling.

## Quick start

```bash
cargo run -p billflow
```

On first launch the database is bootstrapped with a demo business. Sign in with
`demo@billingapp.com` / `Demo@1234`.

## Build

```bash
# Debug
cargo run -p billflow

# Optimised release binary -> target/release/billflow (or billflow.exe)
cargo build --release -p billflow
```

Platform-specific build and packaging instructions:

- [Linux build](linux-app/README.md) and [Linux packaging](linux-app/packaging/README.md)
- [Windows build](windows-app/README.md) and [Windows packaging](windows-app/packaging/README.md)

The release profile in `Cargo.toml` targets a small, fast binary
(`opt-level = "z"`, LTO, one codegen unit, `panic = "abort"`, stripped symbols).
`rusqlite` is compiled with its `bundled` feature, so SQLite needs no separate
installation. Queries run in-process against a local file with WAL enabled, so
there is no network hop and no server to manage.

## Data location

| Platform | Database file |
| --- | --- |
| Linux | `~/.local/share/billflow/billflow.sqlite3` |
| Windows | `%APPDATA%\BillFlow\billflow.sqlite3` |

The directory is created automatically on first launch; deleting the file
starts a fresh demo business.

## Legacy web implementation (untouched)

The original full-stack web version remains in `backend/` (FastAPI, SQLAlchemy,
PostgreSQL) and `frontend/` (React, TypeScript, Vite). These directories are
left **untouched** and are not part of the native Rust build. They are kept for
reference; see their own folders for the previous setup instructions.
