"""
Shared MCP Etc Server for ChitChats.

This server exposes utility tools (current_time) via the MCP protocol.
It can be used by any AI provider (Claude SDK, Codex CLI, etc.).

Usage:
    # Factory mode (in-process)
    from mcp_servers import create_etc_server
    server = create_etc_server(agent_name="TestAgent", provider="claude")

    # Subprocess mode (stdio)
    AGENT_NAME=TestAgent python -m mcp_servers.etc_server

Environment variables (for subprocess mode):
    AGENT_NAME: Name of the agent (required)
    AGENT_GROUP: Group name for tool config overrides (optional)
    PROVIDER: AI provider (optional, default: claude)
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

from domain.etc_models import CurrentTimeInput
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, ResourceTemplate, TextContent, Tool
from pydantic import AnyUrl

from .config import get_tool_description, get_tool_response, is_tool_enabled

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("EtcServer")


def create_etc_server(
    agent_name: str,
    group_name: Optional[str] = None,
    provider: str = "claude",
) -> Server:
    """
    Create an MCP server with utility tools (current_time).

    Args:
        agent_name: Name of the agent
        group_name: Optional group name for tool config overrides
        provider: AI provider ("claude" or "codex")

    Returns:
        Configured MCP Server instance
    """
    server = Server("etc")

    @server.list_tools()
    async def list_tools():
        """List available utility tools."""
        tools = []

        # Current time tool
        if is_tool_enabled("current_time", group_name=group_name, provider=provider):
            description = get_tool_description(
                "current_time", agent_name=agent_name, group_name=group_name, provider=provider
            )
            tools.append(
                Tool(
                    name="current_time",
                    description=description or "Get the current date and time",
                    inputSchema=CurrentTimeInput.model_json_schema(),
                )
            )

        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        """Handle tool calls."""
        if name == "current_time":
            now = datetime.now()
            time_str = now.strftime("%Y-%m-%d %H:%M:%S (%A)")

            response_text = get_tool_response(
                "current_time", group_name=group_name, provider=provider, current_time=time_str
            )
            return [TextContent(type="text", text=response_text)]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    # Resources (empty for etc server, but required for MCP compliance)
    @server.list_resources()
    async def list_resources():
        """List available resources (none for etc server)."""
        return []

    @server.read_resource()
    async def read_resource(uri: AnyUrl) -> str:
        """Read a resource by URI."""
        raise ValueError(f"Unknown resource URI: {uri}")

    @server.list_resource_templates()
    async def list_resource_templates():
        """List resource templates (none for etc server)."""
        return []

    return server


# =============================================================================
# Standalone Server Entry Point
# =============================================================================


def _get_env_config() -> dict:
    """Get configuration from environment variables."""
    return {
        "agent_name": os.environ.get("AGENT_NAME", "Agent"),
        "agent_group": os.environ.get("AGENT_GROUP"),
        "provider": os.environ.get("PROVIDER", "claude"),
    }


async def main():
    """Run the MCP server as a standalone process."""
    config = _get_env_config()
    logger.info("Starting ChitChats Etc MCP Server")
    logger.info(f"Agent: {config['agent_name']}, Group: {config['agent_group']}, Provider: {config['provider']}")

    server = create_etc_server(
        agent_name=config["agent_name"],
        group_name=config["agent_group"],
        provider=config["provider"],
    )

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
