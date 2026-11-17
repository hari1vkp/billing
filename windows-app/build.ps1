# BillFlow Windows build + packaging (Tauri 2).
# Builds the React frontend and the Rust Tauri shell with the Tauri CLI, then
# stages the generated NSIS .exe / MSI installer into packaging\dist\.
# Runs as a normal user: no administrator rights.

$ErrorActionPreference = 'Stop'

$ScriptDir = $PSScriptRoot
$RootDir = Split-Path -Parent $ScriptDir
$DistDir = Join-Path $ScriptDir 'packaging\dist'
$BundleDir = Join-Path $RootDir 'src-tauri\target\release\bundle'
$RootPackageJson = Join-Path $RootDir 'package.json'
$TauriConf = Join-Path $RootDir 'src-tauri\tauri.conf.json'

# --- prerequisite sanity checks --------------------------------------------
# Tauri needs Node/npm (frontend + CLI) and Rust (native shell). WebView2 is
# supplied by the OS/runtime at run time, not installed by this script.
foreach ($cmd in @('node', 'npm', 'cargo', 'rustc')) {
    if (-not (Get-Command -Name $cmd -ErrorAction SilentlyContinue)) {
        throw "'$cmd' is required to build BillFlow. Install Node.js (LTS, includes npm) and the Rust stable toolchain (https://rustup.rs/)."
    }
}
if (-not (Test-Path -LiteralPath $RootPackageJson)) {
    throw "Expected root package.json not found: $RootPackageJson"
}
if (-not (Test-Path -LiteralPath $TauriConf)) {
    throw "Expected Tauri config not found: $TauriConf"
}

# --- build ------------------------------------------------------------------
Push-Location $RootDir
try {
    Write-Host '==> Installing frontend dependencies (npm install)'
    & npm install
    if ($LASTEXITCODE -ne 0) { throw "npm install failed with exit code $LASTEXITCODE" }

    Write-Host '==> Building Tauri app (npm run tauri:build)'
    & npm run tauri:build
    if ($LASTEXITCODE -ne 0) { throw "npm run tauri:build failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}

# --- stage outputs ----------------------------------------------------------
Write-Host "==> Staging installers into $DistDir"
if (Test-Path -LiteralPath $DistDir) {
    Remove-Item -LiteralPath $DistDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

$artifacts = @()
foreach ($sub in @('nsis', 'msi')) {
    $src = Join-Path $BundleDir $sub
    if (Test-Path -LiteralPath $src) {
        $artifacts += Get-ChildItem -LiteralPath $src -File |
            Where-Object { $_.Extension -in @('.exe', '.msi') }
    }
}

if ($artifacts.Count -eq 0) {
    throw "No NSIS .exe or .msi installer found under $BundleDir (looked in nsis\ and msi\)."
}

foreach ($artifact in $artifacts) {
    Copy-Item -LiteralPath $artifact.FullName -Destination $DistDir -Force
    Write-Host "    staged: $($artifact.Name)"
}

Write-Host '==> Done. BillFlow installers are in:'
Get-ChildItem -LiteralPath $DistDir | Select-Object -ExpandProperty FullName
Write-Host 'No administrator rights were required.'
