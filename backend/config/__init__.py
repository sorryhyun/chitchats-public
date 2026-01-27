"""
Configuration module for ChitChats.

This module provides:
- Agent configuration parsing (from agents/*.md files)
- Memory parsing utilities
- Validation functions

Note: Tool and prompt configuration has moved to mcp_servers.config and providers/.
The following are re-exported for backward compatibility.
"""


# Lazy imports for all modules to avoid circular dependencies
def __getattr__(name):
    """Lazy import attributes to avoid circular imports."""
    # Parser functions (core agent parsing functionality)
    if name in ("list_available_configs", "parse_agent_config"):
        from . import parser

        return getattr(parser, name)

    # Memory parsing (now in parser.py)
    if name in ("get_memory_by_subtitle", "get_memory_subtitles", "parse_long_term_memory"):
        from . import parser

        return getattr(parser, name)

    # Validation
    if name in ("log_config_validation", "reload_all_configs", "validate_config_schema"):
        from . import validation

        return getattr(validation, name)

    # Deprecated: cache utilities - now in infrastructure.yaml_cache
    if name in ("_config_cache", "_get_file_mtime", "_load_yaml_file", "clear_cache", "get_cached_config"):
        from infrastructure import yaml_cache

        return getattr(yaml_cache, name)

    # Deprecated: build_system_prompt - now in providers.prompt_builder
    if name == "build_system_prompt":
        from providers import prompt_builder

        return prompt_builder.build_system_prompt

    # Deprecated: get_base_system_prompt - now in providers.prompt_builder
    if name == "get_base_system_prompt":
        from providers import prompt_builder

        return prompt_builder.get_base_system_prompt

    # Deprecated: loaders - now in mcp_servers.config
    if name in (
        "get_conversation_context_config",
        "get_debug_config",
        "get_extreme_traits",
        "get_group_config",
        "get_guidelines_config",
        "get_guidelines_config_path",
        "get_guidelines_file",
        "get_provider_prompts",
        "get_shared_prompts_config",
        "get_system_prompt_config",
        "merge_tool_configs",
    ):
        from mcp_servers.config import loaders

        return getattr(loaders, name)

    # Deprecated: tool config - now in mcp_servers.config.tools
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

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Agent config (core functionality - retained)
    "parse_agent_config",
    "list_available_configs",
    # Memory parser (core functionality - retained)
    "parse_long_term_memory",
    "get_memory_subtitles",
    "get_memory_by_subtitle",
    # Validation (core functionality - retained)
    "reload_all_configs",
    "validate_config_schema",
    "log_config_validation",
    # Deprecated: prompt building (moved to providers.prompt_builder)
    "build_system_prompt",
    "get_base_system_prompt",
    # Deprecated: cache (moved to infrastructure.yaml_cache)
    "_config_cache",
    "_get_file_mtime",
    "_load_yaml_file",
    "clear_cache",
    "get_cached_config",
    # Deprecated: loaders (moved to mcp_servers.config)
    "get_tools_config",
    "get_guidelines_config",
    "get_guidelines_config_path",
    "get_guidelines_file",
    "get_debug_config",
    "get_conversation_context_config",
    "get_provider_prompts",
    "get_shared_prompts_config",
    "get_system_prompt_config",
    "get_extreme_traits",
    "get_group_config",
    "merge_tool_configs",
    # Deprecated: tool config (moved to mcp_servers.config)
    "get_tool_description",
    "get_tool_response",
    "get_situation_builder_note",
    "is_tool_enabled",
    "get_tools_by_group",
    "get_tool_names_by_group",
    "get_tool_group",
]
