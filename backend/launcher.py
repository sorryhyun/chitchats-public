"""
Launcher script for the packaged ChitChats application.

This is the entry point for the PyInstaller bundle. It:
1. Sets up paths for bundled resources
2. Runs first-time setup wizard if needed (console mode only)
3. Opens the default web browser automatically
4. Starts the uvicorn server

When run as a Tauri sidecar (legacy, archived):
- Setup is handled by Tauri's GUI wizard
- Browser is not opened (Tauri provides the webview)
- Graceful shutdown on SIGTERM
"""

import getpass
import os
import secrets
import signal
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Global flag to prevent duplicate browser opens
_browser_opened = False

# Default and fallback ports
DEFAULT_PORT = 8000
FALLBACK_PORTS = [8001, 8080, 8888, 9000]

# Codex binary download URL for Windows
CODEX_DOWNLOAD_URL = "https://github.com/openai/codex/releases/download/rust-v0.98.0/codex-x86_64-pc-windows-msvc.exe"
CODEX_BINARY_NAME = "codex-x86_64-pc-windows-msvc.exe"


def find_available_port(preferred_port: int = DEFAULT_PORT) -> int:
    """Find an available port, starting with the preferred port.

    Args:
        preferred_port: The port to try first.

    Returns:
        An available port number.
    """
    ports_to_try = [preferred_port] + [p for p in FALLBACK_PORTS if p != preferred_port]

    for port in ports_to_try:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except (OSError, PermissionError):
            continue

    # Last resort: let OS assign a port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get_base_path() -> Path:
    """Get the base path for resources (handles both dev and bundled modes)."""
    if getattr(sys, "frozen", False):
        # Running as PyInstaller bundle
        return Path(sys._MEIPASS)
    else:
        # Running in development
        return Path(__file__).parent.parent


