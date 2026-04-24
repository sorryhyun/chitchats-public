"""Windowed-mode detection and log-file redirection."""

import logging
import sys

from .paths import get_work_dir

_windowed_mode: bool | None = None
_log_file_path: str | None = None


def is_windowed_mode() -> bool:
    """Check if running in windowed mode (no console attached).

    The result is cached because setup_log_file() replaces sys.stderr with
    a log file handle, which would cause subsequent checks to return False.
    """
    global _windowed_mode
    if _windowed_mode is not None:
        return _windowed_mode

    if not getattr(sys, "frozen", False):
        _windowed_mode = False
    else:
        _windowed_mode = sys.stderr is None or not hasattr(sys.stderr, "write")

    return _windowed_mode


def setup_log_file() -> str | None:
    """Redirect stdout/stderr to a log file when running in windowed mode.

    Returns the log file path, or None if not in windowed mode.
    """
    global _log_file_path

    if not is_windowed_mode():
        return None

    log_path = get_work_dir() / "chitchats.log"
    _log_file_path = str(log_path)

    try:
        log_file = open(log_path, "a", encoding="utf-8", buffering=1)
        sys.stdout = log_file
        sys.stderr = log_file
        logging.basicConfig(
            stream=log_file,
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
        return _log_file_path
    except Exception:
        return None
