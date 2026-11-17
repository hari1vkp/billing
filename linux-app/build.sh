#!/usr/bin/env bash
set -euo pipefail

# BillFlow native Linux build + portable packaging.
# Runs entirely as a normal user: no sudo, no Node, no Python, no browser.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
STAGING_PARENT="$SCRIPT_DIR/packaging/staged"
APPDIR="$STAGING_PARENT/BillFlow"
BIN="billflow"
ARCH="$(uname -m)"

echo "==> Building release binary (cargo build --release -p $BIN)"
cargo build --release --manifest-path "$ROOT_DIR/Cargo.toml" -p "$BIN"

BIN_SRC="$ROOT_DIR/target/release/$BIN"
if [[ ! -f "$BIN_SRC" ]]; then
  echo "error: expected binary at $BIN_SRC was not produced" >&2
  exit 1
fi
if [[ ! -f "$ROOT_DIR/assets/icon.png" ]]; then
  echo "error: assets/icon.png is missing (see assets/README.md)" >&2
  exit 1
fi

echo "==> Staging AppDir at $APPDIR"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/assets"

install -m 0755 "$BIN_SRC" "$APPDIR/usr/bin/$BIN"
cp -R "$ROOT_DIR/assets/." "$APPDIR/assets/"

# AppImage metadata: the launcher and the icon must be at the AppDir root,
# matching Exec=billflow / Icon=billflow in the .desktop file.
cp "$SCRIPT_DIR/packaging/BillFlow.desktop" "$APPDIR/billflow.desktop"
cp "$ROOT_DIR/assets/icon.png" "$APPDIR/billflow.png"

cat > "$APPDIR/AppRun" <<'EOR'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
export LD_LIBRARY_PATH="$HERE/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$HERE/usr/bin/billflow" "$@"
EOR
chmod +x "$APPDIR/AppRun"

echo "==> Packaging"
if command -v appimagetool >/dev/null 2>&1; then
  APPIMAGE="$SCRIPT_DIR/packaging/BillFlow-${ARCH}.AppImage"
  echo "appimagetool found; creating $APPIMAGE"
  appimagetool "$APPDIR" "$APPIMAGE"
  echo "AppImage ready: $APPIMAGE"
  echo "Run it with: chmod +x '$APPIMAGE' && '$APPIMAGE'"
else
  # Fallback: a plain portable bundle. appimagetool is a standalone download;
  # nothing is installed here, so this path needs no privileges either.
  echo "appimagetool not found on PATH - falling back to a portable tar.gz bundle."
  echo "To get an AppImage, put appimagetool on PATH and re-run this script."
  TARBALL="$SCRIPT_DIR/packaging/BillFlow-portable-${ARCH}.tar.gz"
  tar -czf "$TARBALL" -C "$STAGING_PARENT" BillFlow
  echo "Portable bundle ready: $TARBALL"
  echo "Run it with: tar -xzf '$TARBALL' && ./BillFlow/AppRun"
fi

echo "==> Done. Staged files remain in: $APPDIR"
