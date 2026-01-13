"""
Debug logging utilities for agent input/output debugging.

This module provides functions to write agent inputs and outputs to debug files
for debugging purposes. Configuration is loaded from debug.yaml.
"""

import logging
import os
from datetime import datetime

from claude_agent_sdk import ClaudeAgentOptions
from core.config import get_debug_config

logger = logging.getLogger("DebugLogger")


async def _extract_tools_from_mcp_server(server_dict: dict) -> list:
    """
    Extract tool information from an MCP server.

    Args:
        server_dict: MCP server dictionary with 'instance' key

    Returns:
        List of Tool objects with name, description, and inputSchema
    """
    try:
        instance = server_dict.get("instance")
        if not instance:
            return []

        # Get the list_tools handler
        from mcp.types import ListToolsRequest

        if ListToolsRequest not in instance.request_handlers:
            return []

        handler = instance.request_handlers[ListToolsRequest]
        request = ListToolsRequest()
        result = await handler(request)

        # Extract tools from the result
        # Result is a pydantic model with a 'root' attribute
        if hasattr(result, "root") and hasattr(result.root, "tools"):
            return result.root.tools
        elif hasattr(result, "tools"):
            return result.tools

        return []
    except Exception as e:
        logger.warning(f"Failed to extract tools from MCP server: {e}")
        return []


async def write_debug_log(
    agent_name: str,
    task_id: str,
    system_prompt: str,
    message_to_send: str,
    config_data: dict,
    options: ClaudeAgentOptions,
    has_situation_builder: bool = False,
):
    """
    Write complete agent input to debug file for debugging purposes.
    Logs the ACTUAL system prompt and tools from ClaudeAgentOptions object.
    Configuration and output format are loaded from debug.yaml.
    """
    # Load debug configuration
    config = get_debug_config()
    debug_settings = config.get("debug", {})

    # Check if debug logging is enabled
    if not debug_settings.get("enabled", False):
        return

    logging_config = debug_settings.get("logging", {})
    format_config = debug_settings.get("format", {})

    # Check what to log
    if not logging_config.get("input", {}).get("system_prompt", True):
        return  # Skip if input logging is disabled

    try:
        # Get output file path from configuration
        output_file = debug_settings.get("output_file", "debug.txt")
        debug_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), output_file)

        # Get format settings
        separator = format_config.get("separator", "=")
        separator_length = format_config.get("separator_length", 80)
        separator_line = separator * separator_length

        with open(debug_file_path, "a", encoding="utf-8") as f:
            f.write("\n" + separator_line + "\n")

            # Write timestamp if enabled
            if format_config.get("timestamp", True):
                f.write(f"TIMESTAMP: {datetime.now().isoformat()}\n")

            # Write agent name if enabled
            if format_config.get("include_agent_name", True):
                f.write(f"AGENT: {agent_name}\n")

            # Write task ID if enabled
            if format_config.get("include_task_id", True):
                f.write(f"TASK_ID: {task_id}\n")

            f.write(separator_line + "\n\n")

            # Write ACTUAL system prompt from options (not reconstructed)
            if logging_config.get("input", {}).get("system_prompt", True):
                f.write("--- ACTUAL SYSTEM PROMPT (from ClaudeAgentOptions) ---\n")
                f.write(options.system_prompt if hasattr(options, "system_prompt") else system_prompt)
                f.write("\n\n")

            # Write ACTUAL tool configuration from options
            if logging_config.get("input", {}).get("tool_descriptions", True):
                f.write("--- ACTUAL TOOL CONFIGURATION (from ClaudeAgentOptions) ---\n\n")

                # Write model
                if hasattr(options, "model"):
                    f.write(f"MODEL: {options.model}\n")

                # Write session ID if present
                if hasattr(options, "resume") and options.resume:
                    f.write(f"SESSION ID: {options.resume}\n")

                f.write("\n")

                # Extract and write actual tool descriptions from MCP servers
                if hasattr(options, "mcp_servers") and options.mcp_servers:
                    f.write("TOOLS AVAILABLE TO AGENT:\n\n")

                    # Get tools from each MCP server
                    try:
                        for server_name, server_config in options.mcp_servers.items():
                            # Extract tools from MCP server
                            tools = await _extract_tools_from_mcp_server(server_config)

                            if tools:
                                f.write(f"[{server_name.upper()} SERVER]\n")
                                for tool in tools:
                                    tool_name = tool.name if hasattr(tool, "name") else str(tool)
                                    tool_desc = tool.description if hasattr(tool, "description") else "No description"
                                    f.write(f"\nTool: {tool_name}\n")
                                    f.write(f"Description: {tool_desc}\n")

                                    # Write input schema if available
                                    if hasattr(tool, "inputSchema") and tool.inputSchema:
                                        f.write(f"Input Schema: {tool.inputSchema}\n")

                                f.write("\n")
                    except Exception as e:
                        logger.warning(f"Failed to extract tool descriptions: {e}")
                        f.write(f"(Failed to extract tool descriptions: {e})\n\n")

                # Write allowed/disallowed tools summary
                if hasattr(options, "allowed_tools") and options.allowed_tools:
                    f.write("ALLOWED TOOLS (names only):\n")
                    for tool_name in options.allowed_tools:
                        f.write(f"  - {tool_name}\n")
                    f.write("\n")

                if hasattr(options, "disallowed_tools") and options.disallowed_tools:
                    f.write("DISALLOWED TOOLS:\n")
                    for tool_name in options.disallowed_tools:
                        f.write(f"  - {tool_name}\n")
                    f.write("\n")

            # Write message content if enabled
            if logging_config.get("input", {}).get("message_content", True):
                f.write("--- MESSAGE TO SEND (including conversation history) ---\n")
                f.write(message_to_send)
                f.write("\n\n")

            f.write(separator_line + "\n\n")

        logger.info(f"📝 Debug log written to {debug_file_path}")
    except Exception as e:
        logger.warning(f"Failed to write debug log: {e}")


