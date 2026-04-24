"""Thin shim — real code lives in `backend/launch/`.

Kept for backwards compatibility with:
- ChitChats.spec (PyInstaller entry script points here)
- backend/tray.py (imports `_find_browser_for_app_mode`, `cleanup_lock_file`)
"""

from launch.browser import _find_browser_for_app_mode
from launch.instance import cleanup_lock_file
from launch.run import main

__all__ = ["main", "cleanup_lock_file", "_find_browser_for_app_mode"]


if __name__ == "__main__":
    main()
