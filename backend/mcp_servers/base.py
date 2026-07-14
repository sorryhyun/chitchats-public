"""
Shared plumbing for the ChitChats MCP servers.

Every server (action, guidelines, etc, social) exposes the same shape: it lists
the tools registered for its group in the tool registry, dispatches calls to a
handler, and can run either in-process or as a stdio subprocess. That shape lives
here; each server module supplies only its group name and its handlers.
"""

import asyncio
import inspect
import logging
import os
from typing import Awaitable, Callable, Optional, Union

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .config import (
    ToolDef,
    get_tool_description,
    get_tools_by_group,
    is_tool_enabled,
)

# Handlers receive the tool name (so one handler can serve several tools, as the
# guidelines server does for anthropic/openai) and may be sync or async.
ToolResult = list[TextContent]
Handler = Callable[[str, dict, dict], Union[ToolResult, Awaitable[ToolResult]]]


def setup_logging(logger_name: str) -> logging.Logger:
    """Configure logging for a standalone server process."""
    logging.basicConfig(level=logging.INFO)
    return logging.getLogger(logger_name)


logger = logging.getLogger("MCPServerBase")


def build_server(
    server_name: str,
    group: str,
    *,
    handlers: dict[str, Handler],
    context: dict,
    description_vars: Optional[dict[str, str]] = None,
    include_tool: Optional[Callable[[str, ToolDef], bool]] = None,
) -> Server:
    """
    Build an MCP server exposing the enabled tools of a single registry group.

    Args:
        server_name: MCP server name advertised to the client
        group: Tool registry group ("action", "guidelines", "etc", "social")
        handlers: Maps tool id to its handler; unmapped tools return "Unknown tool"
        context: Per-agent state passed to every handler (agent_name, agent_group, ...)
        description_vars: Extra template variables for tool descriptions
        include_tool: Optional filter applied after the enabled/provider check

    Returns:
        Configured MCP Server instance
    """
    server = Server(server_name)

    agent_name = context["agent_name"]
    group_name = context["agent_group"]
    provider = context["provider"]

    @server.list_tools()
    async def list_tools():
        tools = []

        for tool_id, tool_def in get_tools_by_group(group).items():
            if not is_tool_enabled(tool_id, group_name=group_name, provider=provider):
                continue

            if include_tool and not include_tool(tool_id, tool_def):
                continue

            description = get_tool_description(
                tool_id,
                agent_name=agent_name,
                group_name=group_name,
                provider=provider,
                **(description_vars or {}),
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
        handler = handlers.get(name)
        if handler is None:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

        result = handler(name, arguments, context)
        if inspect.isawaitable(result):
            result = await result
        return result

    return server


def env_config() -> dict:
    """Read the config every server takes from the subprocess environment."""
    return {
        "agent_name": os.environ.get("AGENT_NAME", "Agent"),
        "agent_group": os.environ.get("AGENT_GROUP"),
        "provider": os.environ.get("PROVIDER", "claude"),
    }


def run_stdio(label: str, factory: Callable[[dict], Server]) -> None:
    """
    Run a server as a standalone stdio process (the `python -m` entry point).

    Args:
        label: Human-readable server name for the startup logs
        factory: Builds the Server from the env config
    """

    async def _serve():
        config = env_config()
        logger.info(f"Starting ChitChats {label} MCP Server")
        logger.info(f"Agent: {config['agent_name']}, Group: {config['agent_group']}, Provider: {config['provider']}")

        server = factory(config)
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(_serve())
