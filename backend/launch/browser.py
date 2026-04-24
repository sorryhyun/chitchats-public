"""Browser launching (app-mode for bundled exe) and window-close monitoring."""

import os
import shutil
import sys
import threading
import time
import webbrowser

from .instance import cleanup_lock_file
from .logging_setup import is_windowed_mode

_browser_opened = False


def _find_browser_for_app_mode() -> str | None:
    """Find a Chromium-based browser that supports --app mode.

    Returns the executable path, or None if not found.
    Checks Chrome first, then Edge as fallback.
    """
    candidates = [
        # Chrome (preferred)
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        # Edge (fallback, pre-installed on Windows 10/11)
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]

    for path in candidates:
        if os.path.isfile(path):
            return path

    for cmd in ["chrome", "google-chrome", "msedge"]:
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

        if getattr(sys, "frozen", False):
            browser_path = _find_browser_for_app_mode()
            if browser_path:
                try:
                    proc = sp.Popen(
                        [browser_path, f"--app={url}"],
                        stdout=sp.DEVNULL,
                        stderr=sp.DEVNULL,
                    )
                    if is_windowed_mode():
                        _monitor_browser_process(proc)
                    return
                except Exception:
                    pass

        webbrowser.open(url)

    threading.Thread(target=_open, daemon=True).start()


def _monitor_browser_process(proc):
    """Monitor a browser process and terminate the server when it exits.

    Used in windowed (exe) mode to quit the server when the user closes
    the browser app window, instead of requiring a tray icon quit action.
    """
    def _wait_and_exit():
        start = time.monotonic()
        proc.wait()
        elapsed = time.monotonic() - start
        # If process exited within 3 seconds, the browser was already running
        # and delegated to the existing instance — don't kill the server
        if elapsed < 3:
            return
        print("\n브라우저 창이 닫혔습니다. 서버를 종료합니다...")
        cleanup_lock_file()
        os._exit(0)

    threading.Thread(target=_wait_and_exit, daemon=True).start()
