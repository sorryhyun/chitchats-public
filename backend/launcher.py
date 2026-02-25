"""
Launcher script for the packaged ChitChats application.

This is the entry point for the PyInstaller bundle. It:
1. Sets up paths for bundled resources
2. Runs first-time setup wizard if needed (console mode only)
3. Opens the default web browser automatically
4. Starts the uvicorn server
5. Shows a system tray icon in windowed mode (no console window)

When run as a Tauri sidecar (legacy, archived):
- Setup is handled by Tauri's GUI wizard
- Browser is not opened (Tauri provides the webview)
- Graceful shutdown on SIGTERM
"""

import getpass
import logging
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

# Log file path (set during setup_logging)
_log_file_path = None


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


_windowed_mode: bool | None = None


def is_windowed_mode() -> bool:
    """Check if running in windowed mode (no console attached).

    In windowed mode (PyInstaller with console=False), there is no console
    window. We use a system tray icon and log file instead.

    The result is cached because setup_log_file() replaces sys.stderr with
    a log file handle, which would cause subsequent checks to return False.
    """
    global _windowed_mode
    if _windowed_mode is not None:
        return _windowed_mode

    if not getattr(sys, "frozen", False):
        _windowed_mode = False
    else:
        # sys.stderr is None when running in windowed mode (--noconsole)
        _windowed_mode = sys.stderr is None or not hasattr(sys.stderr, "write")

    return _windowed_mode


