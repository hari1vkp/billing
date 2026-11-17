# Linux packaging

`linux-app/build.sh` checks prerequisites, runs `npm install` and
`npm run tauri:build` from the repository root, then copies Tauri's output into
`linux-app/packaging/dist/`:

```
dist/
  BillFlow-<arch>.AppImage   # from src-tauri/target/release/bundle/appimage/
  billflow_<version>_<arch>.deb  # from src-tauri/target/release/bundle/deb/
  BillFlow.desktop           # freedesktop launcher (Exec=billflow, Icon=billflow)
  billflow.png               # icon from assets/icon.png
```

The `.desktop` file is kept `desktop-file-validate` compliant and is optional —
copy it and the icon into `~/.local/share/applications/` and the icon theme for
a manual desktop-menu entry. Run the AppImage directly:

```bash
chmod +x BillFlow-x86_64.AppImage
./BillFlow-x86_64.AppImage
```

If FUSE is unavailable: `./BillFlow-x86_64.AppImage --appimage-extract-and-run`.
The `.deb` can be installed with a package manager (installation may need root;
building does not).

## Runtime dependencies

Tauri uses the native WebKit2GTK WebView: no Chromium/Node/Python is bundled.
The target machine needs WebKit2GTK 4.1, GTK3, libayatana-appindicator and
librsvg (see [../README.md](../README.md) for package names). Application data
is stored locally in `~/.local/share/billflow/billflow.sqlite3`, with the backend
URL in `settings.json`.
