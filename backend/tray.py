"""
System tray icon for the ChitChats standalone application.

Provides a Windows system tray icon with:
- Status indicator (starting/running)
- Open in Browser action
- Open Log File action
- Quit action

Uses pystray for cross-platform system tray support.
Falls back gracefully if pystray is not available.
"""

import os
import sys
import threading
import webbrowser
from pathlib import Path

# Track tray state
_tray_icon = None
_tray_thread = None
_server_url = None
_log_file_path = None


def _get_icon_image():
    """Load the ChitChats icon for the system tray."""
    try:
        from PIL import Image

        # In PyInstaller bundle, check _MEIPASS for bundled icon
        if getattr(sys, "frozen", False):
            base_path = Path(sys._MEIPASS)
            # Check for icon in static files (bundled frontend)
            icon_paths = [
                base_path / "static" / "chitchats.webp",
                base_path / "static" / "chitchats.ico",
            ]
        else:
            # Development mode
            project_root = Path(__file__).parent.parent
            icon_paths = [
                project_root / "frontend" / "public" / "chitchats.webp",
                project_root / "frontend" / "public" / "chitchats.ico",
            ]

        for icon_path in icon_paths:
            if icon_path.exists():
                img = Image.open(icon_path)
                # Resize to standard tray icon size
                img = img.resize((64, 64), Image.LANCZOS)
                return img

        # Fallback: create a simple colored square icon
        img = Image.new("RGBA", (64, 64), (217, 119, 87, 255))  # #D97757 theme color
        return img

    except Exception:
        # If PIL fails, create minimal fallback
        try:
            from PIL import Image
            return Image.new("RGBA", (64, 64), (217, 119, 87, 255))
        except Exception:
            return None


def _open_browser(icon=None, item=None):
    """Open the application in the default browser."""
    if _server_url:
        webbrowser.open(_server_url)


def _open_log(icon=None, item=None):
    """Open the log file in the default text editor."""
    if _log_file_path and Path(_log_file_path).exists():
        if sys.platform == "win32":
            os.startfile(_log_file_path)
        else:
            webbrowser.open(f"file://{_log_file_path}")


def _quit_app(icon=None, item=None):
    """Quit the application."""
    global _tray_icon
    if _tray_icon:
        _tray_icon.stop()
    # Force exit the entire process (uvicorn may keep running otherwise)
    os._exit(0)


def start_tray(server_url: str, log_file: str = None):
    """
    Start the system tray icon in a background thread.

    Args:
        server_url: The URL where the server is running (e.g., "http://localhost:8000")
        log_file: Path to the log file (optional)
    """
    global _tray_icon, _tray_thread, _server_url, _log_file_path

    _server_url = server_url
    _log_file_path = log_file

    try:
        import pystray
    except ImportError:
        # pystray not available - silently skip tray icon
        return

    icon_image = _get_icon_image()
    if icon_image is None:
        return

    # Build menu items
    menu_items = [
        pystray.MenuItem(
            f"ChitChats - {server_url}",
            _open_browser,
            default=True,  # Double-click action
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open in Browser", _open_browser),
    ]

    if log_file:
        menu_items.append(pystray.MenuItem("Open Log File", _open_log))

    menu_items.extend([
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", _quit_app),
    ])

    menu = pystray.Menu(*menu_items)

    _tray_icon = pystray.Icon(
        name="ChitChats",
        icon=icon_image,
        title=f"ChitChats - {server_url}",
        menu=menu,
    )

    def _run_tray():
        _tray_icon.run()

    _tray_thread = threading.Thread(target=_run_tray, daemon=True)
    _tray_thread.start()

    # Show notification that the app is running
    try:
        _tray_icon.notify(
            f"Server running at {server_url}",
            "ChitChats",
        )
    except Exception:
        # Some platforms don't support notifications
        pass


def stop_tray():
    """Stop the system tray icon."""
    global _tray_icon
    if _tray_icon:
        try:
            _tray_icon.stop()
        except Exception:
            pass
        _tray_icon = None
