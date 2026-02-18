<#
.SYNOPSIS
    Build the ChitChats Windows executable.

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

# Handle UNC paths (common when running from WSL)
# CMD.exe doesn't support UNC paths as current directory, so we track this for special handling
$isUncPath = $repoRoot -match '^\\\\'
if ($isUncPath) {
    Write-Host "[*] UNC path detected: $repoRoot" -ForegroundColor Yellow
    Write-Host "[*] Using cmd.exe pushd wrapper for npm commands" -ForegroundColor Yellow
}

# Helper function to run commands - uses pushd wrapper for UNC paths
function Invoke-BuildCommand {
    param(
        [string]$Command,
        [string]$WorkingDir = $script:repoRoot
    )

    if ($script:isUncPath) {
        # Start cmd.exe from C:\ first to avoid UNC path error, then pushd to map UNC path
        # pushd automatically creates a temporary drive letter (like Z:) for UNC paths
        $cmdScript = "cd /d C:\ && pushd `"$WorkingDir`" && $Command && exit"
        & cmd /c $cmdScript
        return $LASTEXITCODE
    } else {
        Push-Location $WorkingDir
        try {
            # Run command via cmd.exe to get reliable exit code
            # The 'call' ensures proper exit code propagation for batch/npm commands
            & cmd /c "call $Command"
            return $LASTEXITCODE
        } finally {
            Pop-Location
        }
    }
}

# Set location - for UNC paths, stay in a safe directory and use Invoke-BuildCommand for all operations
if (-not $isUncPath) {
    Set-Location $repoRoot
}

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
        -Subject "CN=ChitChats Dev Certificate" `
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
    $distPath = Join-Path $repoRoot "dist"
    $buildPath = Join-Path $repoRoot "build"
    if (Test-Path $distPath) { Remove-Item -Recurse -Force $distPath }
    if (Test-Path $buildPath) { Remove-Item -Recurse -Force $buildPath }
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
    $frontendDir = Join-Path $repoRoot "frontend"

    # Always ensure dependencies are installed (check for vite specifically)
    if (-not (Test-Path (Join-Path $frontendDir "node_modules/vite"))) {
        Write-Step "Installing frontend dependencies..."
        Push-Location $frontendDir
        npm install
        Pop-Location
    }

    # Run npm build - exit code is unreliable in PowerShell, so we check output file instead
    Push-Location $frontendDir
    npm run build
    Pop-Location

    # Verify build succeeded by checking output file existence
    $frontendIndex = Join-Path $repoRoot "frontend/dist/index.html"
    if (-not (Test-Path $frontendIndex)) {
        Write-Error "Frontend build failed - dist/index.html not found"
        exit 1
    }
    Write-Success "Frontend built successfully"
} else {
    Write-Step "Skipping frontend build (using existing dist)"
    $frontendIndex = Join-Path $repoRoot "frontend/dist/index.html"
    if (-not (Test-Path $frontendIndex)) {
        Write-Error "frontend/dist/index.html not found. Run without -SkipFrontend first."
        exit 1
    }
}

# Install PyInstaller if needed
Write-Step "Ensuring PyInstaller is installed..."
$exitCode = Invoke-BuildCommand -Command "uv pip install pyinstaller --quiet"

# Helper function to finalize a built exe (checksum, sign, report)
function Complete-ExeBuild {
    param(
        [string]$ExePath,
        [string]$ExeName
    )

    if (-not (Test-Path $ExePath)) {
        Write-Error "Build failed - $ExeName not found"
        return $false
    }

    $size = (Get-Item $ExePath).Length / 1MB
    Write-Success "$ExeName build complete!"
    Write-Host ""
    Write-Host "Output: $ExePath" -ForegroundColor Yellow
    Write-Host "Size: $([math]::Round($size, 2)) MB" -ForegroundColor Yellow

    # Generate checksum (compatible with all PowerShell versions)
    $sha256hash = [System.Security.Cryptography.SHA256]::Create()
    $fileStream = [System.IO.File]::OpenRead($ExePath)
    try {
        $hashBytes = $sha256hash.ComputeHash($fileStream)
        $hashString = [BitConverter]::ToString($hashBytes) -replace '-', ''
    } finally {
        $fileStream.Close()
        $sha256hash.Dispose()
    }
    Write-Host "SHA256: $hashString" -ForegroundColor Yellow

    # Save checksum to file
    $checksumFile = "$ExePath.sha256"
    "$hashString  $ExeName" | Out-File -FilePath $checksumFile -Encoding ASCII
    Write-Host "Checksum saved to: $checksumFile" -ForegroundColor Yellow

    # Sign the executable if requested
    if ($script:Sign) {
        Write-Host ""

        # Check if certificate exists, offer to create if not (only prompt once)
        if (-not (Test-Path $script:CertPath)) {
            Write-Host "Certificate not found: $($script:CertPath)" -ForegroundColor Yellow
            $createCert = Read-Host "Create a development certificate? (Y/n)"
            if ($createCert -ne 'n' -and $createCert -ne 'N') {
                if (-not $script:CertPassword) {
                    $script:CertPassword = Read-Host "Enter password for new certificate"
                }
                if (-not (New-DevCertificate -CertPath $script:CertPath -Password $script:CertPassword)) {
                    Write-Error "Failed to create certificate"
                    return $false
                }
            } else {
                Write-Host "Skipping code signing." -ForegroundColor Yellow
                $script:Sign = $false
            }
        }

        # Prompt for password if not provided
        if ($script:Sign -and -not $script:CertPassword) {
            $script:CertPassword = Read-Host "Enter certificate password"
        }

        # Sign the executable
        if ($script:Sign) {
            if (-not (Sign-Executable -ExePath $ExePath -CertPath $script:CertPath -Password $script:CertPassword)) {
                Write-Error "Code signing failed for $ExeName"
                return $false
            }
        }
    }

    return $true
}

# Build the main executable (Opus mode)
Write-Step "Building ChitChats.exe (Opus mode) with PyInstaller..."
$exitCode = Invoke-BuildCommand -Command "uv run pyinstaller ChitChats.spec --noconfirm"

$exePath = Join-Path $repoRoot "dist/ChitChats.exe"
if (-not (Complete-ExeBuild -ExePath $exePath -ExeName "ChitChats.exe")) {
    exit 1
}

# Build the Haiku executable (Sonnet 4.6 mode)
Write-Step "Building ChitChats-Haiku.exe (Sonnet 4.6 mode) with PyInstaller..."
$exitCode = Invoke-BuildCommand -Command "uv run pyinstaller ChitChats-Haiku.spec --noconfirm"

$haikuExePath = Join-Path $repoRoot "dist/ChitChats-Haiku.exe"
if (-not (Complete-ExeBuild -ExePath $haikuExePath -ExeName "ChitChats-Haiku.exe")) {
    exit 1
}

# Summary
Write-Host ""
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "Build Summary" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""
Write-Host "  ChitChats.exe       - Uses Claude Opus 4.6 (default)" -ForegroundColor Yellow
Write-Host "  ChitChats-Haiku.exe - Uses Claude Sonnet 4.6 (USE_HAIKU=true)" -ForegroundColor Yellow
Write-Host ""
Write-Host "To run the application:" -ForegroundColor Cyan
Write-Host "  1. Copy the desired .exe to your location"
Write-Host "  2. Create a .env file with API_KEY_HASH and JWT_SECRET"
Write-Host "  3. Run the .exe"
Write-Host ""

if (-not $Sign) {
    Write-Host "Tip: Use -Sign to code sign the executables" -ForegroundColor DarkGray
}
