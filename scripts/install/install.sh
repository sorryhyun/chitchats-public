#!/usr/bin/env bash
#
# ChitChats installer for macOS / Linux / WSL.
#
#   curl -fsSL https://github.com/sorryhyun/chitchats-public/releases/latest/download/install.sh | bash
#
# Downloads the latest GitHub release, installs dependencies and drops a
# `chitchats` launcher into ~/.local/bin. Re-running it upgrades in place and
# keeps your .env, database and agents.
#
set -euo pipefail

REPO="${CHITCHATS_REPO:-sorryhyun/chitchats-public}"
INSTALL_DIR="${CHITCHATS_HOME:-$HOME/.chitchats}"
BIN_DIR="${CHITCHATS_BIN_DIR:-$HOME/.local/bin}"
VERSION="latest"
INSTALL_UV=1
CREATE_ENV=1
CREATE_LAUNCHER=1

# User data that survives an upgrade. Agents are merged separately.
PRESERVE=(.env .env.bak chitchats.db generated_images sounds work_dir)
# Expensive to rebuild, so carried over instead of re-downloaded.
CARRY_OVER=(.venv frontend/node_modules)

usage() {
    cat <<'EOF'
ChitChats installer

Usage: install.sh [options]

Options:
  --dir <path>      Install location (default: ~/.chitchats, or $CHITCHATS_HOME)
  --version <tag>   Release tag to install (default: latest)
  --repo <owner/repo>
                    Source repository (default: sorryhyun/chitchats-public)
  --bin-dir <path>  Where to put the `chitchats` launcher (default: ~/.local/bin)
  --no-uv           Fail instead of installing uv when it is missing
  --no-env          Skip the interactive .env setup
  --no-launcher     Skip creating the `chitchats` launcher
  -h, --help        Show this help

Environment: CHITCHATS_HOME, CHITCHATS_BIN_DIR, CHITCHATS_REPO
EOF
}

log()  { printf '  %s\n' "$*"; }
step() { printf '\n\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33m  ! %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[31m  x %s\033[0m\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
    case "$1" in
        --dir)       INSTALL_DIR="${2:?--dir needs a path}"; shift 2 ;;
        --version)   VERSION="${2:?--version needs a tag}"; shift 2 ;;
        --repo)      REPO="${2:?--repo needs owner/repo}"; shift 2 ;;
        --bin-dir)   BIN_DIR="${2:?--bin-dir needs a path}"; shift 2 ;;
        --no-uv)     INSTALL_UV=0; shift ;;
        --no-env)    CREATE_ENV=0; shift ;;
        --no-launcher) CREATE_LAUNCHER=0; shift ;;
        -h|--help)   usage; exit 0 ;;
        *)           die "Unknown option: $1 (try --help)" ;;
    esac
done

# ---------------------------------------------------------------- prerequisites

need() { command -v "$1" >/dev/null 2>&1; }

step "Checking prerequisites"

need curl || die "curl is required."
need tar  || die "tar is required."

case "$(uname -s)" in
    Darwin) PLATFORM="macOS" ;;
    Linux)  PLATFORM="Linux"; grep -qi microsoft /proc/version 2>/dev/null && PLATFORM="WSL" ;;
    *)      die "Unsupported platform: $(uname -s). On Windows use scripts/install/install.ps1." ;;
esac
log "Platform: $PLATFORM"

if ! need node || ! need npm; then
    die "Node.js (with npm) is required for the frontend. Install Node 20+ and re-run.
      macOS:        brew install node
      Debian/Ubuntu: curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs"
fi
log "Node: $(node --version)"

if ! need uv; then
    [ "$INSTALL_UV" -eq 1 ] || die "uv is required but --no-uv was passed. See https://docs.astral.sh/uv/"
    log "uv not found - installing from https://astral.sh/uv/install.sh"
    curl -fsSL https://astral.sh/uv/install.sh | sh
    # The installer drops uv in one of these; pick it up for this session.
    for candidate in "$HOME/.local/bin" "$HOME/.cargo/bin"; do
        [ -x "$candidate/uv" ] && PATH="$candidate:$PATH"
    done
    need uv || die "uv installed but not on PATH. Open a new shell and re-run this installer."
fi
log "uv: $(uv --version)"

if ! need claude && ! need codex; then
    warn "Neither the 'claude' nor 'codex' CLI was found."
    warn "Install at least one before creating a room:"
    warn "  claude: npm install -g @anthropic-ai/claude-code"
    warn "  codex:  https://github.com/openai/codex  (then run 'codex login')"
fi

# ------------------------------------------------------------------- download

step "Resolving release"

if [ "$VERSION" = "latest" ]; then
    # Follow the /releases/latest redirect - no API token, no rate limit.
    resolved_url="$(curl -fsSLI -o /dev/null -w '%{url_effective}' \
        "https://github.com/$REPO/releases/latest" 2>/dev/null || true)"
    case "$resolved_url" in
        */releases/tag/*) VERSION="${resolved_url##*/tag/}" ;;
        *)
            warn "No published release found for $REPO - falling back to the master branch."
            VERSION="master"
            ;;
    esac
fi

if [ "$VERSION" = "master" ] || [ "$VERSION" = "main" ]; then
    TARBALL_URL="https://github.com/$REPO/archive/refs/heads/$VERSION.tar.gz"
else
    TARBALL_URL="https://github.com/$REPO/archive/refs/tags/$VERSION.tar.gz"
fi
log "Version: $VERSION"

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/chitchats-install.XXXXXX")"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

STAGE="$TMP_DIR/stage"
mkdir -p "$STAGE"

