"""
SDK Configuration module.

Provides functions for loading and managing YAML configuration files:
- Tool descriptions, schemas, and groupings
- Guidelines and system prompt templates
- Debug settings
- Conversation context configuration

Configuration files are located in backend/config/*.yaml
"""

# Re-export from cache
from .cache import (
    _config_cache,
    _get_file_mtime,
    _load_yaml_file,
    clear_cache,
    get_cached_config,
)

# Re-export from loaders
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

# Re-export from tool_config
from .tool_config import (
    get_situation_builder_note,
    get_tool_description,
    get_tool_group,
    get_tool_names_by_group,
    get_tool_response,
    get_tools_by_group,
    is_tool_enabled,
)

# Re-export from validation
from .validation import (
    log_config_validation,
    reload_all_configs,
    validate_config_schema,
)

__all__ = [
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
]
