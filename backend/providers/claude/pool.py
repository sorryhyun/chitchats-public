"""
Claude-specific client pool implementation.

This module provides the ClaudeClientPool class for managing Claude SDK
client lifecycle with connection pooling.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Tuple

from claude_agent_sdk import ClaudeAgentOptions
from domain.task_identifier import TaskIdentifier

from providers.base import AIClient, ClientPoolInterface

from .client import ClaudeClient

logger = logging.getLogger("ClaudeClientPool")


class ClaudeClientPool(ClientPoolInterface):
    """
    Claude-specific client pool.

    Manages pooling and lifecycle of Claude SDK clients with:
    - Concurrent connection management (semaphore)
    - Per-task locking to prevent duplicate client creation
    - Background cleanup of disconnected clients
    - Session ID tracking for client reuse decisions
    """

    # Allow up to 10 concurrent connections
    MAX_CONCURRENT_CONNECTIONS = 10
    # Stabilization delay after each connection (seconds)
    CONNECTION_STABILIZATION_DELAY = 0.05
    # Timeout for disconnect operations (seconds)
    DISCONNECT_TIMEOUT = 5.0

    def __init__(self):
        """Initialize the client pool."""
        self._pool: dict[TaskIdentifier, ClaudeClient] = {}
        self._connection_semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_CONNECTIONS)
        self._task_locks: dict[TaskIdentifier, asyncio.Lock] = {}
        self._cleanup_tasks: set[asyncio.Task] = set()

    @property
    def pool(self) -> dict:
        """Get the underlying pool dictionary."""
        return self._pool

    def _get_task_lock(self, task_id: TaskIdentifier) -> asyncio.Lock:
        """Get or create a per-task_id lock."""
        if task_id not in self._task_locks:
            self._task_locks[task_id] = asyncio.Lock()
        return self._task_locks[task_id]

    async def get_or_create(
        self,
        task_id: TaskIdentifier,
        options: ClaudeAgentOptions,
    ) -> Tuple[AIClient, bool]:
        """Get existing client or create new one.

        Args:
            task_id: Identifier for this agent task
            options: ClaudeAgentOptions for client configuration

        Returns:
            (client, is_new) tuple
        """
        # Check if client exists (fast path)
        if task_id in self._pool:
            existing_client = self._pool[task_id]
            old_session_id = getattr(existing_client.options, "resume", None) if existing_client.options else None
            new_session_id = getattr(options, "resume", None)

            logger.debug(f"Client exists for {task_id} | Old session: {old_session_id} | New session: {new_session_id}")

            # If session changed, recreate the client
            if old_session_id != new_session_id and (old_session_id is not None or new_session_id is not None):
                logger.info(f"Session changed for {task_id}, recreating client")
                self._remove_from_pool(task_id)
            else:
                logger.debug(f"Reusing existing client for {task_id}")
                self._pool[task_id].options = options
                return self._pool[task_id], False

        # Use per-task lock to prevent duplicate client creation
        task_lock = self._get_task_lock(task_id)
        async with task_lock:
            # Double-check after acquiring lock
            if task_id in self._pool:
                existing_client = self._pool[task_id]
                old_session_id = getattr(existing_client.options, "resume", None) if existing_client.options else None
                new_session_id = getattr(options, "resume", None)

                if old_session_id != new_session_id and (old_session_id is not None or new_session_id is not None):
                    logger.info(f"Session changed for {task_id} while waiting for lock, recreating client")
                    self._remove_from_pool(task_id)
                else:
                    logger.debug(f"Client for {task_id} was created while waiting for lock")
                    self._pool[task_id].options = options
                    return self._pool[task_id], False

            # Use semaphore to limit overall connection concurrency
            async with self._connection_semaphore:
                logger.debug(f"Creating new Claude client for {task_id}")

                # Retry connection with exponential backoff
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        client = ClaudeClient(options)
                        await client.connect()
                        self._pool[task_id] = client

                        # Brief delay to let connection stabilize
                        await asyncio.sleep(self.CONNECTION_STABILIZATION_DELAY)

                        return client, True
                    except Exception as e:
                        error_str = str(e)
                        if (
                            "ProcessTransport is not ready" in error_str or "transport" in error_str.lower()
                        ) and attempt < max_retries - 1:
                            delay = 0.3 * (2**attempt)
                            logger.warning(
                                f"Connection failed for {task_id}, retrying in {delay}s (attempt {attempt + 1}/{max_retries})"
                            )
                            await asyncio.sleep(delay)
                        else:
                            raise

                raise RuntimeError(f"Failed to create client for {task_id} after {max_retries} retries")

    def _remove_from_pool(self, task_id: TaskIdentifier):
        """Remove a client from the pool without calling disconnect."""
        if task_id not in self._pool:
            return
        logger.info(f"Removing client from pool for {task_id}")
        del self._pool[task_id]

    async def cleanup(self, task_id: Any) -> None:
        """Remove and cleanup a specific client."""
        if task_id not in self._pool:
            return

        logger.info(f"Cleaning up client for {task_id}")
        client = self._pool[task_id]
        del self._pool[task_id]

        # Schedule disconnect in background task
        task = asyncio.create_task(self._disconnect_client_background(client, task_id))
        self._cleanup_tasks.add(task)
        task.add_done_callback(self._cleanup_tasks.discard)

    async def cleanup_room(self, room_id: int) -> None:
        """Cleanup all clients for a specific room."""
        tasks_to_cleanup = [task_id for task_id in self._pool.keys() if task_id.room_id == room_id]
        for task_id in tasks_to_cleanup:
            await self.cleanup(task_id)

    async def shutdown_all(self) -> None:
        """Graceful shutdown of all clients."""
        logger.info(f"Shutting down ClaudeClientPool with {len(self._pool)} pooled clients")

        task_ids = list(self._pool.keys())
        for task_id in task_ids:
            await self.cleanup(task_id)

        if self._cleanup_tasks:
            logger.info(f"Waiting for {len(self._cleanup_tasks)} cleanup tasks to complete")
            await asyncio.gather(*self._cleanup_tasks, return_exceptions=True)

        logger.info("ClaudeClientPool shutdown complete")

    def get_keys_for_agent(self, agent_id: int) -> list[TaskIdentifier]:
        """Get all pool keys for a specific agent."""
        return [task_id for task_id in self._pool.keys() if task_id.agent_id == agent_id]

    def keys(self):
        """Get all pool keys."""
        return self._pool.keys()

    async def _disconnect_client_background(self, client: ClaudeClient, task_id: TaskIdentifier):
        """Background task for client disconnection with timeout."""
        try:
            await asyncio.wait_for(
                asyncio.shield(client.disconnect()),
                timeout=self.DISCONNECT_TIMEOUT,
            )
            logger.debug(f"Disconnected client for {task_id}")
        except asyncio.TimeoutError:
            logger.warning(f"Timeout disconnecting client {task_id}")
        except asyncio.CancelledError:
            logger.debug(f"Disconnect cancelled for {task_id}")
        except Exception as e:
            error_msg = str(e).lower()
            if "cancel scope" not in error_msg and "cancelled" not in error_msg:
                logger.warning(f"Error disconnecting client {task_id}: {e}")
