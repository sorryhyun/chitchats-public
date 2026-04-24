"""Single-instance lock file management (bundled mode)."""

import os
import sys

from .paths import get_work_dir


def check_single_instance() -> bool:
    """Check if another instance is already running using a lock file.

    Returns True if this is the only instance, False if another is running.
    """
    if not getattr(sys, "frozen", False):
        return True

    lock_file = get_work_dir() / ".chitchats.lock"

    try:
        if lock_file.exists():
            try:
                pid = int(lock_file.read_text().strip())
                if sys.platform == "win32":
                    import ctypes
                    kernel32 = ctypes.windll.kernel32
                    handle = kernel32.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE
                    if handle:
                        kernel32.CloseHandle(handle)
                        return False
                else:
                    os.kill(pid, 0)
                    return False
            except (ValueError, OSError, ProcessLookupError):
                pass  # Stale lock file

        lock_file.write_text(str(os.getpid()))
        return True
    except Exception:
        return True


def cleanup_lock_file():
    """Remove the lock file on exit."""
    if not getattr(sys, "frozen", False):
        return

    lock_file = get_work_dir() / ".chitchats.lock"
    try:
        if lock_file.exists():
            lock_file.unlink()
    except Exception:
        pass
