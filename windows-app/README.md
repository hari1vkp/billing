# BillFlow for Windows

Builds the Tauri 2 desktop app: a thin Rust shell around the **existing React
frontend** (`frontend/`, reused unchanged). Tauri uses the system WebView2
control, so no Chromium/Node/Python runtime is bundled or installed.

## Prerequisites

- Windows 10 or 11 (64-bit) with the WebView2 Runtime (bundled in Windows 11;
  install the Evergreen runtime on Windows 10 if missing)
- Node.js LTS + npm, and the Rust stable toolchain via
  [rustup](https://rustup.rs/) with the Visual Studio "C++ build tools" workload
  (MSVC linker)

No administrator rights are needed to build or package.

## Build

From a terminal at the repository root:

```powershell
npm install
npm run tauri:build
```

Or run `.\build.ps1` from PowerShell in this directory — it checks prerequisites,
runs both commands and stages the result.

## Outputs

Tauri writes bundles to `src-tauri\target\release\bundle\` (`nsis\` and `msi\`).
`build.ps1` copies the NSIS `.exe` installer and/or `.msi` into
`windows-app\packaging\dist\`. The NSIS installer is per-user and needs no admin.

During development use `npm run tauri:dev` from the repository root.

## Data locations

- Local SQLite (offline/native operations): `%APPDATA%\BillFlow\billflow.sqlite3`
- Backend URL setting: `%APPDATA%\BillFlow\settings.json`

See [packaging/README.md](packaging/README.md) for details.
