<#
.SYNOPSIS
    ChitChats installer for Windows.

.DESCRIPTION
    Downloads the standalone ChitChats.exe (and the agents bundle) from the
    latest GitHub release, installs it under %LOCALAPPDATA%\ChitChats, and adds
    Start Menu / Desktop shortcuts. Re-running upgrades in place and keeps your
    .env, database and agents.

    One-liner:
      irm https://github.com/sorryhyun/chitchats-public/releases/latest/download/install.ps1 | iex

    With options, download first:
      irm <url> -OutFile install.ps1; .\install.ps1 -InstallDir D:\ChitChats

.PARAMETER Version
    Release tag to install. Defaults to the latest published release.

.PARAMETER InstallDir
    Install location. Defaults to $env:LOCALAPPDATA\ChitChats.

.PARAMETER Repo
    Source repository in owner/repo form.

.PARAMETER NoShortcut
    Skip creating Start Menu and Desktop shortcuts.

.PARAMETER NoPath
    Skip adding the install directory to the user PATH.
#>
[CmdletBinding()]
param(
    [string]$Version = 'latest',
    [string]$InstallDir = "$env:LOCALAPPDATA\ChitChats",
    [string]$Repo = 'sorryhyun/chitchats-public',
    [switch]$NoShortcut,
    [switch]$NoPath
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Write-Step { param([string]$Message) Write-Host "`n==> $Message" -ForegroundColor Cyan }
function Write-Info { param([string]$Message) Write-Host "  $Message" }
function Write-Warn { param([string]$Message) Write-Host "  ! $Message" -ForegroundColor Yellow }
function Write-Fail { param([string]$Message) Write-Host "  x $Message" -ForegroundColor Red; exit 1 }

# ------------------------------------------------------------------- release

Write-Step "Resolving release for $Repo"

$headers = @{ 'User-Agent' = 'chitchats-installer' }
try {
    $apiUrl = if ($Version -eq 'latest') {
        "https://api.github.com/repos/$Repo/releases/latest"
    } else {
        "https://api.github.com/repos/$Repo/releases/tags/$Version"
    }
    $release = Invoke-RestMethod -Uri $apiUrl -Headers $headers
} catch {
    Write-Fail "Could not reach the GitHub release API: $($_.Exception.Message)"
}

$tag = $release.tag_name
Write-Info "Version: $tag"

$exeAsset = $release.assets | Where-Object { $_.name -like '*.exe' } | Select-Object -First 1
if (-not $exeAsset) {
    Write-Fail "Release $tag has no .exe asset. Pick another version with -Version, or build from source with 'make build-exe'."
}
$agentsAsset = $release.assets | Where-Object { $_.name -eq 'agents.zip' } | Select-Object -First 1

# ------------------------------------------------------------------ download

$tempDir = Join-Path ([IO.Path]::GetTempPath()) ("chitchats-install-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

try {
    Write-Step "Downloading $($exeAsset.name) ($([math]::Round($exeAsset.size / 1MB, 1)) MB)"
    $exeTemp = Join-Path $tempDir 'ChitChats.exe'
    Invoke-WebRequest -Uri $exeAsset.browser_download_url -OutFile $exeTemp -Headers $headers

    $agentsTemp = $null
    if ($agentsAsset) {
        Write-Step "Downloading agents.zip"
        $agentsTemp = Join-Path $tempDir 'agents.zip'
        Invoke-WebRequest -Uri $agentsAsset.browser_download_url -OutFile $agentsTemp -Headers $headers
    } else {
        # Older releases ship without an agents bundle - take the agents folder
        # out of the tagged source archive instead.
        Write-Step "Release has no agents.zip - fetching agents from the source archive"
        try {
            $agentsTemp = Join-Path $tempDir 'source.zip'
            Invoke-WebRequest -Uri "https://github.com/$Repo/archive/refs/tags/$tag.zip" -OutFile $agentsTemp -Headers $headers
        } catch {
            Write-Warn "Could not fetch default agents: $($_.Exception.Message)"
            $agentsTemp = $null
        }
    }

    # ----------------------------------------------------------------- install

    Write-Step "Installing to $InstallDir"
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null

    $exePath = Join-Path $InstallDir 'ChitChats.exe'
    if (Test-Path $exePath) {
        $running = Get-Process -Name 'ChitChats' -ErrorAction SilentlyContinue
        if ($running) {
            Write-Fail "ChitChats is currently running. Close it and re-run this installer."
        }
    }
    Copy-Item $exeTemp $exePath -Force
    Write-Info "ChitChats.exe"

    # Agents are user data: copy only the ones that aren't there yet, so local
    # edits and hand-made characters survive an upgrade.
    if ($agentsTemp) {
        $agentsDir = Join-Path $InstallDir 'agents'
        $extractDir = Join-Path $tempDir 'agents-extracted'
        Expand-Archive -Path $agentsTemp -DestinationPath $extractDir -Force

        # agents.zip has a top-level agents/; a source archive nests it one
        # level deeper under <repo>-<tag>/agents.
        $source = Get-ChildItem -Path $extractDir -Directory -Recurse -Depth 1 |
            Where-Object { $_.Name -eq 'agents' } | Select-Object -First 1

        if ($source) {
            New-Item -ItemType Directory -Path $agentsDir -Force | Out-Null
            $added = 0
            Get-ChildItem -Path $source.FullName -Force | ForEach-Object {
                $target = Join-Path $agentsDir $_.Name
                if (-not (Test-Path $target)) {
                    Copy-Item $_.FullName $target -Recurse -Force
                    $added++
                }
            }
            Write-Info "agents/ ($added new, existing ones left untouched)"
        } else {
            Write-Warn "No agents folder found in the downloaded archive."
        }
    }

    $tag | Set-Content -Path (Join-Path $InstallDir '.chitchats-version') -Encoding ascii

    # --------------------------------------------------------------- shortcuts

    if (-not $NoShortcut) {
        Write-Step "Creating shortcuts"
        $shell = New-Object -ComObject WScript.Shell
        $targets = @(
            (Join-Path ([Environment]::GetFolderPath('Programs')) 'ChitChats.lnk'),
            (Join-Path ([Environment]::GetFolderPath('Desktop')) 'ChitChats.lnk')
        )
        foreach ($linkPath in $targets) {
            $shortcut = $shell.CreateShortcut($linkPath)
            $shortcut.TargetPath = $exePath
            $shortcut.WorkingDirectory = $InstallDir
            $shortcut.Description = 'ChitChats - multi-agent AI chat rooms'
            $shortcut.Save()
            Write-Info "$(Split-Path $linkPath -Leaf) -> $(Split-Path $linkPath -Parent)"
        }
    }

    # -------------------------------------------------------------------- PATH

    if (-not $NoPath) {
        $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
        if ($userPath -notlike "*$InstallDir*") {
            Write-Step "Adding $InstallDir to your PATH"
            $newPath = if ([string]::IsNullOrEmpty($userPath)) { $InstallDir } else { "$userPath;$InstallDir" }
            [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
            Write-Info "Open a new terminal to pick it up."
        }
    }
} finally {
    Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}

# --------------------------------------------------------------- prerequisites

Write-Step "Checking AI providers"
$hasClaude = [bool](Get-Command claude -ErrorAction SilentlyContinue)
$hasCodex = [bool](Get-Command codex -ErrorAction SilentlyContinue)

if ($hasClaude) { Write-Info "claude CLI found" }
if ($hasCodex) { Write-Info "codex CLI found" }
if (-not $hasClaude -and -not $hasCodex) {
    Write-Warn "Neither the 'claude' nor 'codex' CLI was found."
    Write-Warn "Install at least one before creating a room:"
    Write-Warn "  claude: npm install -g @anthropic-ai/claude-code"
    Write-Warn "  codex:  https://github.com/openai/codex/releases  (then run 'codex login')"
}

Write-Step "Done"
Write-Info "Installed $tag to $InstallDir"
Write-Host ""
Write-Info "Start it from the Start Menu, or run:  $exePath"
Write-Info "It sets up your password on first launch, then opens the app in your browser."
Write-Host ""
