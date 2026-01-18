"""
Codex MCP client pool implementation.

This module provides the client pool class for managing Codex MCP client lifecycle.
Uses a shared MCP server connection for all queries.
"""

from __future__ import annotations

import logging

from core.client_pool import BaseClientPool
from providers.base import AIClient

from .mcp_client import CodexMCPClient, CodexMCPOptions

logger = logging.getLogger("CodexMCPClientPool")


class CodexMCPClientPool(BaseClientPool):
    """
    Codex MCP client pool for persistent server mode.

    Extends BaseClientPool with Codex MCP client creation logic.
    Creates CodexMCPClient instances that use the shared MCP server connection
    managed by CodexMCPServerManager.

    Unlike subprocess-based approaches, the MCP pool uses a shared server connection
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


def create_codex_mcp_pool() -> CodexMCPClientPool:
    """Factory function to create a CodexMCPClientPool instance."""
    return CodexMCPClientPool()
