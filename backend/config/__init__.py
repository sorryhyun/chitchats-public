"""
Configuration module for the backend application.

This module provides:
1. Agent configuration parsing (from markdown files)
2. YAML configuration loading with caching (tools, guidelines, debug settings)
3. Tool configuration functions (descriptions, responses, groupings)
4. Memory parsing utilities
"""

# Agent configuration (markdown-based)
from .agent_io import AgentConfigIO
from .constants import (
    DEFAULT_FALLBACK_PROMPT,
    get_base_system_prompt,
)
from .parser import list_available_configs, parse_agent_config
from .prompt_builder import build_system_prompt

# YAML configuration caching
from .cache import (
    _config_cache,
    _get_file_mtime,
    _load_yaml_file,
    clear_cache,
    get_cached_config,
)

# YAML configuration loaders
from .loaders import (
    get_conversation_context_config,
    get_debug_config,
    get_extreme_traits,
    get_group_config,
    get_guidelines_config,
    get_guidelines_config_path,
    get_guidelines_file,
    get_provider_tools_config,
    get_tools_config,
    merge_tool_configs,
)

# Tool configuration functions
from .tool_config import (
    get_situation_builder_note,
    get_tool_description,
    get_tool_group,
    get_tool_names_by_group,
    get_tool_response,
    get_tools_by_group,
    is_tool_enabled,
)

# Configuration validation
from .validation import (
    log_config_validation,
    reload_all_configs,
    validate_config_schema,
)

# Memory parsing
from .memory_parser import (
    get_memory_by_subtitle,
    get_memory_subtitles,
    parse_long_term_memory,
)

__all__ = [
    # Agent configuration
    "parse_agent_config",
    "list_available_configs",
    "get_base_system_prompt",
    "DEFAULT_FALLBACK_PROMPT",
    "build_system_prompt",
    "AgentConfigIO",
    # Cache
    "_config_cache",
    "_get_file_mtime",
    "_load_yaml_file",
    "clear_cache",
    "get_cached_config",
    # Loaders
    "get_tools_config",
    "get_provider_tools_config",
    "get_guidelines_config",
    "get_guidelines_config_path",
    "get_guidelines_file",
    "get_debug_config",
    "get_conversation_context_config",
    "get_extreme_traits",
    "get_group_config",
    "merge_tool_configs",
    # Tool config
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
    # Memory parsing
    "parse_long_term_memory",
    "get_memory_subtitles",
    "get_memory_by_subtitle",
]
