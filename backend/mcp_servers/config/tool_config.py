"""
Tool configuration functions.

This module provides a thin wrapper around the tools.py registry,
adding special handling for guidelines loading from separate YAML file.
"""

import logging
from typing import Optional

from .loaders import get_guidelines_config
from .tools import (
    TOOLS,
    ToolDef,
    get_situation_builder_note,
    get_tool_group,
    get_tool_input_model,
    get_tool_names_by_group,
    get_tools_by_group,
    is_tool_enabled,
)
from .tools import get_tool_description as _get_tool_description_base
from .tools import get_tool_response as _get_tool_response_base

logger = logging.getLogger(__name__)

# Re-export from tools.py
__all__ = [
    "TOOLS",
    "ToolDef",
    "get_tool_description",
    "get_tool_response",
    "get_situation_builder_note",
    "is_tool_enabled",
    "get_tools_by_group",
    "get_tool_names_by_group",
    "get_tool_group",
    "get_tool_input_model",
]


def get_tool_description(
    tool_name: str,
    agent_name: str = "",
    config_sections: str = "",  # Legacy, unused
    situation_builder_note: str = "",
    memory_subtitles: str = "",
    group_name: Optional[str] = None,
    provider: str = "claude",
) -> Optional[str]:
    """
    Get a tool description with template variables substituted.

    This wraps the base function to handle the special "guidelines" tool
    which loads content from a separate YAML file.

    Args:
        tool_name: Name of the tool (skip, memorize, recall, guidelines, etc.)
        agent_name: Agent name to substitute in templates
        config_sections: Legacy parameter, unused
        situation_builder_note: Situation builder note to include
        memory_subtitles: Available memory subtitles for the recall tool
        group_name: Optional group name to apply group-specific overrides
        provider: The AI provider ("claude" or "codex")

    Returns:
        Tool description string with variables substituted, or None if tool not found
    """
    # Handle guidelines tool specially - it loads from a separate file
    # (not defined in tools registry, loaded from guidelines.yaml)
    if tool_name == "guidelines":
        guidelines_config = get_guidelines_config()
        active_version = guidelines_config.get("active_version", "v1")
        version_config = guidelines_config.get(active_version, {})

        # For Codex provider, try to use the codex variant first
        if provider == "codex" and "codex" in version_config:
            template = version_config.get("codex", "")
            logger.debug(f"Using Codex-specific guidelines template for version {active_version}")
        else:
            template = version_config.get("template", "")

        # Substitute template variables
        description = template.format(agent_name=agent_name, situation_builder_note=situation_builder_note)
        return description

    # For other tools, use the base function from tools.py
    return _get_tool_description_base(
        tool_name=tool_name,
        agent_name=agent_name,
        memory_subtitles=memory_subtitles,
        situation_builder_note=situation_builder_note,
        group_name=group_name,
        provider=provider,
    )


def get_tool_response(
    tool_name: str,
    group_name: Optional[str] = None,
    **kwargs,
) -> str:
    """
    Get the response message for a tool with variables substituted.

    Args:
        tool_name: Name of the tool
        group_name: Optional group name to apply group-specific overrides
        **kwargs: Variables to substitute in the response template

    Returns:
        Response string with variables substituted
    """
    return _get_tool_response_base(tool_name=tool_name, group_name=group_name, **kwargs)
