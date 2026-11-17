# Windows packaging

`windows-app\build.ps1` checks prerequisites, runs `npm install` and
`npm run tauri:build` from the repository root, then copies Tauri's output into
`windows-app\packaging\dist\`:

```
dist\
  BillFlow_<version>_x64-setup.exe   # NSIS installer, from bundle\nsis\
  BillFlow_<version>_x64.msi         # MSI, from bundle\msi\
```

Both come from `src-tauri\target\release\bundle\`. The NSIS installer is
per-user and needs no administrator rights. Tauri's installers replace the old
custom Inno Setup script, which has been removed.

The app uses the system WebView2 control, so no Chromium/Node/Python runtime is
bundled. Windows 10/11 (64-bit) with WebView2 is required at run time.
Application data is local in `%APPDATA%\BillFlow\billflow.sqlite3`, with the
backend URL in `settings.json`. No admin rights are needed to build or package.
