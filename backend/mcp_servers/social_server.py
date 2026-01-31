"""
Shared MCP Social Server for ChitChats.

This server exposes social network tools (Moltbook) via the MCP protocol.
It can be used by any AI provider (Claude SDK, Codex CLI, etc.).

Usage:
    # Factory mode (in-process)
    from mcp_servers import create_social_server
    server = create_social_server(agent_name="TestAgent", provider="claude")

    # Subprocess mode (stdio)
    AGENT_NAME=TestAgent python -m mcp_servers.social_server

Environment variables (for subprocess mode):
    AGENT_NAME: Name of the agent (required)
    AGENT_GROUP: Group name for tool config overrides (optional)
    PROVIDER: AI provider (optional, default: claude)
    MOLTBOOK_API_KEY: Moltbook API key (required for Moltbook tools)
"""

import asyncio
import json
import logging
import os
import urllib.error
import urllib.request
from typing import Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .config import (
    get_tool_description,
    get_tool_response,
    get_tools_by_group,
    is_tool_enabled,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SocialServer")


def create_social_server(
    agent_name: str,
    group_name: Optional[str] = None,
    provider: str = "claude",
) -> Server:
    """
    Create an MCP server with social network tools (Moltbook).

    Args:
        agent_name: Name of the agent
        group_name: Optional group name for tool config overrides
        provider: AI provider ("claude" or "codex")

    Returns:
        Configured MCP Server instance
    """
    server = Server("chitchats_social")

    # Context for tools
    context = {
        "agent_name": agent_name,
        "agent_group": group_name,
        "provider": provider,
    }

    @server.list_tools()
    async def list_tools():
        """List available social tools based on registry."""
        tools = []

        for tool_id, tool_def in get_tools_by_group("social").items():
            # Check if enabled for this provider/group
            if not is_tool_enabled(tool_id, group_name=group_name, provider=provider):
                continue

            # Get description with variable substitution
            description = get_tool_description(
                tool_id,
                agent_name=agent_name,
                group_name=group_name,
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
        if name == "moltbook":
            return _handle_moltbook(arguments, context)

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    return server


# =============================================================================
# Tool Handlers
# =============================================================================


def _handle_moltbook(arguments: dict, context: dict) -> list[TextContent]:
    """
    Handle Moltbook social network tool calls.

    Moltbook API base: https://www.moltbook.com/api/v1
    """
    api_key = os.environ.get("MOLTBOOK_API_KEY")
    if not api_key:
        return [
            TextContent(
                type="text",
                text="Error: MOLTBOOK_API_KEY not configured. Add it to your .env file.",
            )
        ]

    base_url = "https://www.moltbook.com/api/v1"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    action = arguments.get("action", "")

    try:
        if action == "browse_feed":
            sort = arguments.get("sort", "hot")
            limit = arguments.get("limit", 10)
            submolt = arguments.get("submolt")

            url = f"{base_url}/feed?sort={sort}&limit={limit}"
            if submolt:
                url += f"&submolt={submolt}"

            result = _moltbook_request("GET", url, headers)

        elif action == "create_post":
            title = arguments.get("title")
            content = arguments.get("content")
            submolt = arguments.get("submolt", "general")
            link_url = arguments.get("url")

            if not title or not content:
                return [
                    TextContent(
                        type="text",
                        text="Error: title and content are required for create_post",
                    )
                ]

            data = {"title": title, "content": content, "submolt": submolt}
            if link_url:
                data["url"] = link_url

            result = _moltbook_request("POST", f"{base_url}/posts", headers, data)

        elif action == "comment":
            post_id = arguments.get("post_id")
            content = arguments.get("content")
            parent_comment_id = arguments.get("parent_comment_id")

            if not post_id or not content:
                return [
                    TextContent(
                        type="text",
                        text="Error: post_id and content are required for comment",
                    )
                ]

            data = {"content": content}
            if parent_comment_id:
                data["parent_id"] = parent_comment_id

            result = _moltbook_request("POST", f"{base_url}/posts/{post_id}/comments", headers, data)

        elif action == "vote":
            post_id = arguments.get("post_id")
            comment_id = arguments.get("comment_id")
            direction = arguments.get("direction", "up")

            if direction not in ("up", "down"):
                return [TextContent(type="text", text="Error: direction must be 'up' or 'down'")]

            if post_id:
                result = _moltbook_request("POST", f"{base_url}/posts/{post_id}/vote?direction={direction}", headers)
            elif comment_id:
                result = _moltbook_request(
                    "POST", f"{base_url}/comments/{comment_id}/vote?direction={direction}", headers
                )
            else:
                return [TextContent(type="text", text="Error: either post_id or comment_id is required for vote")]

        elif action == "search":
            query = arguments.get("query")
            limit = arguments.get("limit", 10)

            if not query:
                return [TextContent(type="text", text="Error: query is required for search")]

            data = {"query": query, "limit": limit}
            result = _moltbook_request("POST", f"{base_url}/search", headers, data)

        elif action == "view_profile":
            name = arguments.get("name")
            if not name:
                return [TextContent(type="text", text="Error: name is required for view_profile")]

            result = _moltbook_request("GET", f"{base_url}/agents/profile?name={name}", headers)

        elif action == "list_submolts":
            limit = arguments.get("limit", 20)
            result = _moltbook_request("GET", f"{base_url}/submolts?limit={limit}", headers)

        elif action == "my_status":
            result = _moltbook_request("GET", f"{base_url}/agents/status", headers)

        else:
            return [TextContent(type="text", text=f"Error: Unknown action '{action}'")]

        response_text = get_tool_response(
            "moltbook",
            group_name=context["agent_group"],
            moltbook_response=result,
        )
        return [TextContent(type="text", text=response_text)]

    except Exception as e:
        logger.error(f"Moltbook API error: {e}")
        return [TextContent(type="text", text=f"Moltbook API error: {e}")]


def _moltbook_request(
    method: str,
    url: str,
    headers: dict,
    data: Optional[dict] = None,
) -> str:
    """Make an HTTP request to Moltbook API."""
    try:
        body = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            # Format response nicely for the agent
            return json.dumps(result, indent=2, ensure_ascii=False)

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        try:
            error_json = json.loads(error_body)
            return f"Moltbook API error ({e.code}): {json.dumps(error_json, indent=2)}"
        except json.JSONDecodeError:
            return f"Moltbook API error ({e.code}): {error_body}"
    except urllib.error.URLError as e:
        return f"Network error: {e.reason}"
    except Exception as e:
        return f"Request failed: {e}"


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
    logger.info("Starting ChitChats Social MCP Server")
    logger.info(f"Agent: {config['agent_name']}, Group: {config['agent_group']}, Provider: {config['provider']}")

    server = create_social_server(
        agent_name=config["agent_name"],
        group_name=config["agent_group"],
        provider=config["provider"],
    )

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
