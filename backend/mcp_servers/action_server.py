"""
Shared MCP Action Server for ChitChats.

This server exposes action tools (skip, memorize, recall) via the MCP protocol.
It can be used by any AI provider (Claude SDK, Codex CLI, etc.).

Usage:
    # Factory mode (in-process)
    from mcp_servers import create_action_server
    server = create_action_server(agent_name="TestAgent", provider="claude")

    # Subprocess mode (stdio)
    AGENT_NAME=TestAgent python -m mcp_servers.action_server

Environment variables (for subprocess mode):
    AGENT_NAME: Name of the agent (required)
    AGENT_GROUP: Group name for tool config overrides (optional)
    AGENT_ID: Agent ID for cache invalidation (optional)
    CONFIG_FILE: Path to agent config folder (optional, for memorize)
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from domain.action_models import MemorizeInput, RecallInput, SkipInput
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .config import get_tool_description, get_tool_response, is_tool_enabled

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ActionServer")


def create_action_server(
    agent_name: str,
    agent_group: Optional[str] = None,
    agent_id: Optional[int] = None,
    config_file: Optional[str] = None,
    long_term_memory_index: Optional[dict[str, str]] = None,
    provider: str = "claude",
) -> Server:
    """
    Create an MCP server with action tools (skip, memorize, recall).

    Args:
        agent_name: Name of the agent
        agent_group: Optional group name for tool config overrides
        agent_id: Optional agent ID for cache invalidation
        config_file: Path to agent config folder (for memorize tool)
        long_term_memory_index: Optional dict mapping memory subtitles to content
        provider: AI provider ("claude" or "codex")

    Returns:
        Configured MCP Server instance
    """
    server = Server("action")

    # Use provided memory index or load from config file
    memory_index = long_term_memory_index or _load_memory_index(config_file)

    @server.list_tools()
    async def list_tools():
        """List available action tools."""
        tools = []

        # Skip tool
        if is_tool_enabled("skip", group_name=agent_group, provider=provider):
            description = get_tool_description("skip", agent_name=agent_name, group_name=agent_group, provider=provider)
            tools.append(
                Tool(
                    name="skip",
                    description=description or "Skip this turn",
                    inputSchema=SkipInput.model_json_schema(),
                )
            )

        # Memorize tool
        if is_tool_enabled("memorize", group_name=agent_group, provider=provider):
            description = get_tool_description(
                "memorize", agent_name=agent_name, group_name=agent_group, provider=provider
            )
            tools.append(
                Tool(
                    name="memorize",
                    description=description or "Record a memory",
                    inputSchema=MemorizeInput.model_json_schema(),
                )
            )

        # Recall tool - only if we have memory index
        if is_tool_enabled("recall", group_name=agent_group, provider=provider) and memory_index:
            memory_subtitles = ", ".join(f"'{s}'" for s in memory_index.keys())
            description = get_tool_description(
                "recall",
                agent_name=agent_name,
                memory_subtitles=memory_subtitles,
                group_name=agent_group,
                provider=provider,
            )
            tools.append(
                Tool(
                    name="recall",
                    description=description or "Recall a memory",
                    inputSchema=RecallInput.model_json_schema(),
                )
            )

        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        """Handle tool calls."""
        if name == "skip":
            return _handle_skip(agent_group, provider)

        elif name == "memorize":
            return await _handle_memorize(arguments, config_file, agent_id, agent_group, provider)

        elif name == "recall":
            return _handle_recall(arguments, memory_index, agent_group, provider)

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    return server


# =============================================================================
# Tool Handlers
# =============================================================================


def _handle_skip(group_name: Optional[str], provider: str) -> list[TextContent]:
    """Handle skip tool call."""
    response_text = get_tool_response("skip", group_name=group_name)
    return [TextContent(type="text", text=response_text)]


async def _handle_memorize(
    arguments: dict,
    config_file: Optional[str],
    agent_id: Optional[int],
    group_name: Optional[str],
    provider: str,
) -> list[TextContent]:
    """Handle memorize tool call."""
    memory_entry = arguments.get("memory_entry", "")
    if not memory_entry.strip():
        return [TextContent(type="text", text="Error: Memory entry cannot be empty")]

    if config_file:
        success = _append_to_recent_events(config_file, memory_entry)
        if success:
            # Invalidate cache if agent_id is available
            if agent_id:
                try:
                    from infrastructure.cache import agent_config_key, get_cache

                    cache = get_cache()
                    cache.invalidate(agent_config_key(agent_id))
                except Exception as e:
                    logger.warning(f"Failed to invalidate cache: {e}")

            response_text = get_tool_response("memorize", group_name=group_name, memory_entry=memory_entry)
        else:
            response_text = f"Failed to record memory: {memory_entry}"
    else:
        response_text = f"Memory noted (no config file): {memory_entry}"

    return [TextContent(type="text", text=response_text)]


def _handle_recall(
    arguments: dict,
    memory_index: dict[str, str],
    group_name: Optional[str],
    provider: str,
) -> list[TextContent]:
    """Handle recall tool call."""
    subtitle = arguments.get("subtitle", "")
    if not subtitle.strip():
        return [TextContent(type="text", text="Error: Subtitle cannot be empty")]

    if subtitle in memory_index:
        memory_content = memory_index[subtitle]
        response_text = get_tool_response("recall", group_name=group_name, memory_content=memory_content)
    else:
        available = ", ".join(f"'{s}'" for s in memory_index.keys())
        response_text = f"Memory subtitle '{subtitle}' not found. Available: {available}"

    return [TextContent(type="text", text=response_text)]


# =============================================================================
# Helper Functions
# =============================================================================


def _load_memory_index(config_file: Optional[str]) -> dict[str, str]:
    """Load memory index from agent's config folder."""
    if not config_file:
        return {}

    try:
        from config.parser import parse_long_term_memory
        from core import AgentConfigService

        project_root = AgentConfigService.get_project_root()
        config_path = project_root / config_file

        for filename in ["consolidated_memory.md", "long_term_memory.md"]:
            memory_file = config_path / filename
            if memory_file.exists():
                return parse_long_term_memory(memory_file)
    except Exception as e:
        logger.warning(f"Failed to load memory index: {e}")

    return {}


