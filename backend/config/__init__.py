"""
Configuration module for ChitChats.

This module provides:
- Agent configuration parsing (from agents/*.md files)
- YAML configuration loading and caching (tools, guidelines, debug, etc.)
- Tool configuration and descriptions
- Memory parsing utilities
- Prompt building utilities

Note: Tool-related config has moved to mcp_servers.config but is re-exported here
for backward compatibility.
"""


# Lazy imports for all modules to avoid circular dependencies
def __getattr__(name):
    """Lazy import attributes to avoid circular imports."""
    # Constants
    if name == "get_base_system_prompt":
        from . import constants

        return constants.get_base_system_prompt

    # Parser
    if name in ("list_available_configs", "parse_agent_config"):
        from . import parser

        return getattr(parser, name)

    # Cache utilities
    if name in ("_config_cache", "_get_file_mtime", "_load_yaml_file", "clear_cache", "get_cached_config"):
        from . import cache

        return getattr(cache, name)

    # Loaders - now in mcp_servers.config
    if name in (
        "get_conversation_context_config",
        "get_debug_config",
        "get_extreme_traits",
        "get_group_config",
        "get_guidelines_config",
        "get_guidelines_config_path",
        "get_guidelines_file",
        "get_tools_config",
        "merge_tool_configs",
    ):
        from mcp_servers.config import loaders

        return getattr(loaders, name)

    # Tool config - now in mcp_servers.config.tools
    if name in (
        "get_situation_builder_note",
        "get_tool_description",
        "get_tool_group",
        "get_tool_names_by_group",
        "get_tool_response",
        "get_tools_by_group",
        "is_tool_enabled",
    ):
        from mcp_servers.config import tools

        return getattr(tools, name)

    # Validation
    if name in ("log_config_validation", "reload_all_configs", "validate_config_schema"):
        from . import validation

        return getattr(validation, name)

    # Memory parsing (now in parser.py)
    if name in ("get_memory_by_subtitle", "get_memory_subtitles", "parse_long_term_memory"):
        from . import parser

        return getattr(parser, name)

    # Prompt builder
    if name == "build_system_prompt":
        from . import prompt_builder

        return prompt_builder.build_system_prompt

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Agent config
    "parse_agent_config",
    "list_available_configs",
    "get_base_system_prompt",
    # Cache
    "_config_cache",
    "_get_file_mtime",
    "_load_yaml_file",
    "clear_cache",
    "get_cached_config",
    # Loaders (from mcp_servers.config)
    "get_tools_config",
    "get_guidelines_config",
    "get_guidelines_config_path",
    "get_guidelines_file",
    "get_debug_config",
    "get_conversation_context_config",
    "get_extreme_traits",
    "get_group_config",
    "merge_tool_configs",
    # Tool config (from mcp_servers.config)
    "get_tool_description",
    "get_tool_response",
    "get_situation_builder_note",
    "is_tool_enabled",
    "get_tools_by_group",
    "get_tool_names_by_group",
    "get_tool_group",
    # Validation
    "reload_all_configs",
    "validate_config_schema",
    "log_config_validation",
    # Memory parser
    "parse_long_term_memory",
    "get_memory_subtitles",
    "get_memory_by_subtitle",
    # Prompt builder
    "build_system_prompt",
]
