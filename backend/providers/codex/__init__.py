"""
Codex provider implementation.

This module provides the Codex provider that supports two modes:
1. MCP mode (default): Uses a pool of `codex mcp-server` connections
2. App Server mode: Uses `codex app-server` for better parallelism

Mode selection is controlled by USE_CODEX_APP_SERVER environment variable.

The provider abstraction layer enables seamless integration with the
multi-provider architecture.
"""

from .app_server_client import CodexAppServerClient, CodexAppServerOptions
from .app_server_instance import AppServerConfig, CodexAppServerInstance
from .app_server_parser import AppServerStreamAccumulator, parse_streaming_event
from .app_server_pool import CodexAppServerPool
from .events import (
    AppServerMethod,
    EventType,
    ItemType,
    SessionRecoveryError,
    TurnStatus,
    agent_message,
    error,
    reasoning,
    thread_started,
    tool_call,
)
from .format_mapper import map_approval_policy, map_sandbox
from .mcp_client import CodexMCPClient, CodexMCPOptions
from .mcp_server_instance import CodexMCPServerInstance, ReasoningCapture
from .mcp_server_manager import CodexMCPServerManager, get_mcp_server_manager
from .mcp_server_pool import CodexServerPool, SelectionStrategy
from .parser import CodexStreamParser
from .pool import CodexClientPool
from .provider import CodexProvider
from .windows_support import get_bundled_codex_path

__all__ = [
    # Provider
    "CodexProvider",
    # MCP Client (default mode)
    "CodexMCPClient",
    "CodexMCPOptions",
    "CodexClientPool",
    # App Server Client (parallel mode)
    "CodexAppServerClient",
    "CodexAppServerOptions",
    "CodexAppServerPool",
    "CodexAppServerInstance",
    "AppServerConfig",
    # App Server parsing
    "AppServerStreamAccumulator",
    "parse_streaming_event",
    # Format mapping
    "map_approval_policy",
    "map_sandbox",
    # Server pool (MCP mode - recommended)
    "CodexServerPool",
    "SelectionStrategy",
    # Server instance (MCP mode)
    "CodexMCPServerInstance",
    "ReasoningCapture",
    "get_bundled_codex_path",
    # Server management (legacy, deprecated)
    "CodexMCPServerManager",
    "get_mcp_server_manager",
    # Parser
    "CodexStreamParser",
    # Events
    "EventType",
    "ItemType",
    "AppServerMethod",
    "TurnStatus",
    "SessionRecoveryError",
    "thread_started",
    "agent_message",
    "reasoning",
    "error",
    "tool_call",
]
