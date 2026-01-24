"""
Codex provider implementation.

This module provides the Codex provider that uses `codex app-server` with
JSON-RPC streaming for AI interactions. The provider abstraction layer
enables seamless integration with the multi-provider architecture.

The pool runs multiple server instances (configurable via CODEX_POOL_SIZE)
for parallel request processing with thread ID affinity routing.
"""

from providers.configs import CodexStartupConfig, CodexTurnConfig

# App Server components
from .app_server_client import CodexAppServerClient, CodexAppServerOptions
from .app_server_instance import CodexAppServerInstance
from .app_server_pool import CodexAppServerPool
from .constants import (
    AppServerMethod,
    EventType,
    ItemType,
    TurnStatus,
    map_approval_policy,
    map_sandbox,
)
from .parser import (
    AppServerStreamAccumulator,
    CodexStreamParser,
)
from .provider import CodexClientPool, CodexProvider
from .thread_manager import ThreadSessionManager

__all__ = [
    # Provider
    "CodexProvider",
    # Event types
    "EventType",
    "ItemType",
    "AppServerMethod",
    "TurnStatus",
    # Parser
    "CodexStreamParser",
    "AppServerStreamAccumulator",
    # Client pool
    "CodexClientPool",
    # App Server components
    "CodexAppServerClient",
    "CodexAppServerOptions",
    "CodexAppServerInstance",
    "CodexAppServerPool",
    "CodexStartupConfig",
    "CodexTurnConfig",
    # Thread management
    "ThreadSessionManager",
    # Format mappers
    "map_sandbox",
    "map_approval_policy",
]
