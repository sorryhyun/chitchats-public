<#
.SYNOPSIS
    Build the Claude Code Role Play Windows executable.

.DESCRIPTION
    This script builds a single Windows EXE that includes:
    - The FastAPI backend (bundled with PyInstaller)
    - The React frontend (pre-built and served statically)
    - Default agent configurations
    - All required dependencies

.PARAMETER SkipFrontend
    Skip building the frontend (use existing dist folder)

.PARAMETER Clean
    Clean build artifacts before building

.PARAMETER Sign
    Sign the executable after building (requires certificate)

.PARAMETER CertPath
    Path to the .pfx certificate file (default: .\dev-cert.pfx)

.PARAMETER CertPassword
    Password for the certificate (will prompt if not provided with -Sign)

.EXAMPLE
    .\build_exe.ps1
    .\build_exe.ps1 -SkipFrontend
    .\build_exe.ps1 -Clean
    .\build_exe.ps1 -Sign -CertPath ".\my-cert.pfx" -CertPassword "mypassword"
#>

[CmdletBinding()]
param(
    [switch]$SkipFrontend,
    [switch]$Clean,
    [switch]$Sign,
    [string]$CertPath = ".\dev-cert.pfx",
    [string]$CertPassword
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $scriptDir

Set-Location $repoRoot

function Write-Step($message) {
    Write-Host "`n[+] $message" -ForegroundColor Cyan
}

function Write-Success($message) {
    Write-Host "[OK] $message" -ForegroundColor Green
}

function Write-Error($message) {
    Write-Host "[ERROR] $message" -ForegroundColor Red
}

function Find-SignTool {
    # Check if signtool is already in PATH
    $inPath = Get-Command "signtool" -ErrorAction SilentlyContinue
    if ($inPath) {
        return $inPath.Source
    }

    # Search in Windows SDK directories
    $sdkPath = "${env:ProgramFiles(x86)}\Windows Kits\10\bin"
    if (-not (Test-Path $sdkPath)) {
        return $null
    }

    # Get all version directories, sorted descending (newest first)
    $versions = Get-ChildItem $sdkPath -Directory |
        Where-Object { $_.Name -match '^\d+\.' } |
        Sort-Object Name -Descending

    foreach ($version in $versions) {
        $signtool = Join-Path $version.FullName "x64\signtool.exe"
        if (Test-Path $signtool) {
            return $signtool
        }
    }

    return $null
}

function New-DevCertificate {
    param([string]$CertPath, [string]$Password)

    Write-Step "Creating development code signing certificate..."

    # Create self-signed certificate
    $cert = New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject "CN=Claude Code RP Dev Certificate" `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -NotAfter (Get-Date).AddYears(5)

    # Export to .pfx
    $securePassword = ConvertTo-SecureString -String $Password -Force -AsPlainText
    Export-PfxCertificate -Cert $cert -FilePath $CertPath -Password $securePassword | Out-Null

    # Clean up from certificate store (optional, keeps only the .pfx)
    Remove-Item "Cert:\CurrentUser\My\$($cert.Thumbprint)" -ErrorAction SilentlyContinue

    Write-Success "Certificate created: $CertPath"
    Write-Host "  Note: This is a self-signed certificate for development only." -ForegroundColor Yellow
    Write-Host "  Windows SmartScreen will still warn users about unsigned apps." -ForegroundColor Yellow

    return $true
}

function Sign-Executable {
    param(
        [string]$ExePath,
        [string]$CertPath,
        [string]$Password
    )

    $signtool = Find-SignTool
    if (-not $signtool) {
        Write-Error "signtool.exe not found. Please install Windows SDK."
        Write-Host "  Download from: https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/" -ForegroundColor Yellow
        return $false
    }

    Write-Step "Signing executable with signtool..."
    Write-Host "  SignTool: $signtool" -ForegroundColor DarkGray
    Write-Host "  Certificate: $CertPath" -ForegroundColor DarkGray

    # Sign with SHA256
    $signArgs = @(
        "sign",
        "/f", $CertPath,
        "/p", $Password,
        "/fd", "sha256",
        "/tr", "http://timestamp.digicert.com",
        "/td", "sha256",
        $ExePath
    )

    & $signtool @signArgs

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Executable signed successfully"
        return $true
    } else {
        Write-Error "Signing failed (exit code: $LASTEXITCODE)"
        return $false
    }
}

# Clean previous builds if requested
if ($Clean) {
    Write-Step "Cleaning previous build artifacts..."
    if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
    if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
    Write-Success "Clean complete"
}

# Check prerequisites
Write-Step "Checking prerequisites..."

if (-not (Get-Command "uv" -ErrorAction SilentlyContinue)) {
    Write-Error "uv is not installed. Please install it first: irm https://astral.sh/uv/install.ps1 | iex"
    exit 1
}

if (-not (Get-Command "node" -ErrorAction SilentlyContinue)) {
    Write-Error "Node.js is not installed. Please install it first."
    exit 1
}

Write-Success "Prerequisites OK"

# Build frontend
if (-not $SkipFrontend) {
    Write-Step "Building frontend..."
    Push-Location "frontend"

    # Always ensure dependencies are installed (check for vite specifically)
    if (-not (Test-Path "node_modules/vite")) {
        Write-Step "Installing frontend dependencies..."
        npm install
        if ($LASTEXITCODE -ne 0) {
            Pop-Location
            Write-Error "npm install failed"
            exit 1
        }
    }

    npm run build
    if ($LASTEXITCODE -ne 0) {
        Pop-Location
        Write-Error "Frontend build failed"
        exit 1
    }
    Pop-Location

    if (-not (Test-Path "frontend/dist/index.html")) {
        Write-Error "Frontend build failed - dist/index.html not found"
        exit 1
    }
    Write-Success "Frontend built successfully"
} else {
    Write-Step "Skipping frontend build (using existing dist)"
    if (-not (Test-Path "frontend/dist/index.html")) {
        Write-Error "frontend/dist/index.html not found. Run without -SkipFrontend first."
        exit 1
    }
}

# Install PyInstaller if needed
Write-Step "Ensuring PyInstaller is installed..."
uv pip install pyinstaller --quiet

# Build the executable
Write-Step "Building Windows executable with PyInstaller..."
uv run pyinstaller ClaudeCodeRP.spec --noconfirm

# Check output
$exePath = "dist/ClaudeCodeRP.exe"
if (Test-Path $exePath) {
    $size = (Get-Item $exePath).Length / 1MB
    Write-Success "Build complete!"
    Write-Host ""
    Write-Host "Output: $exePath" -ForegroundColor Yellow
    Write-Host "Size: $([math]::Round($size, 2)) MB" -ForegroundColor Yellow

    # Sign the executable if requested
    if ($Sign) {
        Write-Host ""

        # Check if certificate exists, offer to create if not
        if (-not (Test-Path $CertPath)) {
            Write-Host "Certificate not found: $CertPath" -ForegroundColor Yellow
            $createCert = Read-Host "Create a development certificate? (Y/n)"
            if ($createCert -ne 'n' -and $createCert -ne 'N') {
                if (-not $CertPassword) {
                    $CertPassword = Read-Host "Enter password for new certificate"
                }
                if (-not (New-DevCertificate -CertPath $CertPath -Password $CertPassword)) {
                    Write-Error "Failed to create certificate"
                    exit 1
                }
            } else {
                Write-Host "Skipping code signing." -ForegroundColor Yellow
                $Sign = $false
            }
        }

        # Prompt for password if not provided
        if ($Sign -and -not $CertPassword) {
            $CertPassword = Read-Host "Enter certificate password"
        }

        # Sign the executable
        if ($Sign) {
            if (-not (Sign-Executable -ExePath $exePath -CertPath $CertPath -Password $CertPassword)) {
                Write-Error "Code signing failed"
                exit 1
            }
        }
    }

    Write-Host ""
    Write-Host "To run the application:" -ForegroundColor Cyan
    Write-Host "  1. Copy ClaudeCodeRP.exe to your desired location"
    Write-Host "  2. Create a .env file with API_KEY_HASH and JWT_SECRET"
    Write-Host "  3. Run ClaudeCodeRP.exe"
    Write-Host ""

    if (-not $Sign) {
        Write-Host "Tip: Use -Sign to code sign the executable" -ForegroundColor DarkGray
    }
} else {
    Write-Error "Build failed - executable not found"
    exit 1
}
