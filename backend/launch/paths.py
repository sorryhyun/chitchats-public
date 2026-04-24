"""Path resolution for dev vs. PyInstaller-bundled modes."""

import os
import sys
from pathlib import Path


def get_base_path() -> Path:
    """Get the base path for resources (handles both dev and bundled modes)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.parent.parent


def get_work_dir() -> Path:
    """Get the working directory for user data (.env, agents, etc.)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent.parent


def setup_paths():
    """Set up Python paths for imports."""
    base_path = get_base_path()

    backend_path = base_path / "backend"
    if backend_path.exists():
        sys.path.insert(0, str(backend_path))
    else:
        # In dev mode, backend is current directory's parent
        sys.path.insert(0, str(Path(__file__).parent.parent))

    work_dir = get_work_dir()
    os.chdir(work_dir)
