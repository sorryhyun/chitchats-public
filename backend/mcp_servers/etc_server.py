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

from datetime import datetime
from typing import Optional

from mcp.server import Server
from mcp.types import TextContent

from .base import build_server, run_stdio, setup_logging
from .config import get_tool_response

logger = setup_logging("EtcServer")


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
    return build_server(
        "chitchats_etc",
        "etc",
        handlers={"current_time": _handle_current_time},
        context={
            "agent_name": agent_name,
            "agent_group": group_name,
            "provider": provider,
        },
    )


# =============================================================================
# Tool Handlers
# =============================================================================


def _handle_current_time(_name: str, _arguments: dict, context: dict) -> list[TextContent]:
    """Handle current_time tool call."""
    now = datetime.now()
    time_str = now.strftime("%Y-%m-%d %H:%M:%S (%A)")

    response_text = get_tool_response(
        "current_time",
        group_name=context["agent_group"],
        current_time=time_str,
    )
    return [TextContent(type="text", text=response_text)]


# =============================================================================
# Standalone Server Entry Point
# =============================================================================


def from_env(config: dict) -> Server:
    """Build the etc server from the subprocess environment."""
    return create_etc_server(
        agent_name=config["agent_name"],
        group_name=config["agent_group"],
        provider=config["provider"],
    )


if __name__ == "__main__":
    run_stdio("Etc", from_env)