def append_response_to_debug_log(agent_name: str, task_id: str, response_text: str, thinking_text: str, skipped: bool):
    """
    Append agent's response to debug file.
    Configuration and output format are loaded from debug.yaml.
    """
    # Load debug configuration
    config = get_debug_config()
    debug_settings = config.get("debug", {})

    # Check if debug logging is enabled
    if not debug_settings.get("enabled", False):
        return

    logging_config = debug_settings.get("logging", {})
    format_config = debug_settings.get("format", {})

    # Check what to log
    output_config = logging_config.get("output", {})
    if not output_config.get("response_text", True):
        return  # Skip if output logging is disabled

    try:
        # Get output file path from configuration
        output_file = debug_settings.get("output_file", "debug.txt")
        debug_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), output_file)

        # Get format settings
        separator = format_config.get("separator", "=")
        separator_length = format_config.get("separator_length", 80)
        separator_line = separator * separator_length

        with open(debug_file_path, "a", encoding="utf-8") as f:
            # Write header
            header_parts = ["--- AGENT RESPONSE"]
            if format_config.get("include_agent_name", True):
                header_parts.append(f"AGENT: {agent_name}")
            if format_config.get("include_task_id", True):
                header_parts.append(f"TASK_ID: {task_id}")
            f.write(f"{', '.join(header_parts)} ---\n\n")

            # Write skipped status if applicable and enabled
            if skipped and output_config.get("skipped_status", True):
                f.write("[AGENT SKIPPED THIS TURN]\n\n")
            else:
                # Write thinking text if enabled
                if thinking_text and output_config.get("thinking_text", True):
                    f.write("THINKING:\n")
                    f.write(thinking_text)
                    f.write("\n\n")

                # Write response text if enabled
                if output_config.get("response_text", True):
                    f.write("RESPONSE:\n")
                    f.write(response_text if response_text else "[No response text]")
                    f.write("\n\n")

            f.write(separator_line + "\n\n")

        logger.info("📝 Agent response appended to debug log")
    except Exception as e:
        logger.warning(f"Failed to append response to debug log: {e}")
