"""
Configuration validation and logging.

Provides functions for validating configuration schema and startup logging.
"""

import logging

from mcp_servers.config.loaders import (
    get_conversation_context_config,
    get_debug_config,
    get_guidelines_config,
    get_guidelines_file,
    get_tools_config,
)
from mcp_servers.config.tool_config import is_tool_enabled

from .cache import clear_cache

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

    # Validate tools.yaml
    tools_config = get_tools_config()
    if not tools_config:
        errors.append("tools.yaml is empty or missing")
    elif "tools" not in tools_config:
        errors.append("tools.yaml missing 'tools' section")
    else:
        # Check for required tools
        # Note: "guidelines" content comes from guidelines_3rd.yaml, not tools.yaml
        required_tools = ["skip", "memorize", "recall", "read"]
        for tool_name in required_tools:
            if tool_name not in tools_config["tools"]:
                errors.append(f"tools.yaml missing required tool: {tool_name}")
            else:
                tool = tools_config["tools"][tool_name]
                # Validate tool structure
                if "name" not in tool:
                    errors.append(f"tools.yaml tool '{tool_name}' missing 'name' field")
                # Tools must have either 'description' or 'source' (for loading from separate file)
                if "description" not in tool and "source" not in tool:
                    errors.append(f"tools.yaml tool '{tool_name}' missing 'description' or 'source' field")

    # Validate guidelines yaml (guidelines_3rd.yaml or guidelines_v2.yaml)
    guidelines_config = get_guidelines_config()
    guidelines_filename = f"{get_guidelines_file()}.yaml"
    if not guidelines_config:
        errors.append(f"{guidelines_filename} is empty or missing")
    else:
        # Check for active_version (guidelines template)
        if "active_version" not in guidelines_config:
            errors.append(f"{guidelines_filename} missing 'active_version' field")
        else:
            active_version = guidelines_config.get("active_version")
            if active_version not in guidelines_config:
                errors.append(f"{guidelines_filename} missing version section: {active_version}")
            else:
                version_config = guidelines_config[active_version]
                if "template" not in version_config:
                    errors.append(f"{guidelines_filename} version '{active_version}' missing 'template' field")

        # Check for system_prompt
        active_system_prompt = guidelines_config.get("active_system_prompt", "system_prompt")
        if active_system_prompt not in guidelines_config:
            errors.append(f"{guidelines_filename} missing system prompt: '{active_system_prompt}'")

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
        logger.error("Fix configuration files in backend/config/")
    else:
        logger.info("All configuration files validated successfully")

    # Log active configuration settings
    tools_config = get_tools_config()
    guidelines_config = get_guidelines_config()

    logger.info(f"Guidelines file: {get_guidelines_file()}.yaml")
    active_version = guidelines_config.get("active_version", "unknown")
    logger.info(f"Active guidelines version: {active_version}")

    # Log system prompt mode
    active_system_prompt = guidelines_config.get("active_system_prompt", "system_prompt")
    logger.info(f"Active system prompt: {active_system_prompt}")

    # Count enabled tools
    if "tools" in tools_config:
        enabled_tools = [name for name in tools_config["tools"].keys() if is_tool_enabled(name)]
        logger.info(f"Enabled tools: {len(enabled_tools)}/{len(tools_config['tools'])} ({', '.join(enabled_tools)})")
