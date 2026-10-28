# Build the dashboard (if needed) and serve API + UI on one port.
# Usage:  .\scripts\serve.ps1 [-Port 8000] [-Rebuild]
param(
    [int]$Port = 8000,
    [switch]$Rebuild
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$dist = Join-Path $root "apps\web\dist\index.html"
if ($Rebuild -or -not (Test-Path $dist)) {
    Write-Host "Building dashboard..." -ForegroundColor Cyan
    Push-Location (Join-Path $root "apps\web")
    if (-not (Test-Path "node_modules")) { npm install }
    npm run build
    Pop-Location
}

Write-Host "FieldWizard running at http://127.0.0.1:$Port" -ForegroundColor Green
python -m uvicorn apps.api.main:app --host 127.0.0.1 --port $Port
