"""
Caching infrastructure for YAML configuration files.

Provides file-based caching with automatic invalidation on file changes.
"""

import logging
from pathlib import Path
from typing import Any, Dict

from infrastructure.locking import file_lock
from ruamel.yaml import YAML

yaml = YAML(typ="safe", pure=True)
logger = logging.getLogger(__name__)

# Cache for loaded configurations: path -> (mtime, config)
_config_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}


def _get_file_mtime(file_path: Path) -> float:
    """Get the modification time of a file."""
    try:
        return file_path.stat().st_mtime
    except FileNotFoundError:
        return 0.0


def _load_yaml_file(file_path: Path) -> Dict[str, Any]:
    """
    Load a YAML file with file locking.

    Args:
        file_path: Path to the YAML file

    Returns:
        Dictionary containing the parsed YAML content
    """
    if not file_path.exists():
        logger.warning(f"Configuration file not found: {file_path}")
        return {}

    try:
        with file_lock(str(file_path), "r") as f:
            content = yaml.load(f)
            return content if content else {}
    except Exception as e:
        logger.error(f"Error loading YAML file {file_path}: {e}")
        return {}


def get_cached_config(file_path: Path, force_reload: bool = False) -> Dict[str, Any]:
    """
    Get configuration from cache or reload if file has changed.

    Args:
        file_path: Path to the configuration file
        force_reload: Force reload even if cache is valid

    Returns:
        Configuration dictionary
    """
    cache_key = str(file_path)
    current_mtime = _get_file_mtime(file_path)

    # Check if cache is valid
    if not force_reload and cache_key in _config_cache:
        cached_mtime, cached_config = _config_cache[cache_key]
        if cached_mtime == current_mtime:
            return cached_config

    # Load fresh configuration
    config = _load_yaml_file(file_path)
    _config_cache[cache_key] = (current_mtime, config)

    logger.debug(f"Loaded configuration from {file_path}")
    return config


def clear_cache():
    """Clear the configuration cache."""
    global _config_cache
    _config_cache.clear()
    logger.info("Cleared configuration cache")


# Export internal functions and cache for testing
__all__ = [
    "_config_cache",
    "_get_file_mtime",
    "_load_yaml_file",
    "get_cached_config",
    "clear_cache",
]
