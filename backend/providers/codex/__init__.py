"""
Codex provider implementation.

This module provides the Codex provider that uses CLI subprocess or MCP server
for use with the ChitChats multi-provider abstraction layer.

Supports two modes:
    - CLI Mode (default): Spawns `codex exec` subprocess per query
    - MCP Mode: Uses persistent `codex mcp-server` connection

Set CODEX_USE_MCP=true to enable MCP mode.
"""

from .client import CodexClient
from .mcp_client import CodexMCPClient, CodexMCPOptions
from .mcp_server_manager import CodexMCPServerManager, get_mcp_server_manager
from .parser import CodexStreamParser
from .pool import CodexClientPool, CodexMCPClientPool
from .provider import CodexProvider

__all__ = [
    # CLI mode
    "CodexClient",
    "CodexClientPool",
    # MCP mode
    "CodexMCPClient",
    "CodexMCPClientPool",
    "CodexMCPOptions",
    "CodexMCPServerManager",
    "get_mcp_server_manager",
    # Common
    "CodexProvider",
    "CodexStreamParser",
]
