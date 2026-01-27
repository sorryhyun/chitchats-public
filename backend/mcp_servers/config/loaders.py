"""
Configuration file loaders.

Provides functions to load specific configuration files with caching.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict

from infrastructure.yaml_cache import get_cached_config

logger = logging.getLogger(__name__)

# Path to shared prompts config
_PROMPTS_SHARED_PATH = Path(__file__).parent / "prompts_shared.yaml"


def get_guidelines_config_path() -> Path:
    """
    Get the path to the guidelines config file.

    Returns:
        Path to the guidelines YAML file
    """
    from core import get_settings

    return get_settings().guidelines_config_path


def get_provider_prompts(provider: str) -> Dict[str, Any]:
    """
    Load provider-specific prompts configuration.

    Args:
        provider: The AI provider ("claude" or "codex")

    Returns:
        Dictionary containing system_prompt and conversation_context
    """
    if provider == "claude":
        from providers.claude.prompts import _get_prompts_config

        return _get_prompts_config()
    elif provider == "codex":
        from providers.codex.prompts import _get_prompts_config

        return _get_prompts_config()
    else:
        logger.warning(f"Unknown provider '{provider}', falling back to claude")
        from providers.claude.prompts import _get_prompts_config

        return _get_prompts_config()


def get_shared_prompts_config() -> Dict[str, Any]:
    """
    Load shared prompts configuration from prompts_shared.yaml.

    Returns:
        Dictionary containing situation_builder and other shared templates
    """
    return get_cached_config(_PROMPTS_SHARED_PATH)


def get_tools_config() -> Dict[str, Any]:
    """
    Get tools configuration from the Python registry (tools.py).

    Returns a dictionary compatible with the old YAML format for backwards compatibility.

    Returns:
        Dictionary containing tool definitions with 'tools' key
    """
    from .tools import TOOLS

    # Convert ToolDef objects to dictionary format for backwards compatibility
    tools_dict = {}
    for tool_name, tool_def in TOOLS.items():
        tools_dict[tool_name] = {
            "name": tool_def.name,
            "group": tool_def.group,
            "description": tool_def.description,
            "response": tool_def.response,
            "enabled": tool_def.enabled,
        }
        if tool_def.providers:
            tools_dict[tool_name]["providers"] = tool_def.providers
        if tool_def.requires:
            tools_dict[tool_name]["requires"] = tool_def.requires

    return {"tools": tools_dict}


def get_guidelines_config() -> Dict[str, Any]:
    """
    Load the guidelines configuration from guidelines.yaml.

    Returns:
        Dictionary containing guideline templates
    """
    return get_cached_config(get_guidelines_config_path())


def get_system_prompt_config() -> Dict[str, Any]:
    """
    Load the system prompt configuration.

    DEPRECATED: Use get_provider_prompts(provider) instead.
    This function now loads from provider-specific prompts.yaml files.

    Returns:
        Dictionary containing system prompt templates (claude format for backwards compat)
    """
    logger.debug("get_system_prompt_config is deprecated, use get_provider_prompts() instead")
    from providers.claude.prompts import _get_prompts_config

    config = _get_prompts_config()

    # Convert to old format for backwards compatibility
    active_key = config.get("active_system_prompt", "system_prompt_v7")
    prompt_content = config.get(active_key, "")

    return {
        "active_system_prompt": active_key,
        active_key: {
            "claude": prompt_content,
            "codex": get_provider_prompts("codex").get(active_key, ""),
        },
    }


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


def get_conversation_context_config(provider: str = "claude") -> Dict[str, Any]:
    """
    Load the conversation context configuration.

    Args:
        provider: The AI provider ("claude" or "codex")

    Returns:
        Dictionary containing conversation context templates merged with shared config
    """
    # Get provider-specific context config
    provider_prompts = get_provider_prompts(provider)
    provider_context = provider_prompts.get("conversation_context", {})

    # Get shared config (situation_builder, etc.)
    shared_config = get_shared_prompts_config()

    # Merge: shared config keys are added to provider context
    result = dict(provider_context)
    for key, value in shared_config.items():
        if key not in result:
            result[key] = value

    return result


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
