"""
Configuration validation and logging.

Provides functions for validating configuration schema and startup logging.
"""

import logging

from infrastructure.yaml_cache import clear_cache

from .loaders import (
    get_conversation_context_config,
    get_debug_config,
    get_tools_config,
)
from .tools import is_tool_enabled

logger = logging.getLogger(__name__)


def reload_all_configs():
    """Force reload all configuration files by clearing the cache."""
    clear_cache()
    logger.info("Reloaded all configuration files")


def validate_config_schema() -> list[str]:
    """
    Validate configuration files have required keys and structure.

    Returns:
        List of validation errors (empty if all valid)
    """
    errors = []

    # Validate tools registry (Python-based, from tools.py)
    tools_config = get_tools_config()
    if not tools_config:
        errors.append("Tools registry is empty")
    elif "tools" not in tools_config:
        errors.append("Tools registry missing 'tools' section")
    else:
        # Check for required tools
        required_tools = ["skip", "memorize", "recall"]
        for tool_name in required_tools:
            if tool_name not in tools_config["tools"]:
                errors.append(f"Tools registry missing required tool: {tool_name}")
            else:
                tool = tools_config["tools"][tool_name]
                # Validate tool structure
                if "name" not in tool:
                    errors.append(f"Tools registry tool '{tool_name}' missing 'name' field")
                # Tools must have description
                if "description" not in tool:
                    errors.append(f"Tools registry tool '{tool_name}' missing 'description' field")

    # Note: guidelines and system_prompt live in the provider-specific prompts.yaml files
    # (providers/claude/prompts.yaml and providers/codex/prompts.yaml)

    # Validate debug.yaml
    debug_config = get_debug_config()
    if not debug_config:
        errors.append("debug.yaml is empty or missing")
    elif "debug" not in debug_config:
        errors.append("debug.yaml missing 'debug' section")

    # Validate conversation_context.yaml
    context_config = get_conversation_context_config()
    if not context_config:
        errors.append("conversation_context.yaml is empty or missing")

    return errors


def log_config_validation():
    """
    Validate and log configuration status at startup.

    This should be called once during application initialization.
    """
    logger.info("Validating YAML configuration files...")

    errors = validate_config_schema()

    if errors:
        logger.error("Configuration validation failed:")
        for error in errors:
            logger.error(f"   - {error}")
        logger.error("Fix configuration files in mcp_servers/config/")
    else:
        logger.info("All configuration files validated successfully")

    # Log active configuration settings
    tools_config = get_tools_config()

    # Count enabled tools
    if "tools" in tools_config:
        enabled_tools = [name for name in tools_config["tools"].keys() if is_tool_enabled(name)]
        logger.info(f"Enabled tools: {len(enabled_tools)}/{len(tools_config['tools'])} ({', '.join(enabled_tools)})")