def setup_log_file() -> str | None:
    """Redirect stdout/stderr to a log file when running in windowed mode.

    Returns the log file path, or None if not in windowed mode.
    """
    global _log_file_path

    if not is_windowed_mode():
        return None

    work_dir = get_work_dir()
    log_path = work_dir / "chitchats.log"
    _log_file_path = str(log_path)

    try:
        # Open log file in append mode with UTF-8 encoding
        log_file = open(log_path, "a", encoding="utf-8", buffering=1)

        # Redirect stdout and stderr to log file
        sys.stdout = log_file
        sys.stderr = log_file

        # Also configure Python's root logger to write to the file
        logging.basicConfig(
            stream=log_file,
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

        return _log_file_path
    except Exception:
        # If we can't set up logging, continue without it
        return None


def check_single_instance() -> bool:
    """Check if another instance is already running using a lock file.

    Returns True if this is the only instance, False if another is running.
    """
    if not getattr(sys, "frozen", False):
        return True  # Skip in development mode

    work_dir = get_work_dir()
    lock_file = work_dir / ".chitchats.lock"

    try:
        if lock_file.exists():
            # Check if the PID in the lock file is still running
            try:
                pid = int(lock_file.read_text().strip())
                # On Windows, check if process exists
                if sys.platform == "win32":
                    import ctypes
                    kernel32 = ctypes.windll.kernel32
                    handle = kernel32.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE
                    if handle:
                        kernel32.CloseHandle(handle)
                        return False  # Process is still running
                else:
                    os.kill(pid, 0)  # Signal 0 = check if process exists
                    return False
            except (ValueError, OSError, ProcessLookupError):
                pass  # Stale lock file, remove it

        # Write our PID
        lock_file.write_text(str(os.getpid()))
        return True
    except Exception:
        return True  # If we can't check, allow running


def cleanup_lock_file():
    """Remove the lock file on exit."""
    if not getattr(sys, "frozen", False):
        return

    work_dir = get_work_dir()
    lock_file = work_dir / ".chitchats.lock"
    try:
        if lock_file.exists():
            lock_file.unlink()
    except Exception:
        pass


def _patch_subprocess_no_window():
    """Patch subprocess.Popen to hide console windows on Windows.

    When running as a windowed exe (console=False), any subprocess spawned
    without CREATE_NO_WINDOW will flash a visible console window. This patches
    subprocess.Popen to automatically inject the flag for all subprocesses,
    hiding the Claude CLI terminal that would otherwise appear.
    """
    import subprocess

    CREATE_NO_WINDOW = 0x08000000
    _original_popen_init = subprocess.Popen.__init__

    def _patched_popen_init(self, *args, **kwargs):
        # Inject CREATE_NO_WINDOW if no creationflags specified
        if "creationflags" not in kwargs or kwargs["creationflags"] == 0:
            kwargs["creationflags"] = CREATE_NO_WINDOW
        _original_popen_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = _patched_popen_init


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



def is_env_configured(env_file: Path) -> bool:
    """Check if .env file has valid configuration."""
    if not env_file.exists():
        return False

    content = env_file.read_text(encoding="utf-8")

    # Check for placeholder values that indicate unconfigured state
    has_valid_hash = "API_KEY_HASH=" in content and "example_hash" not in content and "paste_your" not in content
    has_valid_jwt = "JWT_SECRET=" in content and "your-random-secret" not in content

    return has_valid_hash and has_valid_jwt


def run_first_time_setup_gui():
    """Run first-time setup using a GUI dialog (for windowed mode without console).

    Uses PowerShell Windows Forms to show a proper setup dialog.
    Falls back to auto-generated credentials with a MessageBox notification.

    Returns:
        dict with password_hash, jwt_secret, user_name, or None if cancelled.
    """
    import bcrypt
    import subprocess

    ps_script = r'''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = "ChitChats - Setup"
$form.Size = New-Object System.Drawing.Size(420, 320)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true
$form.Font = New-Object System.Drawing.Font("Segoe UI", 9)

$y = 15

$lblTitle = New-Object System.Windows.Forms.Label
$lblTitle.Location = New-Object System.Drawing.Point(20, $y)
$lblTitle.Size = New-Object System.Drawing.Size(360, 25)
$lblTitle.Text = "Welcome! Please set up your password."
$lblTitle.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$form.Controls.Add($lblTitle)
$y += 35

$lblPass = New-Object System.Windows.Forms.Label
$lblPass.Location = New-Object System.Drawing.Point(20, $y)
$lblPass.Size = New-Object System.Drawing.Size(360, 18)
$lblPass.Text = "Password (min 4 characters):"
$form.Controls.Add($lblPass)
$y += 22

$txtPass = New-Object System.Windows.Forms.TextBox
$txtPass.Location = New-Object System.Drawing.Point(20, $y)
$txtPass.Size = New-Object System.Drawing.Size(360, 25)
$txtPass.UseSystemPasswordChar = $true
$form.Controls.Add($txtPass)
$y += 35

$lblConfirm = New-Object System.Windows.Forms.Label
$lblConfirm.Location = New-Object System.Drawing.Point(20, $y)
$lblConfirm.Size = New-Object System.Drawing.Size(360, 18)
$lblConfirm.Text = "Confirm Password:"
$form.Controls.Add($lblConfirm)
$y += 22

$txtConfirm = New-Object System.Windows.Forms.TextBox
$txtConfirm.Location = New-Object System.Drawing.Point(20, $y)
$txtConfirm.Size = New-Object System.Drawing.Size(360, 25)
$txtConfirm.UseSystemPasswordChar = $true
$form.Controls.Add($txtConfirm)
$y += 35

$lblName = New-Object System.Windows.Forms.Label
$lblName.Location = New-Object System.Drawing.Point(20, $y)
$lblName.Size = New-Object System.Drawing.Size(360, 18)
$lblName.Text = "Display Name (default: User):"
$form.Controls.Add($lblName)
$y += 22

$txtName = New-Object System.Windows.Forms.TextBox
$txtName.Location = New-Object System.Drawing.Point(20, $y)
$txtName.Size = New-Object System.Drawing.Size(360, 25)
$form.Controls.Add($txtName)
$y += 40

$lblError = New-Object System.Windows.Forms.Label
$lblError.Location = New-Object System.Drawing.Point(20, $y)
$lblError.Size = New-Object System.Drawing.Size(200, 20)
$lblError.ForeColor = [System.Drawing.Color]::Red
$form.Controls.Add($lblError)

$btnOK = New-Object System.Windows.Forms.Button
$btnOK.Location = New-Object System.Drawing.Point(220, $y)
$btnOK.Size = New-Object System.Drawing.Size(75, 28)
$btnOK.Text = "OK"
$form.Controls.Add($btnOK)

$btnCancel = New-Object System.Windows.Forms.Button
$btnCancel.Location = New-Object System.Drawing.Point(305, $y)
$btnCancel.Size = New-Object System.Drawing.Size(75, 28)
$btnCancel.Text = "Cancel"
$btnCancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
$form.CancelButton = $btnCancel
$form.Controls.Add($btnCancel)

$btnOK.Add_Click({
    if ($txtPass.Text.Length -lt 4) {
        $lblError.Text = "Min 4 characters."
        return
    }
    if ($txtPass.Text -ne $txtConfirm.Text) {
        $lblError.Text = "Passwords do not match."
        return
    }
    $form.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.Close()
})

$form.AcceptButton = $btnOK
$result = $form.ShowDialog()

if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
    # Use pipe separator to avoid issues with special chars in password
    Write-Output ("OK|" + $txtPass.Text + "|" + $txtName.Text)
} else {
    Write-Output "CANCELLED"
}
'''

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=300,  # 5 min timeout
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        output = result.stdout.strip()
        if output.startswith("OK|"):
            # Split from the right: last field is username, everything between first and last | is password
            # This handles passwords containing | characters
            first_pipe = output.index("|")
            last_pipe = output.rindex("|")
            password = output[first_pipe + 1:last_pipe]
            user_name = output[last_pipe + 1:] or "User"

            salt = bcrypt.gensalt()
            password_hash = bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

            return {
                "password_hash": password_hash,
                "jwt_secret": secrets.token_hex(32),
                "user_name": user_name,
            }
        else:
            # User cancelled
            return None

    except Exception as e:
        print(f"GUI setup dialog failed: {e}")
        # Fallback: auto-generate credentials and notify via MessageBox
        return _auto_generate_setup()


def _auto_generate_setup():
    """Fallback: auto-generate credentials and show the password via MessageBox."""
    import bcrypt
    import string
    import random

    # Generate a readable random password
    chars = string.ascii_letters + string.digits
    password = "".join(random.choices(chars, k=12))

    salt = bcrypt.gensalt()
    password_hash = bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    # Show the generated password to the user
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            f"ChitChats has been set up with an auto-generated password:\n\n"
            f"    {password}\n\n"
            f"Please save this password. You will need it to log in.\n"
            f"To change it later, edit the .env file and run:\n"
            f"    make generate-hash",
            "ChitChats - Setup Complete",
            0x40,  # MB_ICONINFORMATION
        )
    except Exception:
        pass

    return {
        "password_hash": password_hash,
        "jwt_secret": secrets.token_hex(32),
        "user_name": "User",
    }


