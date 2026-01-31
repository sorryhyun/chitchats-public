"""
Shared MCP servers for ChitChats.

This module provides provider-agnostic MCP server implementations
that can be used by both Claude SDK and Codex providers.

Servers:
- action_server: skip, memorize, recall tools
- guidelines_server: read, anthropic tools
- etc_server: current_time tool
- social_server: moltbook (AI social network) tool

Each server supports two execution modes:
1. Subprocess mode (stdio) - for Claude SDK and Codex CLI
2. In-process mode - for testing or direct use
"""


# Lazy imports to avoid errors when servers don't exist yet
def __getattr__(name):
    if name == "create_action_server":
        from .action_server import create_action_server

        return create_action_server
    elif name == "create_guidelines_server":
        from .guidelines_server import create_guidelines_server

        return create_guidelines_server
    elif name == "create_etc_server":
        from .etc_server import create_etc_server

        return create_etc_server
    elif name == "create_social_server":
        from .social_server import create_social_server

        return create_social_server
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "create_action_server",
    "create_guidelines_server",
    "create_etc_server",
    "create_social_server",
]
