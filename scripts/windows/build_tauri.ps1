# Build Tauri desktop app with bundled backend sidecar
# Usage: .\scripts\windows\build_tauri.ps1

$ErrorActionPreference = "Stop"

Write-Host "Building Tauri desktop app with bundled backend..." -ForegroundColor Cyan
Write-Host ""

# Step 1: Build backend sidecar with PyInstaller
Write-Host "Step 1: Building backend sidecar..." -ForegroundColor Yellow
uv run pyinstaller ChitChats.spec --clean

if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: PyInstaller build failed" -ForegroundColor Red
    exit 1
}

# Create sidecars directory if it doesn't exist
$sidecarsDir = "frontend\src-tauri\sidecars"
if (-not (Test-Path $sidecarsDir)) {
    New-Item -ItemType Directory -Path $sidecarsDir -Force | Out-Null
}

# Copy the built executable to sidecars
$sourceExe = "dist\ChitChats.exe"
$targetExe = "$sidecarsDir\chitchats-backend-x86_64-pc-windows-msvc.exe"

if (Test-Path $sourceExe) {
    Copy-Item $sourceExe $targetExe -Force
    Write-Host "Backend sidecar built: $targetExe" -ForegroundColor Green
} else {
    Write-Host "Error: PyInstaller output not found at $sourceExe" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Step 2: Build Tauri app
Write-Host "Step 2: Building Tauri app..." -ForegroundColor Yellow
Push-Location frontend
try {
    npm run tauri:build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Tauri build failed" -ForegroundColor Red
        exit 1
    }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Tauri Desktop App Build Complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Installers can be found in:"
Write-Host "  frontend\src-tauri\target\release\bundle\"
Write-Host ""
Write-Host "Available formats:"
Write-Host "  - MSI (Windows Installer)"
Write-Host "  - NSIS (Windows Setup)"
Write-Host ""