def _append_to_recent_events(config_file: str, memory_entry: str) -> bool:
    """Append memory entry to recent_events.md."""
    try:
        from core import AgentConfigService

        timestamp = datetime.now(timezone.utc)
        return AgentConfigService.append_to_recent_events(
            config_file=config_file,
            memory_entry=memory_entry,
            timestamp=timestamp,
        )
    except Exception as e:
        logger.error(f"Failed to append to recent_events: {e}")
        return False


# =============================================================================
# Standalone Server Entry Point
# =============================================================================


def _get_env_config() -> dict:
    """Get configuration from environment variables."""
    return {
        "agent_name": os.environ.get("AGENT_NAME", "Agent"),
        "agent_group": os.environ.get("AGENT_GROUP"),
        "agent_id": int(os.environ["AGENT_ID"]) if os.environ.get("AGENT_ID") else None,
        "config_file": os.environ.get("CONFIG_FILE"),
        "provider": os.environ.get("PROVIDER", "claude"),
    }


async def main():
    """Run the MCP server as a standalone process."""
    config = _get_env_config()
    logger.info("Starting ChitChats Action MCP Server")
    logger.info(f"Agent: {config['agent_name']}, Group: {config['agent_group']}, Provider: {config['provider']}")

    server = create_action_server(
        agent_name=config["agent_name"],
        agent_group=config["agent_group"],
        agent_id=config["agent_id"],
        config_file=config["config_file"],
        provider=config["provider"],
    )

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
