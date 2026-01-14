"""
Configuration file loaders.

Provides functions to load specific configuration files with caching.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict

from .cache import get_cached_config

logger = logging.getLogger(__name__)


def get_guidelines_file() -> str:
    """
    Get the guidelines file name from settings.

    Returns:
        Guidelines file name (without .yaml extension)
    """
    from core import get_settings

    return get_settings().guidelines_file


def get_guidelines_config_path() -> Path:
    """
    Get the path to the guidelines config file.

    Returns:
        Path to the guidelines YAML file
    """
    from core import get_settings

    return get_settings().guidelines_config_path


# Backward compatibility: module-level constants that delegate to settings
def __getattr__(name: str):
    from core import get_settings

    settings = get_settings()

    # Map old constant names to settings properties
    path_map = {
        "CONFIG_DIR": settings.config_dir,
        "TOOLS_CONFIG": settings.tools_config_path,
        "DEBUG_CONFIG": settings.debug_config_path,
        "CONVERSATION_CONTEXT_CONFIG": settings.conversation_context_config_path,
        "GUIDELINES_FILE": settings.guidelines_file,
        "GUIDELINES_CONFIG": settings.guidelines_config_path,
    }

    if name in path_map:
        return path_map[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_tools_config() -> Dict[str, Any]:
    """
    Load the tools configuration from tools.yaml.

    Returns:
        Dictionary containing tool definitions
    """
    from core import get_settings

    return get_cached_config(get_settings().tools_config_path)


def get_provider_tools_config(provider: str) -> Dict[str, Any]:
    """
    Load provider-specific tools configuration.

    Args:
        provider: Provider name ('claude' or 'codex')

    Returns:
        Dictionary containing provider-specific tool overrides, or empty dict if not found
    """
    if not provider:
        return {}

    from core import get_settings

    provider_config_path = get_settings().get_provider_tools_config_path(provider)

    if not provider_config_path.exists():
        logger.debug(f"No provider config found for '{provider}' at {provider_config_path}")
        return {}

    try:
        config = get_cached_config(provider_config_path)
        logger.debug(f"Loaded provider config for '{provider}': {list(config.keys())}")
        return config
    except Exception as e:
        logger.warning(f"Error loading provider config for '{provider}': {e}")
        return {}


def get_guidelines_config() -> Dict[str, Any]:
    """
    Load the guidelines configuration from guidelines.yaml.

    Returns:
        Dictionary containing guideline templates
    """
    return get_cached_config(get_guidelines_config_path())


def get_debug_config() -> Dict[str, Any]:
    """
    Load the debug configuration from debug.yaml with environment variable overrides.

    Environment variables take precedence:
    - DEBUG_AGENTS=true overrides debug.enabled

    Returns:
        Dictionary containing debug settings
    """
    from core import get_settings

    config = get_cached_config(get_settings().debug_config_path)

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
    from core import get_settings

    return get_cached_config(get_settings().conversation_context_config_path)


def get_group_config(group_name: str) -> Dict[str, Any]:
    """
    Load group-specific configuration from group_config.yaml.

    Args:
        group_name: Name of the group (e.g., "슈타게", "체인소맨")

    Returns:
        Dictionary containing group-specific tool overrides, or empty dict if not found
    """
    if not group_name:
        return {}

    from core import get_settings

    # Use settings to get agents directory path
    group_config_path = get_settings().agents_dir / f"group_{group_name}" / "group_config.yaml"

    if not group_config_path.exists():
        logger.debug(f"No group config found for group '{group_name}' at {group_config_path}")
        return {}

    try:
        config = get_cached_config(group_config_path)
        logger.debug(f"Loaded group config for '{group_name}': {list(config.keys())}")
        return config
    except Exception as e:
        logger.warning(f"Error loading group config for '{group_name}': {e}")
        return {}


def get_extreme_traits(group_name: str) -> Dict[str, str]:
    """
    Load extreme traits configuration from group's extreme_traits.yaml.

    Args:
        group_name: Name of the group (e.g., "마마마", "슈타게")

    Returns:
        Dictionary mapping agent names to their extreme traits, or empty dict if not found
    """
    if not group_name:
        return {}

    from core import get_settings

    extreme_traits_path = get_settings().agents_dir / f"group_{group_name}" / "extreme_traits.yaml"

    if not extreme_traits_path.exists():
        logger.debug(f"No extreme traits found for group '{group_name}' at {extreme_traits_path}")
        return {}

    try:
        config = get_cached_config(extreme_traits_path)
        logger.debug(f"Loaded extreme traits for '{group_name}': {list(config.keys())}")
        return config if isinstance(config, dict) else {}
    except Exception as e:
        logger.warning(f"Error loading extreme traits for '{group_name}': {e}")
        return {}


def merge_tool_configs(base_config: Dict[str, Any], group_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge group-specific tool configurations over base (global) tool configurations.

    Group config can override any field in the base config (e.g., response, description, etc.)

    Args:
        base_config: Base tools configuration from tools.yaml
        group_config: Group-specific configuration from group_config.yaml

    Returns:
        Merged configuration dictionary
    """
    if not group_config or "tools" not in group_config:
        return base_config

    # Deep copy base config to avoid mutation
    import copy

    merged = copy.deepcopy(base_config)

    # Merge tool overrides from group config
    group_tools = group_config.get("tools", {})
    base_tools = merged.get("tools", {})

    for tool_name, tool_overrides in group_tools.items():
        if tool_name in base_tools:
            # Merge/override fields for this tool
            base_tools[tool_name].update(tool_overrides)
            logger.debug(f"Applied group config override for tool '{tool_name}': {list(tool_overrides.keys())}")
        else:
            logger.warning(f"Group config specifies unknown tool '{tool_name}', ignoring")

    return merged
