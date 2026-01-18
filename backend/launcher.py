"""
Launcher script for the packaged Claude Code Role Play application.

This is the entry point for the PyInstaller bundle. It:
1. Sets up paths for bundled resources
2. Runs first-time setup wizard if needed
3. Starts the uvicorn server
4. Opens the browser to the application

MCP Server Mode:
When launched with --mcp <server>, runs as an MCP server instead of web server.
This allows the bundled exe to spawn itself as MCP tool servers.
- ClaudeCodeRP.exe --mcp action      → runs action MCP server (skip, memorize, recall)
- ClaudeCodeRP.exe --mcp guidelines  → runs guidelines MCP server (read, anthropic/openai)
"""

import argparse
import asyncio
import atexit
import getpass
import os
import secrets
import subprocess
import sys
import webbrowser
from pathlib import Path
from threading import Timer

# Windows detection
IS_WINDOWS = sys.platform == "win32"

# Track if we locked the Codex skills folder
_codex_skills_was_locked = False

# Windows asyncio subprocess fix - must be set before any async code runs
if IS_WINDOWS:
    # ProactorEventLoop is required for subprocess support on Windows
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Codex Windows executable name
_CODEX_WINDOWS_EXE_NAME = "codex-x86_64-pc-windows-msvc.exe"


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
    """Copy default agents if they don't exist."""
    if not getattr(sys, "frozen", False):
        return

    base_path = get_base_path()
    work_dir = get_work_dir()

    agents_dest = work_dir / "agents"
    agents_src = base_path / "agents"
    if not agents_dest.exists() and agents_src.exists():
        import shutil

        shutil.copytree(agents_src, agents_dest)
        print(f"기본 에이전트를 복사했습니다: {agents_dest}")


def _get_bundled_codex_path() -> Path | None:
    """Get the bundled Codex executable path on Windows.

    Checks two locations:
    1. Next to the main executable (for packaged builds)
    2. In bundled/ folder (for development)
    """
    if not IS_WINDOWS:
        return None

    # Packaged builds: next to the executable
    packaged_path = Path(sys.executable).parent / _CODEX_WINDOWS_EXE_NAME
    if packaged_path.exists():
        return packaged_path

    # Development: bundled/ folder
    dev_path = Path(__file__).parent.parent / "bundled" / _CODEX_WINDOWS_EXE_NAME
    if dev_path.exists():
        return dev_path

    return None


def _get_codex_skills_path() -> Path:
    """Get the path to the Codex skills folder."""
    return Path.home() / ".codex" / "skills"


def lock_codex_skills() -> bool:
    """Lock the Codex skills folder to prevent unnecessary prompts.

    Removes ALL permissions (equivalent to chmod 000 on Linux).
    Saves original ACL for restoration on unlock.
    Returns True if the folder was locked, False otherwise.
    """
    global _codex_skills_was_locked

    if not IS_WINDOWS:
        return False

    skills_path = _get_codex_skills_path()
    if not skills_path.exists():
        return False

    # PowerShell script to save ACL and remove all permissions
    ps_script = f'''
$path = "{skills_path}"
$acl = Get-Acl $path
$acl | Export-Clixml "{skills_path}.acl.xml"
$acl.SetAccessRuleProtection($true, $false)
$acl.Access | ForEach-Object {{ $acl.RemoveAccessRule($_) | Out-Null }}
Set-Acl $path $acl
'''

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            _codex_skills_was_locked = True
            print("Codex skills 폴더 잠금됨")
            return True
        else:
            print(f"경고: Codex skills 폴더 잠금 실패: {result.stderr.decode()}")
    except Exception as e:
        print(f"경고: Codex skills 폴더 잠금 실패: {e}")

    return False


def unlock_codex_skills() -> bool:
    """Unlock the Codex skills folder (restore access).

    Restores the original ACL that was saved during lock.
    Returns True if the folder was unlocked, False otherwise.
    """
    global _codex_skills_was_locked

    if not IS_WINDOWS or not _codex_skills_was_locked:
        return False

    skills_path = _get_codex_skills_path()
    acl_backup = Path(f"{skills_path}.acl.xml")

    if not skills_path.exists() or not acl_backup.exists():
        return False

    # PowerShell script to restore ACL from backup
    ps_script = f'''
$path = "{skills_path}"
$acl = Import-Clixml "{acl_backup}"
Set-Acl $path $acl
Remove-Item "{acl_backup}" -Force
'''

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            _codex_skills_was_locked = False
            print("Codex skills 폴더 잠금 해제됨")
            return True
        else:
            print(f"경고: Codex skills 폴더 잠금 해제 실패: {result.stderr.decode()}")
    except Exception as e:
        print(f"경고: Codex skills 폴더 잠금 해제 실패: {e}")

    return False


