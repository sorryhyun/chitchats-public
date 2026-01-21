"""
Platform-specific support for bundled Codex binaries.

This module handles detection and path resolution for bundled Codex executables
across different platforms (Windows, macOS, Linux) and deployment modes
(development, PyInstaller bundles).
"""

import logging
import platform
import sys
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("CodexWindowsSupport")

# Platform-specific binary names for bundled Codex executables
BUNDLED_BINARY_NAMES = {
    "windows-amd64": "codex-x86_64-pc-windows-msvc.exe",
    "windows-x86_64": "codex-x86_64-pc-windows-msvc.exe",
    "darwin-arm64": "codex-aarch64-apple-darwin",
    "darwin-x86_64": "codex-x86_64-apple-darwin",
    "linux-x86_64": "codex-x86_64-unknown-linux-gnu",
    "linux-aarch64": "codex-aarch64-unknown-linux-gnu",
}


def get_bundled_codex_path() -> Optional[str]:
    """Get the path to the bundled Codex Rust binary.

    Checks for platform-specific bundled binaries in:
    1. Next to the exe (for PyInstaller bundles)
    2. In _MEIPASS temp directory (for PyInstaller bundles)
    3. In project bundled/ directory (for development)

    Returns:
        Path to bundled binary if found, None otherwise
    """
    key = f"{platform.system().lower()}-{platform.machine().lower()}"
    binary_name = BUNDLED_BINARY_NAMES.get(key)

    if not binary_name:
        logger.warning(f"No bundled binary configured for platform: {key}")
        return None

    # Check multiple locations in order of priority
    search_paths: List[Path] = []

    if getattr(sys, "frozen", False):
        # Running as PyInstaller bundle
        # 1. Check next to the exe (work directory)
        exe_dir = Path(sys.executable).parent
        search_paths.append(exe_dir / binary_name)
        search_paths.append(exe_dir / "bundled" / binary_name)
        # 2. Check in _MEIPASS (temp extraction directory)
        meipass = Path(getattr(sys, "_MEIPASS", ""))
        if meipass:
            search_paths.append(meipass / binary_name)
            search_paths.append(meipass / "bundled" / binary_name)
    else:
        # Running in development
        # Project root: 4 levels up from backend/providers/codex/windows_support.py
        project_root = Path(__file__).parent.parent.parent.parent
        search_paths.append(project_root / "bundled" / binary_name)

    for path in search_paths:
        logger.debug(f"Checking bundled path: {path}")
        if path.exists():
            logger.info(f"Found bundled Codex binary: {path}")
            return str(path)

    logger.debug(f"Bundled Codex binary not found in: {[str(p) for p in search_paths]}")
    return None
