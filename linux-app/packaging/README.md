# Linux packaging

`linux-app/build.sh` builds the native binary with
`cargo build --release -p billflow`, then stages this layout under
`linux-app/packaging/staged/BillFlow/`:

```
BillFlow/
  AppRun                      # launcher used by the bundle / AppImage
  billflow.desktop            # freedesktop launcher (Exec=billflow, Icon=billflow)
  billflow.png                # 256x256 icon from assets/icon.png
  assets/                     # source icon assets
  usr/bin/billflow            # release binary
```

The script is non-interactive, needs no sudo, and does not install anything
system-wide.

## Two output options

### 1. AppImage (preferred)

If `appimagetool` is on `PATH`, the script produces
`linux-app/packaging/BillFlow-<arch>.AppImage`. It is a single self-contained
file: make it executable and run it.

```bash
chmod +x BillFlow-x86_64.AppImage
./BillFlow-x86_64.AppImage
```

`appimagetool` is a standalone download, not an installed package. If FUSE is
unavailable on the target machine, run
`./BillFlow-x86_64.AppImage --appimage-extract-and-run`.

### 2. Portable `tar.gz` bundle (fallback)

When `appimagetool` is not on `PATH`, the script writes
`linux-app/packaging/BillFlow-portable-<arch>.tar.gz` instead. Extract it and
run the `AppRun` launcher (or `usr/bin/billflow` directly):

```bash
tar -xzf BillFlow-portable-x86_64.tar.gz
./BillFlow/AppRun
```

The `.desktop` file in `linux-app/packaging/BillFlow.desktop` can also be
copied to `~/.local/share/applications/` for a desktop-menu entry; it expects
`billflow` on `PATH` or a matching icon install.

## Minimal runtime dependencies

The Rust binary itself is self-contained apart from the system C library:

- glibc (a recent Linux distribution)
- X11 client libraries (`libX11`, `libXcursor`, `libXrandr`, `libXi`) for the
  eframe `x11` backend, or XWayland on a Wayland session
- `libxkbcommon` for keyboard handling

No Node.js, Python, browser, web server or database server is required at
runtime. Application data is stored in `~/.local/share/billflow/billflow.sqlite3`.
