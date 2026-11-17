# BillFlow native Windows build + portable packaging.
# Runs as a normal user: no administrator rights, Node, Python or browser.

$ErrorActionPreference = 'Stop'

$ScriptDir = $PSScriptRoot
$RootDir = Split-Path -Parent $ScriptDir
$StagingParent = Join-Path $ScriptDir 'packaging\staged'
$AppDir = Join-Path $StagingParent 'BillFlow'
$Bin = 'billflow'

Write-Host '==> Building release binary (cargo build --release -p billflow)'
& cargo build --release --manifest-path (Join-Path $RootDir 'Cargo.toml') -p $Bin
if ($LASTEXITCODE -ne 0) {
    throw "cargo build failed with exit code $LASTEXITCODE"
}

$BinSrc = Join-Path $RootDir "target\release\$Bin.exe"
if (-not (Test-Path -LiteralPath $BinSrc)) {
    throw "Expected binary not found: $BinSrc"
}
$IconSrc = Join-Path $RootDir 'assets\icon.ico'
if (-not (Test-Path -LiteralPath $IconSrc)) {
    throw "Expected icon not found: $IconSrc (see assets/README.md)"
}

Write-Host "==> Staging to $AppDir"
if (Test-Path -LiteralPath $AppDir) {
    Remove-Item -LiteralPath $AppDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path (Join-Path $AppDir 'assets') | Out-Null

Copy-Item -LiteralPath $BinSrc -Destination (Join-Path $AppDir "$Bin.exe") -Force
Copy-Item -LiteralPath $IconSrc -Destination (Join-Path $AppDir 'icon.ico') -Force
Copy-Item -Path (Join-Path $RootDir 'assets\*') -Destination (Join-Path $AppDir 'assets') -Recurse -Force

# The installer shows and installs a license file. Use the repository LICENSE
# when present; otherwise generate an explicit placeholder so the referenced
# path always exists and can be replaced before distribution.
$LicenseSrc = Join-Path $RootDir 'LICENSE'
$LicenseDst = Join-Path $AppDir 'LICENSE.txt'
if (Test-Path -LiteralPath $LicenseSrc) {
    Copy-Item -LiteralPath $LicenseSrc -Destination $LicenseDst -Force
} else {
    Set-Content -LiteralPath $LicenseDst -Encoding UTF8 -Value @(
        'BillFlow. All rights reserved.',
        '',
        'Replace this placeholder with the project license before distributing.'
    )
}

$Zip = Join-Path $ScriptDir 'packaging\BillFlow-portable.zip'
if (Test-Path -LiteralPath $Zip) {
    Remove-Item -LiteralPath $Zip -Force
}
Write-Host "==> Creating portable ZIP: $Zip"
Compress-Archive -Path $AppDir -DestinationPath $Zip

$Iscc = Get-Command -Name iscc -ErrorAction SilentlyContinue
if ($null -ne $Iscc) {
    $Iss = Join-Path $ScriptDir 'packaging\inno-setup.iss'
    Write-Host "==> Building installer with Inno Setup: $Iss"
    & $Iscc.Source $Iss
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup (iscc) failed with exit code $LASTEXITCODE"
    }
} else {
    Write-Host 'iscc (Inno Setup) not found on PATH - skipping installer.'
    Write-Host 'Inno Setup 6 is optional; install it and re-run this script to build the setup exe.'
}

Write-Host '==> Done.'
Write-Host "Staged files: $AppDir"
Write-Host "Portable ZIP: $Zip"
