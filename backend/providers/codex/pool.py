"""
Codex-specific client pool implementation.

This module provides the CodexClientPool class which extends BaseClientPool
with Codex CLI-specific client creation logic.

Note: Codex CLI spawns a new subprocess per query, so pooling is simpler.
The pool mainly tracks client instances for cleanup and interruption support.
"""

from __future__ import annotations

import logging

from core.client_pool import BaseClientPool
from providers.base import AIClient

from .client import CodexClient, CodexOptions

logger = logging.getLogger("CodexClientPool")


class CodexClientPool(BaseClientPool):
    """
    Codex-specific client pool.

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


# For backwards compatibility during transition
def create_codex_pool() -> CodexClientPool:
    """Factory function to create a CodexClientPool instance."""
    return CodexClientPool()
