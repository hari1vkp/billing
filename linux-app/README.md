# BillFlow for Linux

Builds the Tauri 2 desktop app: a thin Rust shell around the **existing React
frontend** (`frontend/`, reused unchanged). Tauri uses the system WebKit2GTK
WebView, so no Chromium/Node/Python runtime is bundled or needed at run time.

## Prerequisites

- Node.js LTS + npm, and the Rust stable toolchain (`rustup` + `cargo`)
- Linux WebView build dependencies: WebKit2GTK 4.1 and GTK3 development libraries

On Debian/Ubuntu (installation may need root; the build does not):

```bash
sudo apt install libwebkit2gtk-4.1-dev libgtk-3-dev libayatana-appindicator3-dev \
  librsvg2-dev build-essential pkg-config curl wget file
```

Fedora: `webkit2gtk4.1-devel gtk3-devel libappindicator-gtk3-devel librsvg2-devel`
Arch: `webkit2gtk-4.1 gtk3 libayatana-appindicator librsvg`

## Build

From the repository root:

```bash
npm install
npm run tauri:build
```

Or run `./build.sh` from this directory — it checks prerequisites, runs both
commands and stages the result. No sudo is needed.

## Outputs

Tauri writes bundles to `src-tauri/target/release/bundle/` (`appimage/` and
`deb/`). `build.sh` copies the produced `.AppImage` and `.deb` into
`linux-app/packaging/dist/`, together with the freedesktop launcher
(`BillFlow.desktop`) and icon (`billflow.png`) for optional manual installation.

During development use `npm run tauri:dev` from the repository root.

## Data locations

- Local SQLite (offline/native operations): `~/.local/share/billflow/billflow.sqlite3`
- Backend URL setting: `~/.local/share/billflow/settings.json`

See [packaging/README.md](packaging/README.md) for details.
