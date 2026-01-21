"""
Codex provider implementation.

This module provides the Codex provider that uses a pool of `codex mcp-server`
connections for AI interactions. The pool architecture enables parallel request
handling for multi-agent conversations.

The provider abstraction layer enables seamless integration with the
multi-provider architecture.
"""

from .events import EventType, ItemType, agent_message, error, reasoning, thread_started, tool_call
from .mcp_client import CodexMCPClient, CodexMCPOptions
from .mcp_server_instance import CodexMCPServerInstance, ReasoningCapture
from .mcp_server_manager import CodexMCPServerManager, get_mcp_server_manager
from .mcp_server_pool import CodexServerPool, SelectionStrategy
from .parser import CodexStreamParser
from .pool import CodexClientPool
from .provider import CodexProvider

__all__ = [
    # Provider
    "CodexProvider",
    # Client
    "CodexMCPClient",
    "CodexMCPOptions",
    "CodexClientPool",
    # Server pool (recommended)
    "CodexServerPool",
    "SelectionStrategy",
    # Server instance
    "CodexMCPServerInstance",
    "ReasoningCapture",
    # Server management (legacy, deprecated)
    "CodexMCPServerManager",
    "get_mcp_server_manager",
    # Parser
    "CodexStreamParser",
    # Events
    "EventType",
    "ItemType",
    "thread_started",
    "agent_message",
    "reasoning",
    "error",
    "tool_call",
]