def check_codex_logged_in() -> bool:
    """Check if Codex is logged in (synchronous version for launcher)."""
    if not IS_WINDOWS:
        return True  # Skip on non-Windows

    codex_exe = _get_bundled_codex_path()
    if not codex_exe:
        print("Codex 실행 파일을 찾을 수 없습니다.")
        return False

    try:
        result = subprocess.run(
            [str(codex_exe), "login", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and "logged in" in result.stdout.lower():
            return True
        return False
    except subprocess.TimeoutExpired:
        print("Codex 인증 확인 시간 초과")
        return False
    except Exception as e:
        print(f"Codex 인증 확인 실패: {e}")
        return False


def run_codex_login() -> bool:
    """Run Codex login interactively (opens browser for OAuth)."""
    if not IS_WINDOWS:
        return True  # Skip on non-Windows

    codex_exe = _get_bundled_codex_path()
    if not codex_exe:
        print("Codex 실행 파일을 찾을 수 없습니다.")
        return False

    print()
    print("Codex 로그인을 시작합니다...")
    print("브라우저에서 인증을 완료해주세요.")
    print()

    try:
        # Run login interactively (don't capture output)
        result = subprocess.run(
            [str(codex_exe), "login"],
            timeout=300,  # 5 minutes for OAuth
        )
        if result.returncode == 0:
            print("Codex 로그인 성공!")
            return True
        else:
            print(f"Codex 로그인 실패 (종료 코드: {result.returncode})")
            return False
    except subprocess.TimeoutExpired:
        print("Codex 로그인 시간 초과 (5분)")
        return False
    except Exception as e:
        print(f"Codex 로그인 실패: {e}")
        return False


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
    print("Claude Code Role Play - 초기 설정")
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

    # Copy default agents
    copy_default_agents()

    # Check if setup is needed
    if is_env_configured(env_file):
        return False

    # Run first-time setup
    try:
        config = run_first_time_setup()
        create_env_file(env_file, config)

        # Check and run Codex login if needed (Windows only)
        if IS_WINDOWS and _get_bundled_codex_path():
            print()
            print("-" * 60)
            print("Codex 인증 확인 중...")
            if not check_codex_logged_in():
                print("Codex 로그인이 필요합니다.")
                if not run_codex_login():
                    print()
                    print("경고: Codex 로그인에 실패했습니다.")
                    print("Codex 프로바이더를 사용하려면 나중에 로그인이 필요합니다.")
            else:
                print("Codex 이미 로그인되어 있습니다.")

        print()
        print("=" * 60)
        print("설정 완료! 애플리케이션을 시작합니다...")
        print("=" * 60)
        print()
        return True
    except KeyboardInterrupt:
        print("\n\n설정이 취소되었습니다.")
        sys.exit(0)


def open_browser():
    """Open the browser to the application."""
    webbrowser.open("http://localhost:8000")


def run_mcp_server(server_type: str):
    """Run an MCP server (action or guidelines).

    This is called when the exe is launched with --mcp <server_type>.
    The MCP server communicates via stdio with the parent process.
    """
    # Set up paths for imports (but don't change working directory)
    base_path = get_base_path()
    backend_path = base_path / "backend"
    if backend_path.exists():
        sys.path.insert(0, str(backend_path))
    else:
        sys.path.insert(0, str(Path(__file__).parent))

    if server_type == "action":
        from mcp_servers.action_server import main as action_main

        asyncio.run(action_main())
    elif server_type == "guidelines":
        from mcp_servers.guidelines_server import main as guidelines_main

        asyncio.run(guidelines_main())
    else:
        print(f"Unknown MCP server type: {server_type}", file=sys.stderr)
        sys.exit(1)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Claude Code Role Play",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mcp",
        choices=["action", "guidelines"],
        help="Run as MCP server instead of web server (used internally)",
    )
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # If --mcp is specified, run as MCP server instead of web server
    if args.mcp:
        run_mcp_server(args.mcp)
        return

    # Set up paths first
    setup_paths()

    # Lock Codex skills folder to prevent unnecessary prompts
    # Register cleanup on exit
    lock_codex_skills()
    atexit.register(unlock_codex_skills)

    # Run environment setup (including first-time wizard if needed)
    setup_was_run = setup_environment()

    # Import uvicorn and app after setting up paths
    import uvicorn

    print("=" * 60)
    print("Claude Code Role Play")
    print("=" * 60)
    print()
    print("서버 시작 중: http://localhost:8000")
    print("서버를 중지하려면 Ctrl+C를 누르세요")
    print()

    # Open browser after a short delay
    Timer(2.0, open_browser).start()

    # Import the app directly instead of using string path
    # This works better with PyInstaller bundling
    # Note: main.py sets WindowsProactorEventLoopPolicy at import time
    from main import app

    # Run the server with the app object directly
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )


if __name__ == "__main__":
    main()
