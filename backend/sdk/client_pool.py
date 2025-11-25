"""
Client pool for managing Claude SDK client lifecycle and pooling.

This module provides the ClientPool class which manages the lifecycle of
ClaudeSDKClient instances, implementing connection pooling to avoid spawning
multiple CLI processes unnecessarily.

SDK Best Practice: Reuse ClaudeSDKClient instances within sessions to avoid
spawning multiple CLI processes. Each client maintains conversation context
across queries.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Tuple

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from domain.task_identifier import TaskIdentifier

logger = logging.getLogger("ClientPool")

# Pool configuration defaults
DEFAULT_MAX_POOL_SIZE = 50  # Maximum number of concurrent clients
DEFAULT_LOCK_TIMEOUT = 30.0  # Seconds to wait for connection lock


class ClientPool:
    """
    Manages pooling and lifecycle of Claude SDK clients.

    SDK Best Practice: Reuse ClaudeSDKClient instances within sessions
    to avoid spawning multiple CLI processes. Each client maintains
    conversation context across queries.

    Pool Strategy:
        - Key: TaskIdentifier(room_id, agent_id)
        - Value: ClaudeSDKClient instance
        - Max Size: Configurable limit to prevent resource exhaustion
        - LRU Eviction: Oldest client evicted when pool is full
        - Lock Timeout: Prevents deadlocks during client creation
        - Cleanup: Background disconnect to avoid cancel scope issues
    """

    def __init__(self, max_size: int = DEFAULT_MAX_POOL_SIZE, lock_timeout: float = DEFAULT_LOCK_TIMEOUT):
        """
        Initialize the client pool.

        Args:
            max_size: Maximum number of clients in the pool (default: 50)
            lock_timeout: Timeout in seconds for acquiring connection lock (default: 30.0)
        """
        self.pool: dict[TaskIdentifier, ClaudeSDKClient] = {}
        self._last_used: dict[TaskIdentifier, float] = {}  # Track last access time for LRU eviction
        self._connection_lock = asyncio.Lock()
        self._cleanup_tasks: set[asyncio.Task] = set()
        self._max_size = max_size
        self._lock_timeout = lock_timeout

    async def _evict_lru_client(self) -> None:
        """Evict the least recently used client to make room for new ones."""
        if not self._last_used:
            return

        # Find the oldest client
        oldest_task_id = min(self._last_used.keys(), key=lambda k: self._last_used[k])
        logger.info(f"🗑️ Pool full ({len(self.pool)}/{self._max_size}), evicting LRU client: {oldest_task_id}")
        await self.cleanup(oldest_task_id)

    async def get_or_create(self, task_id: TaskIdentifier, options: ClaudeAgentOptions) -> Tuple[ClaudeSDKClient, bool]:
        """
        Get existing client or create new one.

        Args:
            task_id: Identifier for this agent task
            options: SDK client configuration

        Returns:
            (client, is_new) tuple
            - client: ClaudeSDKClient instance
            - is_new: True if newly created, False if reused from pool

        Raises:
            asyncio.TimeoutError: If lock acquisition times out

        SDK Best Practice: Use lock to prevent ProcessTransport race
        conditions when creating multiple clients concurrently.
        """
        # Check if client exists outside the lock (fast path)
        if task_id in self.pool:
            existing_client = self.pool[task_id]
            old_session_id = (
                getattr(existing_client.options, "resume", None) if hasattr(existing_client, "options") else None
            )
            new_session_id = getattr(options, "resume", None)

            logger.debug(f"Client exists for {task_id} | Old session: {old_session_id} | New session: {new_session_id}")

            # If session changed (especially from something to None), recreate the client
            if old_session_id != new_session_id and (old_session_id is not None or new_session_id is not None):
                logger.info(
                    f"Session changed for {task_id} (old: {old_session_id}, new: {new_session_id}), recreating client"
                )
                await self.cleanup(task_id)
                # Fall through to create new client below
            else:
                logger.debug(f"Reusing existing client for {task_id}")
                # Update options for the existing client (in case system prompt changed)
                self.pool[task_id].options = options
                # Update last used time
                self._last_used[task_id] = time.monotonic()
                return self.pool[task_id], False

        # Use lock with timeout to prevent concurrent client creation/connection
        # This prevents "ProcessTransport is not ready for writing" errors
        try:
            async with asyncio.timeout(self._lock_timeout):
                async with self._connection_lock:
                    # Double-check after acquiring lock (another coroutine might have created it)
                    if task_id in self.pool:
                        existing_client = self.pool[task_id]
                        old_session_id = (
                            getattr(existing_client.options, "resume", None)
                            if hasattr(existing_client, "options")
                            else None
                        )
                        new_session_id = getattr(options, "resume", None)

                        # If session changed, cleanup and recreate
                        if old_session_id != new_session_id and (
                            old_session_id is not None or new_session_id is not None
                        ):
                            logger.info(f"Session changed for {task_id} while waiting for lock, recreating client")
                            await self.cleanup(task_id)
                            # Continue to create new client below
                        else:
                            logger.debug(f"Client for {task_id} was created while waiting for lock")
                            self.pool[task_id].options = options
                            self._last_used[task_id] = time.monotonic()
                            return self.pool[task_id], False

                    # Check pool size and evict LRU if needed
                    if len(self.pool) >= self._max_size:
                        await self._evict_lru_client()

                    logger.debug(f"Creating new client for {task_id}")

                    # Retry connection with exponential backoff to handle ProcessTransport race conditions
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            client = ClaudeSDKClient(options=options)
                            # Connect without a prompt - messages are sent via query() instead
                            await client.connect()
                            self.pool[task_id] = client
                            self._last_used[task_id] = time.monotonic()

                            # Brief delay to let ProcessTransport stabilize before next connection
                            await asyncio.sleep(0.1)

                            return client, True
                        except Exception as e:
                            if "ProcessTransport is not ready" in str(e) and attempt < max_retries - 1:
                                delay = 0.5 * (2**attempt)  # Exponential backoff: 0.5s, 1s
                                logger.warning(
                                    f"Connection failed for {task_id}, retrying in {delay}s "
                                    f"(attempt {attempt + 1}/{max_retries})"
                                )
                                await asyncio.sleep(delay)
                            else:
                                # Re-raise on final attempt or non-transport errors
                                raise

                    # Should not reach here, but satisfy type checker
                    raise RuntimeError(f"Failed to create client for {task_id} after {max_retries} attempts")

        except asyncio.TimeoutError:
            logger.error(f"⏰ Timeout acquiring connection lock for {task_id} after {self._lock_timeout}s")
            raise asyncio.TimeoutError(f"Timeout acquiring connection lock for {task_id}")

    async def cleanup(self, task_id: TaskIdentifier):
        """
        Remove and cleanup a specific client.

        Args:
            task_id: Identifier for the client to cleanup

        SDK Best Practice: Disconnect in background task to avoid
        cancel scope issues. The cleanup happens outside the current
        async context to prevent premature cancellation.
        """
        if task_id not in self.pool:
            return

        logger.info(f"🧹 Cleaning up client for {task_id}")
        client = self.pool[task_id]

        # Remove from pool and last_used tracking
        del self.pool[task_id]
        self._last_used.pop(task_id, None)

        # Schedule disconnect in a background task (separate from HTTP request task)
        # This ensures disconnect runs in its own async context, avoiding cancel scope violations
        task = asyncio.create_task(self._disconnect_client_background(client, task_id))

        # Track the cleanup task
        self._cleanup_tasks.add(task)
        # Remove from tracking when done
        task.add_done_callback(self._cleanup_tasks.discard)

        logger.info(f"✅ Cleaned up client for {task_id}")

    async def cleanup_room(self, room_id: int):
        """
        Cleanup all clients for a specific room.

        Args:
            room_id: Room ID to cleanup
        """
        tasks_to_cleanup = [task_id for task_id in self.pool.keys() if task_id.room_id == room_id]
        for task_id in tasks_to_cleanup:
            await self.cleanup(task_id)

    async def shutdown_all(self):
        """
        Graceful shutdown of all clients.

        SDK Best Practice: Wait for all cleanup tasks to complete
        before final shutdown to prevent resource leaks.
        """
        logger.info(f"🛑 Shutting down ClientPool with {len(self.pool)} pooled clients")

        # Cleanup all clients
        task_ids = list(self.pool.keys())
        for task_id in task_ids:
            await self.cleanup(task_id)

        # Wait for background cleanup tasks
        if self._cleanup_tasks:
            logger.info(f"⏳ Waiting for {len(self._cleanup_tasks)} cleanup tasks to complete")
            await asyncio.gather(*self._cleanup_tasks, return_exceptions=True)

        logger.info("✅ ClientPool shutdown complete")

    def get_keys_for_agent(self, agent_id: int) -> list[TaskIdentifier]:
        """
        Get all pool keys for a specific agent.

        Args:
            agent_id: Agent ID to filter

        Returns:
            List of TaskIdentifiers for this agent

        Used by agent_service.py for agent cleanup.
        """
        return [task_id for task_id in self.pool.keys() if task_id.agent_id == agent_id]

    def keys(self):
        """
        Get all pool keys.

        Returns:
            Dict keys view of all TaskIdentifiers in the pool
        """
        return self.pool.keys()

    def get_stats(self) -> dict:
        """
        Get pool statistics for monitoring.

        Returns:
            Dictionary containing pool stats:
            - size: Current number of clients in pool
            - max_size: Maximum pool size
            - pending_cleanup: Number of cleanup tasks in progress
            - lock_timeout: Lock timeout in seconds
        """
        return {
            "size": len(self.pool),
            "max_size": self._max_size,
            "pending_cleanup": len(self._cleanup_tasks),
            "lock_timeout": self._lock_timeout,
        }

    async def _disconnect_client_background(self, client: ClaudeSDKClient, task_id: TaskIdentifier):
        """
        Background task for client disconnection.

        Isolated in separate async task to avoid cancel scope issues.

        Args:
            client: The client to disconnect
            task_id: Identifier for logging purposes
        """
        try:
            if hasattr(client, "disconnect"):
                await client.disconnect()
                logger.debug(f"Disconnected client for {task_id}")
            elif hasattr(client, "close"):
                await client.close()
                logger.debug(f"Closed client for {task_id}")
        except Exception as e:
            # Suppress cancel scope errors - these can still happen if the client's
            # internal state is tied to a completed task
            error_msg = str(e).lower()
            if "cancel scope" not in error_msg and "cancelled" not in error_msg:
                logger.warning(f"Error disconnecting client {task_id}: {e}")
