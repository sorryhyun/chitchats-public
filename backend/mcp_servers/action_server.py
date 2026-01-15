"""
Standalone MCP server for action tools (skip, memorize, recall).

This server runs as a separate process for Codex CLI integration,
communicating via stdio using the MCP protocol.

Usage:
    python -m mcp_servers.action_server

Environment Variables:
    AGENT_NAME: Name of the agent (required)
    AGENT_GROUP: Group name for config overrides (optional)
    AGENT_ID: Agent ID for context (optional)
    CONFIG_FILE: Path to agent config directory (optional, relative to WORK_DIR)
    WORK_DIR: Working directory for resolving relative paths (optional, defaults to cwd)
    PROVIDER: AI provider name ('claude' or 'codex') for provider-specific configs (optional)
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Ensure backend is in path
backend_path = Path(__file__).parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from domain.action_models import MemorizeInput, RecallInput, SkipInput
from core.config import (
    clear_cache,
    get_tool_description,
    get_tool_response,
    is_tool_enabled,
)
from core.memory.parser import parse_long_term_memory
from core import get_settings

logger = logging.getLogger("ActionMCPServer")


def create_action_server(
    agent_name: str,
    agent_group: Optional[str] = None,
    agent_id: Optional[int] = None,
    config_file: Optional[str] = None,
    long_term_memory_index: Optional[dict[str, str]] = None,
    provider: str = "claude",
) -> Server:
    """Create an MCP server with action tools."""
    server = Server("action")
    memory_index = long_term_memory_index or {}

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        """Return list of available tools."""
        tools = []
        subtitles = list(memory_index.keys())
        memory_subtitles = ", ".join(subtitles) if subtitles else "None available"

        if is_tool_enabled("skip"):
            tools.append(types.Tool(
                name="skip",
                description=get_tool_description(
                    "skip",
                    agent_name=agent_name,
                    group_name=agent_group,
                    provider=provider,
                ) or "Skip responding to the current message.",
                inputSchema=SkipInput.model_json_schema(),
            ))

        if is_tool_enabled("memorize"):
            tools.append(types.Tool(
                name="memorize",
                description=get_tool_description(
                    "memorize",
                    agent_name=agent_name,
                    group_name=agent_group,
                    provider=provider,
                ) or "Record a new memory or observation for future reference.",
                inputSchema=MemorizeInput.model_json_schema(),
            ))

        if is_tool_enabled("recall"):
            tools.append(types.Tool(
                name="recall",
                description=get_tool_description(
                    "recall",
                    agent_name=agent_name,
                    memory_subtitles=memory_subtitles,
                    group_name=agent_group,
                    provider=provider,
                ) or f"Retrieve long-term memories by subtitle. Available: {memory_subtitles}",
                inputSchema=RecallInput.model_json_schema(),
            ))

        return tools

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        """Handle tool calls."""
        if name == "skip":
            response_text = get_tool_response("skip", group_name=agent_group, provider=provider)
            return [types.TextContent(type="text", text=response_text)]

        elif name == "memorize":
            validated = MemorizeInput(**arguments)
            memory_entry = validated.memory_entry

            # Write to recent_events.md if config_file is provided
            if config_file:
                config_path = Path(config_file)
                recent_events_path = config_path / "recent_events.md"

                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                new_entry = f"\n- [{timestamp}] {memory_entry}"

                try:
                    if not recent_events_path.exists():
                        recent_events_path.write_text(f"# Recent Events\n{new_entry}\n", encoding="utf-8")
                    else:
                        with open(recent_events_path, "a", encoding="utf-8") as f:
                            f.write(new_entry + "\n")

                    # Clear config cache so changes are picked up
                    clear_cache()

                    response_text = get_tool_response("memorize", group_name=agent_group, provider=provider)
                except Exception as e:
                    logger.error(f"Failed to write memory: {e}")
                    response_text = f"Failed to record memory: {e}"
            else:
                response_text = get_tool_response("memorize", group_name=agent_group, provider=provider)

            return [types.TextContent(type="text", text=response_text)]

        elif name == "recall":
            validated = RecallInput(**arguments)
            subtitle = validated.subtitle

            # Strip brackets if agent included them (e.g., "[memory_name]" -> "memory_name")
            if subtitle.startswith("[") and subtitle.endswith("]"):
                subtitle = subtitle[1:-1]

            if subtitle in memory_index:
                memory_content = memory_index[subtitle]
                response_text = get_tool_response("recall", group_name=agent_group, provider=provider)
                if "{memory_content}" in response_text:
                    response_text = response_text.replace("{memory_content}", memory_content)
                else:
                    response_text = f"{response_text}\n\n{memory_content}"
            else:
                available = list(memory_index.keys())
                response_text = f"Memory not found for subtitle '{subtitle}'. Available: {available}"

            return [types.TextContent(type="text", text=response_text)]

        else:
            raise ValueError(f"Unknown tool: {name}")

    return server


async def main():
    """Main entry point for the action MCP server."""
    # Configure logging to stderr
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )

    # Get configuration from environment
    agent_name = os.environ.get("AGENT_NAME", "Agent")
    agent_group = os.environ.get("AGENT_GROUP")
    agent_id_str = os.environ.get("AGENT_ID")
    config_file = os.environ.get("CONFIG_FILE")
    work_dir = os.environ.get("WORK_DIR")
    provider = os.environ.get("PROVIDER", "claude")

    agent_id = int(agent_id_str) if agent_id_str else None

    # Resolve config_file to absolute path using WORK_DIR
    # In bundled mode, WORK_DIR is where the exe is located (where agents folder lives)
    if config_file and work_dir:
        config_file = str(Path(work_dir) / config_file)
    elif config_file and not Path(config_file).is_absolute():
        # Fallback: use backend_path.parent (works in dev mode)
        config_file = str(backend_path.parent / config_file)

    logger.info(f"Starting action MCP server for agent: {agent_name} (provider: {provider})")
    if config_file:
        logger.info(f"Config file path: {config_file}")

    # Load long-term memory index from config file
    long_term_memory_index: dict[str, str] = {}
    if config_file:
        settings = get_settings()
        memory_filename = f"{settings.recall_memory_file}.md"
        memory_file_path = Path(config_file) / memory_filename
        long_term_memory_index = parse_long_term_memory(memory_file_path)
        if long_term_memory_index:
            logger.info(f"Loaded {len(long_term_memory_index)} memories from {memory_file_path}")
        else:
            logger.info(f"No memories found at {memory_file_path}")

    # Create server
    server = create_action_server(
        agent_name=agent_name,
        agent_group=agent_group,
        agent_id=agent_id,
        config_file=config_file,
        long_term_memory_index=long_term_memory_index,
        provider=provider,
    )

    # Run with stdio transport
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
