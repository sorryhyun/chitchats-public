"""
Codex-specific client pool implementations.

This module provides client pool classes for managing Codex client lifecycle:

- CodexClientPool: For CLI mode (subprocess per query)
- CodexMCPClientPool: For MCP mode (shared server connection)

Note: Codex CLI spawns a new subprocess per query, so pooling is simpler.
The pool mainly tracks client instances for cleanup and interruption support.
"""

from __future__ import annotations

import logging

from core.client_pool import BaseClientPool
from providers.base import AIClient

from .client import CodexClient, CodexOptions
from .mcp_client import CodexMCPClient, CodexMCPOptions

logger = logging.getLogger("CodexClientPool")


class CodexClientPool(BaseClientPool):
    """
    Codex-specific client pool for CLI mode.

    Extends BaseClientPool with Codex CLI client creation logic.
    Creates CodexClient instances that spawn CLI subprocesses.

    Note: Unlike Claude SDK which maintains persistent connections,
    Codex CLI spawns new subprocesses per query. The pool still provides
    value by tracking active clients for interruption and cleanup.
    """

    async def _create_client(self, options: CodexOptions) -> AIClient:
        """
        Create a new Codex client with the given options.

        Args:
            options: CodexOptions for client configuration

        Returns:
            Connected CodexClient instance ready for use
        """
        # Create client (validates codex CLI is available)
        client = CodexClient(options)

        # Connect (lightweight - just verifies CLI availability)
        await client.connect()

        logger.debug(f"Created and connected CodexClient with thread: {options.thread_id}")
        return client


class CodexMCPClientPool(BaseClientPool):
    """
    Codex MCP client pool for persistent server mode.

    Extends BaseClientPool with Codex MCP client creation logic.
    Creates CodexMCPClient instances that use the shared MCP server connection
    managed by CodexMCPServerManager.

    Unlike the CLI pool, the MCP pool uses a shared server connection
    for better performance (no subprocess spawn per query).
    """

    async def _create_client(self, options: CodexMCPOptions) -> AIClient:
        """
        Create a new Codex MCP client with the given options.

        Args:
            options: CodexMCPOptions for client configuration

        Returns:
            Connected CodexMCPClient instance ready for use
        """
        # Create MCP client (connects to shared MCP server manager)
        client = CodexMCPClient(options)

        # Connect (lightweight - gets the singleton MCP server manager)
        await client.connect()

        logger.debug(f"Created and connected CodexMCPClient with thread: {options.thread_id}")
        return client


# For backwards compatibility during transition
def create_codex_pool() -> CodexClientPool:
    """Factory function to create a CodexClientPool instance."""
    return CodexClientPool()


def create_codex_mcp_pool() -> CodexMCPClientPool:
    """Factory function to create a CodexMCPClientPool instance."""
    return CodexMCPClientPool()
