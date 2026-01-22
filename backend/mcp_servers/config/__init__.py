"""
Tool configuration for MCP servers.

This module provides configuration loading and tool description functions
used by the shared MCP servers.
"""

from .loaders import (
    get_conversation_context_config,
    get_debug_config,
    get_extreme_traits,
    get_group_config,
    get_guidelines_config,
    get_guidelines_config_path,
    get_guidelines_file,
    merge_tool_configs,
)
from .tools import (
    TOOLS,
    CurrentTimeInput,
    GuidelinesAnthropicInput,
    GuidelinesReadInput,
    MemorizeInput,
    RecallInput,
    SkipInput,
    ToolDef,
    get_situation_builder_note,
    get_tool_description,
    get_tool_group,
    get_tool_input_model,
    get_tool_names_by_group,
    get_tool_response,
    get_tools_by_group,
    is_tool_enabled,
)

__all__ = [
    # Loaders
    "get_guidelines_config",
    "get_guidelines_config_path",
    "get_guidelines_file",
    "get_debug_config",
    "get_conversation_context_config",
    "get_extreme_traits",
    "get_group_config",
    "merge_tool_configs",
    # Tool config
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
    # Input models
    "SkipInput",
    "MemorizeInput",
    "RecallInput",
    "GuidelinesReadInput",
    "GuidelinesAnthropicInput",
    "CurrentTimeInput",
]