def get_work_dir() -> Path:
    """Get the working directory for user data (.env, agents, etc.)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).parent.parent


def setup_paths():
    """Set up Python paths for imports."""
    base_path = get_base_path()

    # Add backend to Python path
    backend_path = base_path / "backend"
    if backend_path.exists():
        sys.path.insert(0, str(backend_path))
    else:
        # In dev mode, backend is current directory's parent
        sys.path.insert(0, str(Path(__file__).parent))

    # Set working directory
    work_dir = get_work_dir()
    os.chdir(work_dir)


def copy_default_agents():
    """Extract default agents from zip if they don't exist.

    In bundled mode, agents are distributed as agents.zip alongside the exe
    rather than being bundled inside the exe. This reduces exe size and allows
    users to update agents independently.
    """
    if not getattr(sys, "frozen", False):
        return

    work_dir = get_work_dir()
    agents_dest = work_dir / "agents"
    agents_zip = work_dir / "agents.zip"

    if agents_dest.exists():
        return  # Already extracted

    if agents_zip.exists():
        import zipfile

        print("에이전트를 압축 해제하는 중...")
        with zipfile.ZipFile(agents_zip, "r") as zf:
            zf.extractall(work_dir)
        print(f"에이전트를 압축 해제했습니다: {agents_dest}")
    else:
        # Fallback: check for bundled agents (legacy support)
        base_path = get_base_path()
        agents_src = base_path / "agents"
        if agents_src.exists():
            import shutil

            shutil.copytree(agents_src, agents_dest)
            print(f"기본 에이전트를 복사했습니다: {agents_dest}")
        else:
            print(f"경고: agents.zip을 찾을 수 없습니다: {agents_zip}")
            print("에이전트 폴더를 수동으로 생성해주세요.")


def download_codex_binary():
    """Download Codex CLI binary for Windows if not already present.

    Only runs when packaged as a frozen exe on Windows.
    Downloads the binary next to ChitChats.exe so that
    windows_support.get_bundled_codex_path() can find it.
    """
    if not getattr(sys, "frozen", False):
        return

    if sys.platform != "win32":
        return

    work_dir = get_work_dir()
    codex_path = work_dir / CODEX_BINARY_NAME

    if codex_path.exists():
        return  # Already downloaded

    print("Codex CLI를 다운로드하는 중...")
    print(f"URL: {CODEX_DOWNLOAD_URL}")

    try:
        import urllib.request

        tmp_path = codex_path.with_suffix(".tmp")

        def _progress_hook(block_num, block_size, total_size):
            if total_size > 0:
                downloaded = block_num * block_size
                pct = min(100, downloaded * 100 // total_size)
                mb_done = downloaded / (1024 * 1024)
                mb_total = total_size / (1024 * 1024)
                print(f"\r  다운로드 중... {pct}% ({mb_done:.1f}/{mb_total:.1f} MB)", end="", flush=True)

        urllib.request.urlretrieve(CODEX_DOWNLOAD_URL, tmp_path, _progress_hook)
        print()  # newline after progress

        tmp_path.rename(codex_path)
        print(f"Codex CLI 다운로드 완료: {codex_path}")
    except Exception as e:
        print(f"\n경고: Codex CLI 다운로드 실패: {e}")
        print("Codex 기능을 사용하려면 수동으로 다운로드해주세요.")
        # Clean up partial download
        tmp_path = codex_path.with_suffix(".tmp")
        if tmp_path.exists():
            tmp_path.unlink()


def is_env_configured(env_file: Path) -> bool:
    """Check if .env file has valid configuration."""
    if not env_file.exists():
        return False

    content = env_file.read_text(encoding="utf-8")

    # Check for placeholder values that indicate unconfigured state
    has_valid_hash = "API_KEY_HASH=" in content and "example_hash" not in content and "paste_your" not in content
    has_valid_jwt = "JWT_SECRET=" in content and "your-random-secret" not in content

    return has_valid_hash and has_valid_jwt


def run_first_time_setup():
    """Run interactive first-time setup wizard."""
    import bcrypt

    print("=" * 60)
    print("ChitChats - 초기 설정")
    print("=" * 60)
    print()
    print("환영합니다! 애플리케이션을 설정해주세요.")
    print()

    # Get password from user
    while True:
        password = getpass.getpass("비밀번호를 입력하세요: ")
        if len(password) < 4:
            print("비밀번호는 최소 4자 이상이어야 합니다. 다시 시도해주세요.")
            continue

        password_confirm = getpass.getpass("비밀번호 확인: ")
        if password != password_confirm:
            print("비밀번호가 일치하지 않습니다. 다시 시도해주세요.")
            continue

        if len(password) < 8:
            print("\n참고: 비밀번호가 8자 미만입니다.")
            proceed = input("계속하시겠습니까? (Y/n): ").strip().lower()
            if proceed == "n":
                continue

        break

    # Generate password hash
    salt = bcrypt.gensalt()
    password_hash = bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    # Generate JWT secret
    jwt_secret = secrets.token_hex(32)

    # Get user name (optional)
    user_name = input("\n표시할 이름을 입력하세요 (기본값: User): ").strip()
    if not user_name:
        user_name = "User"

    return {
        "password_hash": password_hash,
        "jwt_secret": jwt_secret,
        "user_name": user_name,
    }


def create_env_file(env_file: Path, config: dict):
    """Create .env file with user configuration."""
    env_content = f"""USER_NAME={config["user_name"]}
CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK=true

# Authentication (auto-generated by setup wizard)
API_KEY_HASH={config["password_hash"]}

# JWT Secret (auto-generated)
JWT_SECRET={config["jwt_secret"]}