step "Downloading $TARBALL_URL"
curl -fsSL "$TARBALL_URL" | tar -xz --strip-components=1 -C "$STAGE" \
    || die "Download failed. Check the version tag and your network."
[ -f "$STAGE/pyproject.toml" ] || die "Downloaded archive does not look like ChitChats."
printf '%s\n' "$VERSION" > "$STAGE/.chitchats-version"

# --------------------------------------------------------------------- install

step "Installing to $INSTALL_DIR"

if [ -d "$INSTALL_DIR" ]; then
    log "Existing install found - keeping your data"

    for item in "${PRESERVE[@]}"; do
        if [ -e "$INSTALL_DIR/$item" ]; then
            rm -rf "${STAGE:?}/$item"
            cp -R "$INSTALL_DIR/$item" "$STAGE/$item"
            log "kept $item"
        fi
    done

    # Agents: user edits to shipped agents win, user-created agents are kept,
    # and agents new in this release still land because the stage has them.
    if [ -d "$INSTALL_DIR/agents" ]; then
        mkdir -p "$STAGE/agents"
        cp -R "$INSTALL_DIR/agents/." "$STAGE/agents/"
        log "merged agents/"
    fi

    for item in "${CARRY_OVER[@]}"; do
        if [ -d "$INSTALL_DIR/$item" ] && [ ! -e "$STAGE/$item" ]; then
            mkdir -p "$(dirname "$STAGE/$item")"
            mv "$INSTALL_DIR/$item" "$STAGE/$item"
        fi
    done

    BACKUP_DIR="$INSTALL_DIR.old.$$"
    mv "$INSTALL_DIR" "$BACKUP_DIR"
    mkdir -p "$(dirname "$INSTALL_DIR")"
    mv "$STAGE" "$INSTALL_DIR"
    rm -rf "$BACKUP_DIR"
else
    mkdir -p "$(dirname "$INSTALL_DIR")"
    mv "$STAGE" "$INSTALL_DIR"
fi

step "Installing backend dependencies (uv sync)"
(cd "$INSTALL_DIR" && uv sync)

step "Installing frontend dependencies (npm install)"
(cd "$INSTALL_DIR/frontend" && npm install --no-fund --no-audit)

# ------------------------------------------------------------------ .env setup

if [ "$CREATE_ENV" -eq 1 ] && [ ! -f "$INSTALL_DIR/.env" ]; then
    step "Configuring .env"
    # `curl | bash` leaves stdin pointing at the pipe, so borrow the terminal.
    if [ -t 0 ]; then
        (cd "$INSTALL_DIR" && uv run python scripts/setup/create_env.py) || warn ".env setup did not complete."
    elif [ -r /dev/tty ]; then
        (cd "$INSTALL_DIR" && uv run python scripts/setup/create_env.py < /dev/tty) || warn ".env setup did not complete."
    else
        warn "No terminal available - skipping .env setup."
        warn "Run it later with:  chitchats env"
    fi
fi

# ------------------------------------------------------------------- launcher

if [ "$CREATE_LAUNCHER" -eq 1 ]; then
    step "Installing launcher to $BIN_DIR/chitchats"
    mkdir -p "$BIN_DIR"
    cat > "$BIN_DIR/chitchats" <<EOF
#!/usr/bin/env bash
# ChitChats launcher - generated by the installer.
set -euo pipefail
CHITCHATS_HOME="\${CHITCHATS_HOME:-$INSTALL_DIR}"
CHITCHATS_REPO="\${CHITCHATS_REPO:-$REPO}"
INSTALLER_URL="https://github.com/\$CHITCHATS_REPO/releases/latest/download/install.sh"

[ -d "\$CHITCHATS_HOME" ] || { echo "ChitChats is not installed at \$CHITCHATS_HOME" >&2; exit 1; }
cd "\$CHITCHATS_HOME"

case "\${1:-start}" in
    start)   exec make dev ;;
    sqlite)  exec make dev-sqlite ;;
    voice)   exec make dev-voice ;;
    env)     exec uv run python scripts/setup/create_env.py ;;
    stop)    exec make stop ;;
    dir)     echo "\$CHITCHATS_HOME" ;;
    version) cat .chitchats-version 2>/dev/null || echo "unknown" ;;
    update)  exec bash -c "curl -fsSL '\$INSTALLER_URL' | bash -s -- --dir '\$CHITCHATS_HOME'" ;;
    -h|--help|help)
        cat <<'USAGE'
chitchats [command]

  start     Run backend + frontend (default)
  sqlite    Run with SQLite instead of PostgreSQL
  voice     Run backend + frontend + voice TTS server
  env       Re-create the .env file
  stop      Stop running servers
  update    Re-run the installer to upgrade in place
  dir       Print the install directory
  version   Print the installed version
USAGE
        ;;
    *) echo "Unknown command: \$1 (try 'chitchats help')" >&2; exit 1 ;;
esac
EOF
    chmod +x "$BIN_DIR/chitchats"
fi

# ---------------------------------------------------------------------- done

step "Done"
log "Installed $VERSION to $INSTALL_DIR"
echo

case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *)
        if [ "$CREATE_LAUNCHER" -eq 1 ]; then
            warn "$BIN_DIR is not on your PATH. Add this to your shell profile:"
            warn "  export PATH=\"$BIN_DIR:\$PATH\""
        fi
        ;;
esac

if [ "$CREATE_LAUNCHER" -eq 1 ]; then
    log "Start it with:   chitchats"
else
    log "Start it with:   cd $INSTALL_DIR && make dev"
fi
log "Then open:       http://localhost:5173"
echo
