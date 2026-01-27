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

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, ResourceTemplate, TextContent, Tool
from pydantic import AnyUrl

from .config import (
    get_tool_description,
    get_tool_response,
    get_tools_by_group,
    is_tool_enabled,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ActionServer")


def create_action_server(
    agent_name: str,
    agent_group: Optional[str] = None,
    agent_id: Optional[int] = None,
    config_file: Optional[str] = None,
    long_term_memory_index: Optional[dict[str, str]] = None,
    long_term_memory_entries: Optional[dict] = None,
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
        long_term_memory_entries: Optional dict mapping subtitles to MemoryEntry objects (with thoughts)
        provider: AI provider ("claude" or "codex")

    Returns:
        Configured MCP Server instance
    """
    server = Server("action")

    # Use provided memory entries/index or load from config file
    memory_entries = long_term_memory_entries
    memory_index = long_term_memory_index

    if memory_entries is None and memory_index is None:
        memory_index, memory_entries = _load_memory_index_and_entries(config_file)
    elif memory_entries is not None and memory_index is None:
        # Build index from entries
        memory_index = {k: v.content for k, v in memory_entries.items()}
    elif memory_index is None:
        memory_index = {}

    # Context for tools
    context = {
        "agent_name": agent_name,
        "agent_group": agent_group,
        "agent_id": agent_id,
        "config_file": config_file,
        "memory_index": memory_index,
        "memory_entries": memory_entries,
        "provider": provider,
    }

    @server.list_tools()
    async def list_tools():
        """List available action tools based on registry."""
        tools = []

        for tool_id, tool_def in get_tools_by_group("action").items():
            # Check if enabled for this provider/group
            if not is_tool_enabled(tool_id, group_name=agent_group, provider=provider):
                continue

            # Check requirements (e.g., recall needs memory_index)
            if "memory_index" in tool_def.requires and not memory_index:
                continue

            # Get description with variable substitution
            # Generate memory subtitles with thoughts preview if available
            if memory_entries:
                # Use thoughts as previews: [subtitle]: "thought"
                preview_parts = []
                for subtitle, entry in memory_entries.items():
                    if entry.thoughts:
                        preview_parts.append(f"[{subtitle}]: \"{entry.thoughts}\"")
                    else:
                        preview_parts.append(f"'{subtitle}'")
                memory_subtitles = ", ".join(preview_parts)
            elif memory_index:
                memory_subtitles = ", ".join(f"'{s}'" for s in memory_index.keys())
            else:
                memory_subtitles = ""

            description = get_tool_description(
                tool_id,
                agent_name=agent_name,
                memory_subtitles=memory_subtitles,
                group_name=agent_group,
                provider=provider,
            )

            tools.append(
                Tool(
                    name=tool_id,
                    description=description or tool_def.description,
                    inputSchema=tool_def.input_model.model_json_schema(),
                )
            )

        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        """Handle tool calls."""
        if name == "skip":
            return _handle_skip(context)

        elif name == "memorize":
            return await _handle_memorize(arguments, context)

        elif name == "recall":
            return _handle_recall(arguments, context)

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    # Resources for memory access
    @server.list_resources()
    async def list_resources():
        """List available memory resources."""
        resources = []

        for subtitle in memory_index.keys():
            resources.append(
                Resource(
                    uri=AnyUrl(f"memory://{agent_name}/{subtitle}"),
                    name=subtitle,
                    description=f"Memory: {subtitle}",
                    mimeType="text/plain",
                )
            )

        return resources

    @server.read_resource()
    async def read_resource(uri: AnyUrl) -> str:
        """Read a memory resource by URI."""
        uri_str = str(uri)
        prefix = f"memory://{agent_name}/"
        if not uri_str.startswith(prefix):
            raise ValueError(f"Invalid resource URI: {uri_str}")

        subtitle = uri_str[len(prefix) :]

        if subtitle not in memory_index:
            raise ValueError(f"Memory not found: {subtitle}")

        return memory_index[subtitle]

    @server.list_resource_templates()
    async def list_resource_templates():
        """List resource templates for dynamic memory access."""
        templates = []

        if memory_index:
            available = ", ".join(memory_index.keys())
            templates.append(
                ResourceTemplate(
                    uriTemplate=f"memory://{agent_name}/{{subtitle}}",
                    name="Agent Memory",
                    description=f"Access {agent_name}'s memories. Available: {available}",
                    mimeType="text/plain",
                )
            )

        return templates

    return server


# =============================================================================
# Tool Handlers
# =============================================================================


def _handle_skip(context: dict) -> list[TextContent]:
    """Handle skip tool call."""
    response_text = get_tool_response("skip", group_name=context["agent_group"])
    return [TextContent(type="text", text=response_text)]


async def _handle_memorize(arguments: dict, context: dict) -> list[TextContent]:
    """Handle memorize tool call."""
    memory_entry = arguments.get("memory_entry", "")
    if not memory_entry.strip():
        return [TextContent(type="text", text="Error: Memory entry cannot be empty")]

    config_file = context["config_file"]
    agent_id = context["agent_id"]
    agent_group = context["agent_group"]

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

            response_text = get_tool_response("memorize", group_name=agent_group, memory_entry=memory_entry)
        else:
            response_text = f"Failed to record memory: {memory_entry}"
    else:
        response_text = f"Memory noted (no config file): {memory_entry}"

    return [TextContent(type="text", text=response_text)]


def _handle_recall(arguments: dict, context: dict) -> list[TextContent]:
    """Handle recall tool call."""
    subtitle = arguments.get("subtitle", "")
    if not subtitle.strip():
        return [TextContent(type="text", text="Error: Subtitle cannot be empty")]

    memory_index = context["memory_index"]
    agent_group = context["agent_group"]

    if subtitle in memory_index:
        memory_content = memory_index[subtitle]
        response_text = get_tool_response("recall", group_name=agent_group, memory_content=memory_content)
    else:
        available = ", ".join(f"'{s}'" for s in memory_index.keys())
        response_text = f"Memory subtitle '{subtitle}' not found. Available: {available}"

    return [TextContent(type="text", text=response_text)]


# =============================================================================
# Helper Functions
# =============================================================================


def _load_memory_index_and_entries(config_file: Optional[str]) -> tuple[dict[str, str], Optional[dict]]:
    """Load memory index and entries from agent's config folder.

    Args:
        config_file: Path to agent config folder

    Returns:
        Tuple of (memory_index, memory_entries)
        - memory_index: Dict mapping subtitles to content (thoughts stripped)
        - memory_entries: Dict mapping subtitles to MemoryEntry objects (or None if feature disabled)
    """
    if not config_file:
        return {}, None

    try:
        from domain.agent_parser import parse_long_term_memory, parse_long_term_memory_with_thoughts
        from core import AgentConfigService
        from core.settings import get_settings

        project_root = AgentConfigService.get_project_root()
        config_path = project_root / config_file
        settings = get_settings()

        for filename in ["consolidated_memory.md", "long_term_memory.md"]:
            memory_file = config_path / filename
            if memory_file.exists():
                if settings.memory_preview_with_thoughts:
                    # Parse with thoughts extraction
                    memory_entries = parse_long_term_memory_with_thoughts(memory_file)
                    memory_index = {k: v.content for k, v in memory_entries.items()}
                    return memory_index, memory_entries
                else:
                    # Legacy parsing without thoughts
                    memory_index = parse_long_term_memory(memory_file)
                    return memory_index, None
    except Exception as e:
        logger.warning(f"Failed to load memory index: {e}")

    return {}, None


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
