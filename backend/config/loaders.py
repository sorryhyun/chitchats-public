"""
Configuration file loaders.

Provides functions to load specific configuration files with caching.

Caching Behavior:
-----------------
Configuration files are cached with mtime-based invalidation. The cache is
automatically refreshed when the underlying YAML file is modified.

Environment Variable Behavior:
-----------------------------
Environment variable overrides (like DEBUG_AGENTS) are applied AFTER loading
from cache. This means:
1. YAML file changes → cache invalidated → fresh load
2. Environment variable changes → cache NOT invalidated → requires restart

To apply environment variable changes without restart:
- Modify the YAML file (even a whitespace change) to force cache refresh, OR
- Restart the application

Supported environment overrides:
- DEBUG_AGENTS: Overrides debug.enabled in debug.yaml (true/false)
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict

from .cache import get_cached_config

logger = logging.getLogger(__name__)

# Configuration file paths
CONFIG_DIR = Path(__file__).parent / "tools"
TOOLS_CONFIG = CONFIG_DIR / "tools.yaml"
GUIDELINES_CONFIG = CONFIG_DIR / "guidelines_3rd.yaml"
DEBUG_CONFIG = CONFIG_DIR / "debug.yaml"
CONVERSATION_CONTEXT_CONFIG = CONFIG_DIR / "conversation_context.yaml"
BRAIN_CONFIG = CONFIG_DIR / "brain_config.yaml"


def get_tools_config() -> Dict[str, Any]:
    """
    Load the tools configuration from tools.yaml.

    Returns:
        Dictionary containing tool definitions
    """
    return get_cached_config(TOOLS_CONFIG)


def get_guidelines_config() -> Dict[str, Any]:
    """
    Load the guidelines configuration from guidelines_3rd.yaml.

    Returns:
        Dictionary containing guideline templates
    """
    return get_cached_config(GUIDELINES_CONFIG)


def get_debug_config() -> Dict[str, Any]:
    """
    Load the debug configuration from debug.yaml with environment variable overrides.

    Environment variables take precedence:
    - DEBUG_AGENTS=true overrides debug.enabled

    Returns:
        Dictionary containing debug settings
    """
    config = get_cached_config(DEBUG_CONFIG)

    # Apply environment variable overrides
    if "debug" in config:
        debug_env = os.getenv("DEBUG_AGENTS", "").lower()
        if debug_env in ("true", "false"):
            config["debug"]["enabled"] = debug_env == "true"

    return config


def get_conversation_context_config() -> Dict[str, Any]:
    """
    Load the conversation context configuration from conversation_context.yaml.

    Returns:
        Dictionary containing conversation context templates
    """
    return get_cached_config(CONVERSATION_CONTEXT_CONFIG)


def get_brain_config() -> Dict[str, Any]:
    """
    Load the brain configuration from brain_config.yaml (consolidated config).

    Returns:
        Dictionary containing memory tools, policies, and context templates
    """
    return get_cached_config(BRAIN_CONFIG)


def get_memory_tools_config() -> Dict[str, Any]:
    """
    Load the memory tools configuration from brain_config.yaml.

    Returns:
        Dictionary containing memory tool definitions and policies
    """
    return get_brain_config()


def get_memory_context_config() -> Dict[str, Any]:
    """
    Load the memory context configuration from brain_config.yaml.

    Returns:
        Dictionary containing memory brain context templates
    """
    return get_brain_config()


__all__ = [
    "CONFIG_DIR",
    "TOOLS_CONFIG",
    "GUIDELINES_CONFIG",
    "DEBUG_CONFIG",
    "CONVERSATION_CONTEXT_CONFIG",
    "BRAIN_CONFIG",
    "get_tools_config",
    "get_guidelines_config",
    "get_debug_config",
    "get_conversation_context_config",
    "get_brain_config",
    "get_memory_tools_config",
    "get_memory_context_config",
]
