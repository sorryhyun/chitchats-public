"""
Tool configuration functions.

Provides functions to get tool descriptions, schemas, and groupings.
"""

import logging
from typing import Any, Dict, Optional

from .loaders import (
    get_conversation_context_config,
    get_group_config,
    get_guidelines_config,
    get_tools_config,
    merge_tool_configs,
)

logger = logging.getLogger(__name__)


def _get_tools_config_for_group(group_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Get tools configuration with group-specific overrides applied.

    Args:
        group_name: Optional group name to apply group-specific overrides

    Returns:
        Tools configuration dictionary (merged with group config if applicable)
    """
    base_config = get_tools_config()

    if not group_name:
        return base_config

    # Load and merge group config
    group_config = get_group_config(group_name)
    if group_config:
        return merge_tool_configs(base_config, group_config)

    return base_config


def get_tool_description(
    tool_name: str,
    agent_name: str = "",
    config_sections: str = "",
    situation_builder_note: str = "",
    memory_subtitles: str = "",
    group_name: Optional[str] = None,
    provider: str = "claude",
) -> Optional[str]:
    """
    Get a tool description with template variables substituted.

    Args:
        tool_name: Name of the tool (skip, memorize, recall, guidelines, configuration)
        agent_name: Agent name to substitute in templates
        config_sections: Configuration sections for the configuration tool
        situation_builder_note: Situation builder note to include
        memory_subtitles: Available memory subtitles for the recall tool
        group_name: Optional group name to apply group-specific overrides
        provider: AI provider name ('claude', 'codex'). Defaults to 'claude'.

    Returns:
        Tool description string with variables substituted, or None if tool not found
    """
    # Handle guidelines tool specially - it loads from a separate file
    # (not defined in tools.yaml, loaded from guidelines_3rd.yaml)
    if tool_name == "guidelines":
        guidelines_config = get_guidelines_config()
        active_version = guidelines_config.get("active_version", "v1")
        version_config = guidelines_config.get(active_version, {})

        # Select provider-specific template
        # Map 'claude' to 'claudecode', 'codex' to 'codex'
        template_key = "codex" if provider == "codex" else "claudecode"
        template = version_config.get(template_key, "")

        # Fallback to 'claudecode' if provider-specific template not found
        if not template and template_key != "claudecode":
            template = version_config.get("claudecode", "")

        # Legacy fallback to 'template' key for older config versions
        if not template:
            template = version_config.get("template", "")

        # Substitute template variables
        description = template.format(agent_name=agent_name, situation_builder_note=situation_builder_note)
        return description

    # For other tools, load from tools.yaml (with optional group overrides)
    tools_config = _get_tools_config_for_group(group_name)

    if "tools" not in tools_config or tool_name not in tools_config["tools"]:
        logger.warning(f"Tool '{tool_name}' not found in configuration")
        return None

    tool_config = tools_config["tools"][tool_name]

    # Check if tool is enabled
    if not tool_config.get("enabled", True):
        logger.debug(f"Tool '{tool_name}' is disabled in configuration")
        return None

    # Get description from tools.yaml (or group override)
    description = tool_config.get("description", "")

    # Substitute template variables
    description = description.format(
        agent_name=agent_name,
        config_sections=config_sections,
        situation_builder_note=situation_builder_note,
        memory_subtitles=memory_subtitles,
    )

    return description


def get_tool_response(tool_name: str, group_name: Optional[str] = None, **kwargs) -> str:
    """
    Get the response message for a tool with variables substituted.

    Args:
        tool_name: Name of the tool
        group_name: Optional group name to apply group-specific overrides
        **kwargs: Variables to substitute in the response template

    Returns:
        Response string with variables substituted
    """
    tools_config = _get_tools_config_for_group(group_name)

    if "tools" not in tools_config or tool_name not in tools_config["tools"]:
        return "Tool response not configured."

    response_template = tools_config["tools"][tool_name].get("response", "")

    try:
        return response_template.format(**kwargs)
    except KeyError as e:
        logger.warning(f"Missing variable in tool response template: {e}")
        return response_template


def get_situation_builder_note(has_situation_builder: bool) -> str:
    """
    Get the situation builder note if enabled and needed.

    Args:
        has_situation_builder: Whether the room has a situation builder agent

    Returns:
        Situation builder note string or empty string
    """
    if not has_situation_builder:
        return ""

    context_config = get_conversation_context_config()

    if "situation_builder" not in context_config:
        return ""

    sb_config = context_config["situation_builder"]

    if not sb_config.get("enabled", False):
        return ""

    return sb_config.get("template", "")


def is_tool_enabled(tool_name: str) -> bool:
    """
    Check if a tool is enabled in configuration.

    Args:
        tool_name: Name of the tool

    Returns:
        True if tool is enabled, False otherwise
    """
    tools_config = get_tools_config()

    if "tools" not in tools_config or tool_name not in tools_config["tools"]:
        return False

    return tools_config["tools"][tool_name].get("enabled", True)


def get_tools_by_group(group_name: str) -> Dict[str, Dict[str, Any]]:
    """
    Get all tools that belong to a specific group.

    Args:
        group_name: Name of the group (e.g., "action", "character")

    Returns:
        Dictionary mapping tool names (short names like "skip", "memorize") to their config
    """
    tools_config = get_tools_config()

    if "tools" not in tools_config:
        return {}

    tools_in_group = {}
    for tool_name, tool_config in tools_config["tools"].items():
        if tool_config.get("group") == group_name:
            tools_in_group[tool_name] = tool_config

    return tools_in_group


def get_tool_names_by_group(group_name: str, enabled_only: bool = True) -> list[str]:
    """
    Get full MCP tool names for all tools in a specific group.

    Args:
        group_name: Name of the group (e.g., "action", "character")
        enabled_only: Only return enabled tools (default: True)

    Returns:
        List of full MCP tool names (e.g., ["mcp__action__skip", "mcp__action__memorize"])
    """
    tools_in_group = get_tools_by_group(group_name)

    tool_names = []
    for tool_name, tool_config in tools_in_group.items():
        # Check if tool is enabled (if enabled_only is True)
        if enabled_only and not is_tool_enabled(tool_name):
            continue

        # Get the full MCP name
        mcp_name = tool_config.get("name")
        if mcp_name:
            tool_names.append(mcp_name)

    return tool_names


def get_tool_group(tool_name: str) -> Optional[str]:
    """
    Get the group name for a specific tool.

    Args:
        tool_name: Name of the tool (short name like "skip" or "memorize")

    Returns:
        Group name (e.g., "action", "character") or None if not found
    """
    tools_config = get_tools_config()

    if "tools" not in tools_config or tool_name not in tools_config["tools"]:
        return None

    return tools_config["tools"][tool_name].get("group")
