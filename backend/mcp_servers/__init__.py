"""
Standalone MCP servers for Codex integration.

This package provides MCP server entry points that can be run as
separate processes for Codex CLI integration. These servers implement
the same tools as the Claude SDK MCP servers but run standalone.

Usage:
    python -m mcp_servers.action_server
    python -m mcp_servers.guidelines_server

Environment Variables:
    AGENT_NAME: Name of the agent (required)
    AGENT_GROUP: Group name for config overrides (optional)
    AGENT_ID: Agent ID for context (optional)
    ROOM_ID: Room ID for context (optional)
"""