def run_first_time_setup():
    """Run interactive first-time setup wizard (console mode)."""
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

    # Copy default agents
    copy_default_agents()

    # Check if setup is needed
    if is_env_configured(env_file):
        return False

    # Run first-time setup (GUI for windowed mode, console otherwise)
    try:
        if is_windowed_mode():
            config = run_first_time_setup_gui()
            if config is None:
                # User cancelled - exit
                sys.exit(0)
        else:
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


def _find_browser_for_app_mode() -> str | None:
    """Find a Chromium-based browser that supports --app mode.

    Returns the executable path, or None if not found.
    Checks Edge first (always on Windows 10/11), then Chrome.
    """
    import shutil

    # Common paths on Windows
    candidates = [
        # Edge (pre-installed on Windows 10/11)
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        # Chrome
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]

    for path in candidates:
        if os.path.isfile(path):
            return path

    # Try PATH lookup
    for cmd in ["msedge", "chrome", "google-chrome"]:
        found = shutil.which(cmd)
        if found:
            return found

    return None


def open_browser_delayed(url: str, delay: float = 1.5):
    """Open browser after a delay to allow server to start.

    In bundled (exe) mode, tries to open in app mode (--app flag) using
    Edge or Chrome for a standalone window without address bar or tabs.
    Falls back to the default browser if no Chromium browser is found.

    Uses a global flag to prevent duplicate browser opens which can happen
    when Claude SDK or Codex subprocess triggers browser behavior on Windows.
    """
    global _browser_opened

    if _browser_opened:
        return

    _browser_opened = True

    def _open():
        import subprocess as sp

        time.sleep(delay)

        # In bundled mode, try app mode for a native-like window
        if getattr(sys, "frozen", False):
            browser_path = _find_browser_for_app_mode()
            if browser_path:
                try:
                    sp.Popen(
                        [browser_path, f"--app={url}"],
                        stdout=sp.DEVNULL,
                        stderr=sp.DEVNULL,
                    )
                    return
                except Exception:
                    pass

        # Fallback: regular browser tab
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

    # Patch subprocess creation to hide console windows in windowed mode.
    # The Claude Agent SDK uses anyio.open_process() which internally calls
    # asyncio.create_subprocess_exec(), which ultimately calls subprocess.Popen.
    # Without CREATE_NO_WINDOW, each claude.exe subprocess spawns a visible console.
    if is_windowed_mode() and sys.platform == "win32":
        _patch_subprocess_no_window()

    # Check for single instance (bundled mode only)
    if not check_single_instance():
        # Another instance is running - try to open the browser to the existing one
        # and exit quietly
        if is_windowed_mode():
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(
                    0,
                    "ChitChats is already running.\nCheck the system tray icon.",
                    "ChitChats",
                    0x40,  # MB_ICONINFORMATION
                )
            except Exception:
                pass
        else:
            print("ChitChats is already running.")
        sys.exit(0)

    # Set up log file for windowed mode (no console)
    log_file = setup_log_file()

    # Set up signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        print("\n서버를 종료합니다...")
        cleanup_lock_file()
        try:
            from tray import stop_tray
            stop_tray()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Register lock file cleanup at exit
    import atexit
    atexit.register(cleanup_lock_file)

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
    server_url = f"http://localhost:{port}"

    print("=" * 60)
    print("ChitChats")
    print("=" * 60)
    print()
    if port != DEFAULT_PORT:
        print(f"포트 {DEFAULT_PORT}을(를) 사용할 수 없어 포트 {port}을(를) 사용합니다.")
    print(f"서버 시작 중: {server_url}")
    if not sidecar_mode:
        print("서버를 중지하려면 Ctrl+C를 누르세요")
        print()
        # Open browser automatically (standalone mode only)
        open_browser_delayed(server_url)
        print("브라우저를 자동으로 엽니다...")

        # Start system tray icon (windowed mode)
        if is_windowed_mode():
            try:
                from tray import start_tray
                start_tray(server_url, log_file)
                print("시스템 트레이 아이콘이 활성화되었습니다.")
            except Exception as e:
                print(f"시스템 트레이 아이콘을 시작할 수 없습니다: {e}")
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
