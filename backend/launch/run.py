"""Main orchestrator: wires together setup, server start, and shutdown."""

import atexit
import signal
import sys

from .browser import open_browser_delayed
from .instance import check_single_instance, cleanup_lock_file
from .logging_setup import is_windowed_mode, setup_log_file
from .mcp_mode import is_tauri_sidecar, run_mcp_server
from .network import DEFAULT_PORT, find_available_port
from .paths import setup_paths
from .setup import setup_environment
from .windows_compat import patch_subprocess_no_window, setup_job_kill_on_close


def main():
    """Main entry point."""
    # Check for MCP server mode first (before any other setup).
    # This allows the bundled exe to be spawned as an MCP server subprocess.
    if "--mcp-server" in sys.argv:
        try:
            idx = sys.argv.index("--mcp-server")
            server_type = sys.argv[idx + 1]
        except (IndexError, ValueError):
            print("Usage: ChitChats.exe --mcp-server <action|guidelines>", file=sys.stderr)
            sys.exit(1)
        run_mcp_server(server_type)
        return

    setup_paths()

    # Ensure all child processes are killed when this process exits.
    # Must be called before any subprocess is spawned.
    setup_job_kill_on_close()

    # Patch subprocess creation to hide console windows in windowed mode.
    # The Claude Agent SDK uses anyio.open_process() which internally calls
    # asyncio.create_subprocess_exec(), which ultimately calls subprocess.Popen.
    # Without CREATE_NO_WINDOW, each claude.exe subprocess spawns a visible console.
    if is_windowed_mode() and sys.platform == "win32":
        patch_subprocess_no_window()

    if not check_single_instance():
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

    setup_log_file()

    def signal_handler(signum, frame):
        print("\n서버를 종료합니다...")
        cleanup_lock_file()
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    atexit.register(cleanup_lock_file)

    sidecar_mode = is_tauri_sidecar()

    # In sidecar mode, Tauri handles setup via GUI.
    if not sidecar_mode:
        setup_environment()

    import uvicorn

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
        open_browser_delayed(server_url)
        print("브라우저를 자동으로 엽니다...")

    print()

    # Import the app directly instead of using string path — this works better with PyInstaller bundling.
    from main import app

    # Use 127.0.0.1 instead of 0.0.0.0 to avoid Windows permission issues.
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level="info",
    )
