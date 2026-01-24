"""
Claude-specific client pool implementation.

This module provides the ClaudeClientPool class for managing Claude SDK
client lifecycle with connection pooling.
"""

from __future__ import annotations

import asyncio
import logging

from claude_agent_sdk import ClaudeAgentOptions
from domain.task_identifier import TaskIdentifier

from providers.base_pool import BaseClientPool

from .client import ClaudeClient

logger = logging.getLogger("ClaudeClientPool")


class ClaudeClientPool(BaseClientPool[ClaudeClient, ClaudeAgentOptions]):
    """
    Claude-specific client pool.

    Manages pooling and lifecycle of Claude SDK clients with:
    - Concurrent connection management (semaphore)
    - Per-task locking to prevent duplicate client creation
    - Background cleanup of disconnected clients
    - Session ID tracking for client reuse decisions
    - Retry logic with exponential backoff for transport errors
    - Connection stabilization delay
    """

    # Stabilization delay after each connection (seconds)
    CONNECTION_STABILIZATION_DELAY = 0.05

    def _get_pool_name(self) -> str:
        """Get the pool name for logging."""
        return "ClaudeClientPool"

    def _get_session_id_from_options(self, options: ClaudeAgentOptions) -> str | None:
        """Extract session ID from Claude options (resume field)."""
        return getattr(options, "resume", None)

    def _get_session_id_from_client(self, client: ClaudeClient) -> str | None:
        """Extract session ID from Claude client."""
        if client.options:
            return getattr(client.options, "resume", None)
        return None

    async def _create_client_impl(
        self,
        task_id: TaskIdentifier,
        options: ClaudeAgentOptions,
    ) -> ClaudeClient:
        """Create and connect a new Claude client with retry logic.

        Implements exponential backoff for transport errors.
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                client = ClaudeClient(options)
                await client.connect()

                # Brief delay to let connection stabilize
                await asyncio.sleep(self.CONNECTION_STABILIZATION_DELAY)

                return client
            except Exception as e:
                error_str = str(e)
                if (
                    "ProcessTransport is not ready" in error_str or "transport" in error_str.lower()
                ) and attempt < max_retries - 1:
                    delay = 0.3 * (2**attempt)
                    self._logger.warning(
                        f"Connection failed for {task_id}, retrying in {delay}s (attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(delay)
                else:
                    raise

        raise RuntimeError(f"Failed to create client for {task_id} after {max_retries} retries")
