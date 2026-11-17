# BillFlow for Windows

Build the native Windows desktop application. It is a Rust/eframe executable
with an embedded SQLite database — **no Node.js, Python, browser or web server
is needed at build time or at runtime**.

## Prerequisites

- Windows 10 or 11 (64-bit)
- Rust stable toolchain via [rustup](https://rustup.rs/) (includes `cargo` and
  the MSVC linker via the Visual Studio Build Tools "C++ build tools" workload)

No Node.js, Python, browser, PostgreSQL or Docker is required.

## Build

From a terminal at the repository root:

```powershell
cargo build --release -p billflow
```

The executable is written to `target\release\billflow.exe`. Copy that file and
the `assets` folder anywhere and run it — it is fully portable.

During development you can use `cargo run -p billflow`.

## Data location

Application state is a single SQLite file:

```
%APPDATA%\BillFlow\billflow.sqlite3
```

The directory is created on first launch. Deleting the file resets the app to
a fresh demo business. On first run, sign in with
`demo@billingapp.com` / `Demo@1234`.

## Packaging

Run `.\build.ps1` from PowerShell in this directory. It builds the release
binary, stages it with `assets\icon.ico` under
`windows-app\packaging\staged\BillFlow\`, and always produces a portable ZIP.
If the Inno Setup compiler (`iscc`) is on `PATH`, it additionally builds a
setup executable. The script does not require administrator rights.

See [packaging/README.md](packaging/README.md) for the two output formats.
