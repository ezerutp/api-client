# Builds the Windows installer: venv -> PyInstaller exe -> Inno Setup installer.
#
#   powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
#
# Produces dist_installer\api-client-setup.exe
# Requires: Python 3.12+ on PATH, and Inno Setup 6 (https://jrsoftware.org/isdl.php,
# or `winget install JRSoftware.InnoSetup`).

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $root

function Find-Iscc {
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($candidate in @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
        "${env:LocalAppData}\Programs\Inno Setup 6\ISCC.exe"
    )) {
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}

$iscc = Find-Iscc
if (-not $iscc) {
    Write-Error "Inno Setup 6 (ISCC.exe) not found. Install it with 'winget install JRSoftware.InnoSetup' or from https://jrsoftware.org/isdl.php, then re-run this script."
}

Write-Host "==> Virtual environment and dependencies" -ForegroundColor Cyan
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
}
$venvPython = ".venv\Scripts\python.exe"
& $venvPython -m pip install --quiet --upgrade pip
& $venvPython -m pip install --quiet --upgrade -r requirements.txt -r requirements-dev.txt pillow

Write-Host "==> Generating assets\api-client.ico" -ForegroundColor Cyan
& $venvPython packaging\windows\make_icon.py

Write-Host "==> Running PyInstaller" -ForegroundColor Cyan
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
& $venvPython -m PyInstaller api_client.spec
if (-not (Test-Path "dist\api-client\api-client.exe")) {
    Write-Error "PyInstaller did not produce dist\api-client\api-client.exe"
}

Write-Host "==> Compiling the installer with Inno Setup" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path dist_installer | Out-Null
$version = & $venvPython -c "from app import APP_VERSION; print(APP_VERSION)"
& $iscc "/DMyAppVersion=$version" "packaging\windows\api-client.iss"
if ($LASTEXITCODE -ne 0) {
    Write-Error "ISCC.exe failed with exit code $LASTEXITCODE"
}

Write-Host ""
Write-Host "Done: dist_installer\api-client-setup.exe" -ForegroundColor Green
