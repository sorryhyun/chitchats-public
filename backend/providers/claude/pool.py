"""
Claude-specific client pool implementation.

This module provides the ClaudeClientPool class which extends BaseClientPool
with Claude SDK-specific client creation logic.
"""

from __future__ import annotations

import logging

from claude_agent_sdk import ClaudeAgentOptions
from core.client_pool import BaseClientPool

from providers.base import AIClient

from .client import ClaudeClient

logger = logging.getLogger("ClaudeClientPool")


class ClaudeClientPool(BaseClientPool):
    """
    Claude-specific client pool.

    Extends BaseClientPool with Claude SDK client creation logic.
    Creates ClaudeClient instances that wrap ClaudeSDKClient.
    """

    async def _create_client(self, options: ClaudeAgentOptions) -> AIClient:
        """
        Create a new Claude client with the given options.

        Args:
            options: ClaudeAgentOptions for client configuration

        Returns:
            Connected ClaudeClient instance ready for use
        """
        # Create client wrapper
        client = ClaudeClient(options)

        # Connect (spawns Claude Code CLI subprocess)
        await client.connect()

        logger.debug(f"Created and connected ClaudeClient with session: {options.resume}")
        return client


# For backwards compatibility during transition
def create_claude_pool() -> ClaudeClientPool:
    """Factory function to create a ClaudeClientPool instance."""
    return ClaudeClientPool()
