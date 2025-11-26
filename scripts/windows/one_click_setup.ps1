[CmdletBinding()]
param(
    [string]$Password,
    [switch]$SkipDependencies,
    [switch]$StartServers
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

function Write-Step($message) {
    Write-Host "[+] $message" -ForegroundColor Cyan
}

function Ensure-Command($name) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        return $false
    }
    return $true
}

function Install-Uv() {
    if (Ensure-Command 'uv') {
        return
    }
    Write-Step "Installing uv (Python package manager)..."
    powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
}

function Install-Node([string]$nodeMsiUrl = 'https://nodejs.org/dist/v20.14.0/node-v20.14.0-x64.msi') {
    if (Ensure-Command 'node') {
        return
    }

    $wingetAvailable = Ensure-Command 'winget'

    if ($wingetAvailable) {
        Write-Step "Installing Node.js LTS via winget (requires administrator approval)..."
        try {
            winget install --id OpenJS.NodeJS.LTS -e --silent
            return
        }
        catch {
            Write-Warning "winget installation failed. Falling back to direct MSI download..."
        }
    }

    $tempDir = [System.IO.Path]::GetTempPath()
    $msiPath = Join-Path $tempDir 'nodejs-lts-x64.msi'

    Write-Step "Downloading Node.js LTS installer..."
    Invoke-WebRequest -Uri $nodeMsiUrl -OutFile $msiPath -UseBasicParsing

    Write-Step "Installing Node.js LTS silently from MSI..."
    $arguments = @(
        '/i'
        "`"$msiPath`""
        '/qn'
        '/norestart'
    )
    Start-Process -FilePath 'msiexec.exe' -ArgumentList $arguments -Wait
}

function Sync-Dependencies() {
    Write-Step "Installing Python dependencies with uv..."
    uv sync

    Write-Step "Installing frontend dependencies with npm..."
    Push-Location "$repoRoot/frontend"
    npm install
    Pop-Location
}

function Ensure-EnvFile() {
    $envPath = Join-Path $repoRoot '.env'
    if (-not (Test-Path $envPath)) {
        Write-Step "Creating .env from template..."
        Copy-Item (Join-Path $repoRoot '.env.example') $envPath
    }
    return $envPath
}

function Set-EnvValue($path, $key, $value) {
    $existingLines = Get-Content $path -Encoding UTF8
    if (-not $existingLines) {
        $existingLines = @()
    }

    $updatedLines = @()
    $updated = $false

    foreach ($line in $existingLines) {
        if ($line -match "^\s*$key\s*=") {
            $updatedLines += "$key=$value"
            $updated = $true
        } elseif ($line -ne '') {
            $updatedLines += $line
        }
    }

    if (-not $updated) {
        $updatedLines += "$key=$value"
    }

    [System.IO.File]::WriteAllLines($path, $updatedLines)
}

function Generate-PasswordHash($password) {
    if (-not $password) {
        $secure = Read-Host "Enter a password for the app (input hidden)" -AsSecureString
        $password = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        )
    }

    Write-Step "Generating bcrypt hash..."
    $hash = uv run python backend/generate_hash.py --password "$password" --allow-short --output-only
    return $hash.Trim()
}

function Ensure-JwtSecret($envPath) {
    $existing = Select-String -Path $envPath -Pattern '^\s*JWT_SECRET\s*='
    if ($existing) {
        return
    }

    $secret = ([Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N')).Substring(0, 64)
    Write-Step "Adding JWT_SECRET to .env"
    Set-EnvValue -path $envPath -key 'JWT_SECRET' -value $secret
}

function Update-Env($password) {
    $envPath = Ensure-EnvFile
    $hash = Generate-PasswordHash $password
    Write-Step "Writing API_KEY_HASH to .env"
    Set-EnvValue -path $envPath -key 'API_KEY_HASH' -value $hash
    Ensure-JwtSecret $envPath
}

function Start-Servers() {
    Write-Step "Starting backend (FastAPI) in a new window..."
    Start-Process pwsh -ArgumentList "-NoExit", "-Command", "cd `"$repoRoot`"; uv run uvicorn backend/main:app --host 0.0.0.0 --port 8000"

    Write-Step "Starting frontend (Vite) in a new window..."
    Start-Process pwsh -ArgumentList "-NoExit", "-Command", "cd `"$repoRoot`"; cd frontend; npm run dev -- --host 0.0.0.0 --port 5173"

    Write-Step "Servers launched. Open http://localhost:5173 to sign in."
}

Write-Host "=== Claude Code Role Play: Windows One-Click Setup ===" -ForegroundColor Green
Write-Host "This script will install dependencies, set up .env, and optionally start the app." -ForegroundColor Green

if (-not $SkipDependencies) {
    Install-Uv
    Install-Node
    Sync-Dependencies
}

Update-Env $Password

if ($StartServers) {
    Start-Servers
} else {
    Write-Host "Setup complete. Run these commands to start servers:" -ForegroundColor Yellow
    Write-Host "  uv run uvicorn backend/main:app --host 0.0.0.0 --port 8000" -ForegroundColor Yellow
    Write-Host "  cd frontend && npm run dev -- --host 0.0.0.0 --port 5173" -ForegroundColor Yellow
}
