# Windows development script - runs backend + frontend with clean Ctrl+C handling
# Usage: .\scripts\windows\dev.ps1
#        .\scripts\windows\dev.ps1 -SQLite

param(
    [switch]$SQLite
)

$ErrorActionPreference = "Stop"

# Codex skills folder path
$codexSkillsPath = Join-Path $env:USERPROFILE ".codex\skills"
$skillsWasLocked = $false

function Lock-CodexSkills {
    # Remove ALL permissions from ~/.codex/skills (equivalent to chmod 000)
    if (Test-Path $codexSkillsPath) {
        try {
            # Save current ACL for restoration
            $script:savedAcl = Get-Acl $codexSkillsPath

            # Create new ACL with no permissions
            $acl = Get-Acl $codexSkillsPath
            $acl.SetAccessRuleProtection($true, $false)  # Remove inheritance, don't copy
            $acl.Access | ForEach-Object { $acl.RemoveAccessRule($_) | Out-Null }
            Set-Acl $codexSkillsPath $acl

            $script:skillsWasLocked = $true
            Write-Host "Locked Codex skills folder" -ForegroundColor DarkGray
        } catch {
            Write-Host "Warning: Could not lock Codex skills folder: $_" -ForegroundColor Yellow
        }
    }
}

function Unlock-CodexSkills {
    # Restore original ACL to ~/.codex/skills
    if ($script:skillsWasLocked -and $script:savedAcl -and (Test-Path $codexSkillsPath)) {
        try {
            Set-Acl $codexSkillsPath $script:savedAcl
            Write-Host "Unlocked Codex skills folder" -ForegroundColor DarkGray
        } catch {
            Write-Host "Warning: Could not unlock Codex skills folder: $_" -ForegroundColor Yellow
        }
    }
}

Write-Host "Starting backend and frontend..." -ForegroundColor Cyan
Write-Host "Backend will run on http://localhost:8001" -ForegroundColor Green
Write-Host "Frontend will run on http://localhost:5173" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop all servers" -ForegroundColor Yellow
Write-Host ""

$backendProcess = $null
$frontendProcess = $null

try {
    # Lock Codex skills folder to prevent unnecessary prompts
    Lock-CodexSkills

    # Set SQLite env if requested
    if ($SQLite) {
        $env:USE_SQLITE = "true"
        Write-Host "Using SQLite database" -ForegroundColor Magenta
    }

    # Start backend process - main.py sets ProactorEventLoop policy at import time
    # Note: Running WITHOUT --reload because reload spawns subprocesses that don't inherit the policy
    $backendProcess = Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c", "uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001" `
        -WorkingDirectory "$PWD\backend" `
        -PassThru -NoNewWindow

    Write-Host "Backend started (PID: $($backendProcess.Id))" -ForegroundColor DarkGray

    # Give backend a moment to start
    Start-Sleep -Seconds 2

    # Start frontend process (use cmd /c because npm is a .cmd file on Windows)
    $frontendProcess = Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c", "npm", "run", "dev" `
        -WorkingDirectory "$PWD\frontend" `
        -PassThru -NoNewWindow

    Write-Host "Frontend started (PID: $($frontendProcess.Id))" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "Both servers running. Press Ctrl+C to stop." -ForegroundColor Green

    # Wait for either process to exit
    while ($true) {
        if ($backendProcess.HasExited) {
            Write-Host "`nBackend process exited with code: $($backendProcess.ExitCode)" -ForegroundColor Red
            break
        }
        if ($frontendProcess.HasExited) {
            Write-Host "`nFrontend process exited with code: $($frontendProcess.ExitCode)" -ForegroundColor Red
            break
        }
        Start-Sleep -Milliseconds 500
    }
}
finally {
    Write-Host "`nStopping servers..." -ForegroundColor Yellow

    # Unlock Codex skills folder
    Unlock-CodexSkills

    # Stop backend cmd process
    if ($backendProcess -and -not $backendProcess.HasExited) {
        Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
    }

    # Stop frontend cmd process
    if ($frontendProcess -and -not $frontendProcess.HasExited) {
        Stop-Process -Id $frontendProcess.Id -Force -ErrorAction SilentlyContinue
    }

    # Kill child processes that may still be running (cmd.exe doesn't kill children)
    # Kill uvicorn/python processes running our app
    Get-Process -Name "python" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*uvicorn*main:app*" } |
        Stop-Process -Force -ErrorAction SilentlyContinue

    # Kill node/vite processes
    Get-Process -Name "node" -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowTitle -eq "" } |
        Stop-Process -Force -ErrorAction SilentlyContinue

    Write-Host "Servers stopped." -ForegroundColor Green
}
