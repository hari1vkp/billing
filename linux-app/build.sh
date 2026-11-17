#!/usr/bin/env bash
set -euo pipefail

# BillFlow Linux build + packaging (Tauri 2).
# Builds the React frontend and the Rust Tauri shell with the Tauri CLI, then
# stages the generated AppImage/deb into packaging/dist/.
# Runs entirely as a normal user: no sudo, no manual AppDir assembly.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="$SCRIPT_DIR/packaging/dist"
BUNDLE_DIR="$ROOT_DIR/src-tauri/target/release/bundle"
DESKTOP_SRC="$SCRIPT_DIR/packaging/BillFlow.desktop"
ICON_SRC="$ROOT_DIR/assets/icon.png"

# --- prerequisites ---------------------------------------------------------
# Tauri needs Node/npm (frontend + CLI) and Rust (native shell). The Linux
# WebKit2GTK/GTK3 system libraries are required to compile and run the native
# WebView; see linux-app/README.md for the distro package names.
for cmd in node npm cargo rustc; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "error: '$cmd' is required to build BillFlow." >&2
    echo "       Install Node.js (LTS, includes npm) and the Rust stable toolchain (https://rustup.rs/)." >&2
    exit 1
  fi
done

if [[ ! -f "$ROOT_DIR/package.json" ]]; then
  echo "error: expected root package.json at $ROOT_DIR/package.json (npm scripts live there)." >&2
  exit 1
fi
if [[ ! -f "$ROOT_DIR/src-tauri/tauri.conf.json" ]]; then
  echo "error: expected Tauri config at $ROOT_DIR/src-tauri/tauri.conf.json" >&2
  exit 1
fi
if [[ ! -f "$ICON_SRC" ]]; then
  echo "error: $ICON_SRC is missing (see assets/README.md)" >&2
  exit 1
fi
if [[ ! -f "$DESKTOP_SRC" ]]; then
  echo "error: freedesktop launcher $DESKTOP_SRC is missing" >&2
  exit 1
fi

# --- build -----------------------------------------------------------------
echo "==> Installing frontend dependencies (npm install)"
( cd "$ROOT_DIR" && npm install )

echo "==> Building Tauri app (npm run tauri:build)"
( cd "$ROOT_DIR" && npm run tauri:build )

# --- stage outputs ----------------------------------------------------------
echo "==> Staging artifacts into $DIST_DIR"
rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"

copied=0
while IFS= read -r -d '' artifact; do
  case "$artifact" in
    *.AppImage) install -m 0755 "$artifact" "$DIST_DIR/" ;;
    *)          install -m 0644 "$artifact" "$DIST_DIR/" ;;
  esac
  echo "    staged: $(basename -- "$artifact")"
  copied=$((copied + 1))
done < <(find "$BUNDLE_DIR" -type f \( -name '*.AppImage' -o -name '*.deb' \) -print0 2>/dev/null)

if [[ "$copied" -eq 0 ]]; then
  echo "error: no AppImage or .deb found under $BUNDLE_DIR" >&2
  echo "       expected output in $BUNDLE_DIR/appimage/ or $BUNDLE_DIR/deb/" >&2
  exit 1
fi

# Keep the freedesktop launcher and icon alongside the packages for anyone who
# wants a manual desktop-menu entry. BillFlow.desktop remains desktop-file-validate
# compliant (Exec=billflow, Icon=billflow).
cp "$DESKTOP_SRC" "$DIST_DIR/BillFlow.desktop"
cp "$ICON_SRC" "$DIST_DIR/billflow.png"

echo "==> Done. BillFlow packages are in: $DIST_DIR"
ls -1 "$DIST_DIR"
echo "    (The .desktop launcher and billflow.png icon are for optional manual installation.)"
