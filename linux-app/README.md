# BillFlow for Linux

Build the native Linux desktop application. This is a Rust/eframe binary with
an embedded SQLite database — **no Node.js, Python, browser or web server is
needed at build time or at runtime**.

## Prerequisites

- Rust stable toolchain (`rustup` + `cargo`)
- A C compiler and `pkg-config`
- X11 development headers: `libx11-dev`
- Keyboard handling headers: `libxkbcommon-dev`

On Debian/Ubuntu (installation itself may need root, but the build does not):

```bash
sudo apt install build-essential pkg-config libx11-dev libxkbcommon-dev
```

On Fedora: `sudo dnf install gcc pkgconf-pkg-config libX11-devel libxkbcommon-devel`.
On Arch: `sudo pacman -S base-devel pkgconf libx11 libxkbcommon`.

## Build

From the repository root:

```bash
cargo build --release -p billflow
```

The release binary is written to `target/release/billflow`. Run it directly:

```bash
./target/release/billflow
```

Or, during development, `cargo run -p billflow`.

On a Wayland session the binary uses its X11 backend through XWayland; no
extra flags are normally required.

## Data location

All application state lives in one SQLite file:

```
~/.local/share/billflow/billflow.sqlite3
```

The directory is created automatically on first launch. Deleting that file
resets the app to a fresh demo business. On first run, sign in with
`demo@billingapp.com` / `Demo@1234`.

## Packaging

Use `./build.sh` from this directory to build the binary, stage it together
with `assets/`, and produce either an AppImage (when `appimagetool` is on
`PATH`) or a portable `tar.gz` bundle. No sudo is required.

See [packaging/README.md](packaging/README.md) for the output formats and
runtime library requirements.
