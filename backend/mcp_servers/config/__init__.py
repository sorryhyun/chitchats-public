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
    get_provider_prompts,
    get_shared_prompts_config,
)
from .tools import (
    TOOLS,
    CurrentTimeInput,
    GuidelinesAnthropicInput,
    MemorizeInput,
    MoltbookInput,
    RecallInput,
    SkipInput,
    ToolDef,
    get_tool_description,
    get_tool_group,
    get_tool_input_model,
    get_tool_names_by_group,
    get_tool_response,
    get_tools_by_group,
    is_tool_enabled,
)
from .validation import (
    log_config_validation,
    reload_all_configs,
    validate_config_schema,
)

__all__ = [
    # Loaders
    "get_debug_config",
    "get_conversation_context_config",
    "get_provider_prompts",
    "get_shared_prompts_config",
    "get_extreme_traits",
    "get_group_config",
    # Tool config
    "TOOLS",
    "ToolDef",
    "get_tool_description",
    "get_tool_response",
    "is_tool_enabled",
    "get_tools_by_group",
    "get_tool_names_by_group",
    "get_tool_group",
    "get_tool_input_model",
    # Input models
    "SkipInput",
    "MemorizeInput",
    "RecallInput",
    "GuidelinesAnthropicInput",
    "CurrentTimeInput",
    "MoltbookInput",
    # Validation
    "reload_all_configs",
    "validate_config_schema",
    "log_config_validation",
]