# Set to "true" for debug logging
DEBUG_AGENTS=false
"""

    env_file.write_text(env_content, encoding="utf-8")
    print(f"\n설정이 저장되었습니다: {env_file}")


def setup_environment() -> bool:
    """Set up environment for the bundled application. Returns True if setup was run."""
    work_dir = get_work_dir()
    env_file = work_dir / ".env"

    # Copy default agents and download Codex binary
    copy_default_agents()
    download_codex_binary()

    # Check if setup is needed
    if is_env_configured(env_file):
        return False

    # Run first-time setup
    try:
        config = run_first_time_setup()
        create_env_file(env_file, config)
        print()
        print("=" * 60)
        print("설정 완료! 애플리케이션을 시작합니다...")
        print("=" * 60)
        print()
        return True
    except KeyboardInterrupt:
        print("\n\n설정이 취소되었습니다.")
        sys.exit(0)


def is_tauri_sidecar() -> bool:
    """Check if running as a Tauri sidecar."""
    # Tauri sets this when spawning sidecars, or check parent process
    return os.environ.get("TAURI_SIDECAR") == "1" or "--sidecar" in sys.argv


def open_browser_delayed(url: str, delay: float = 1.5):
    """Open browser after a delay to allow server to start.

    Uses a global flag to prevent duplicate browser opens which can happen
    when Claude SDK or Codex subprocess triggers browser behavior on Windows.
    """
    global _browser_opened

    if _browser_opened:
        return

    _browser_opened = True

    def _open():
        time.sleep(delay)
        # Double-check flag in case of race condition
        webbrowser.open(url)

    thread = threading.Thread(target=_open, daemon=True)
    thread.start()


def run_mcp_server(server_type: str) -> None:
    """Run in MCP server mode (for self-spawn from bundled exe).

    This is called when the exe is invoked with --mcp-server argument,
    allowing Codex to spawn this exe as an MCP server subprocess.

    Args:
        server_type: Either "action", "guidelines", or "etc"
    """
    import asyncio

    # Set up paths for imports
    setup_paths()

    if server_type == "action":
        from mcp_servers.action_server import main as server_main
    elif server_type == "guidelines":
        from mcp_servers.guidelines_server import main as server_main
    elif server_type == "etc":
        from mcp_servers.etc_server import main as server_main
    else:
        print(f"Unknown MCP server type: {server_type}", file=sys.stderr)
        print("Valid types: action, guidelines, etc", file=sys.stderr)
        sys.exit(1)

    # Run the MCP server (async main)
    asyncio.run(server_main())


def main():
    """Main entry point."""
    # Check for MCP server mode first (before any other setup)
    # This allows the bundled exe to be spawned as an MCP server subprocess
    if "--mcp-server" in sys.argv:
        try:
            idx = sys.argv.index("--mcp-server")
            server_type = sys.argv[idx + 1]
        except (IndexError, ValueError):
            print("Usage: ChitChats.exe --mcp-server <action|guidelines>", file=sys.stderr)
            sys.exit(1)
        run_mcp_server(server_type)
        return  # MCP server handles its own exit

    # Set up paths first
    setup_paths()

    # Set up signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        print("\n서버를 종료합니다...")
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Check if running as Tauri sidecar
    sidecar_mode = is_tauri_sidecar()

    # Run environment setup (including first-time wizard if needed)
    # In sidecar mode, Tauri handles setup via GUI
    if not sidecar_mode:
        setup_environment()

    # Import uvicorn and app after setting up paths
    import uvicorn

    # Find an available port
    port = find_available_port(DEFAULT_PORT)

    print("=" * 60)
    print("ChitChats")
    print("=" * 60)
    print()
    if port != DEFAULT_PORT:
        print(f"포트 {DEFAULT_PORT}을(를) 사용할 수 없어 포트 {port}을(를) 사용합니다.")
    print(f"서버 시작 중: http://localhost:{port}")
    if not sidecar_mode:
        print("서버를 중지하려면 Ctrl+C를 누르세요")
        print()
        # Open browser automatically (standalone mode only)
        open_browser_delayed(f"http://localhost:{port}")
        print("브라우저를 자동으로 엽니다...")
    print()

    # Import the app directly instead of using string path
    # This works better with PyInstaller bundling
    from main import app

    # Run the server with the app object directly
    # Use 127.0.0.1 instead of 0.0.0.0 to avoid Windows permission issues
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
