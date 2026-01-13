"""
Client pool base class for managing AI client lifecycle and pooling.

This module provides the BaseClientPool abstract class which manages the lifecycle of
AI client instances (Claude, Codex, etc.), implementing connection pooling
to avoid spawning multiple CLI processes unnecessarily.

Each provider implements their own pool by extending BaseClientPool and implementing
the _create_client() method.

Best Practice: Reuse client instances within sessions to avoid spawning
multiple CLI processes. Each client maintains conversation context across
queries.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Tuple

from domain.task_identifier import TaskIdentifier
from providers.base import AIClient, ClientPoolInterface

logger = logging.getLogger("ClientPool")


class BaseClientPool(ClientPoolInterface, ABC):
    """
    Abstract base class for AI client pooling.

    Manages pooling and lifecycle of AI clients with shared logic for:
    - Concurrent connection management (semaphore)
    - Per-task locking to prevent duplicate client creation
    - Background cleanup of disconnected clients
    - Session ID extraction for client reuse decisions

    Provider-specific pools (ClaudeClientPool, CodexClientPool) extend this
    and implement _create_client() for their specific client creation logic.

    Pool Strategy:
        - Key: TaskIdentifier(room_id, agent_id)
        - Value: AIClient instance
        - Cleanup: Background disconnect to avoid cancel scope issues
        - Concurrency: Semaphore allows up to MAX_CONCURRENT_CONNECTIONS simultaneous connections
    """

    # Allow up to 10 concurrent connections (prevents ProcessTransport issues while allowing parallelism)
    MAX_CONCURRENT_CONNECTIONS = 10
    # Stabilization delay after each connection (seconds)
    CONNECTION_STABILIZATION_DELAY = 0.05
    # Timeout for disconnect operations (seconds)
    DISCONNECT_TIMEOUT = 5.0

    def __init__(self):
        """Initialize the client pool."""
        self._pool: dict[TaskIdentifier, AIClient] = {}
        # Use semaphore instead of lock to allow limited concurrency
        self._connection_semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_CONNECTIONS)
        # Per-task_id locks to prevent duplicate client creation for the same task
        self._task_locks: dict[TaskIdentifier, asyncio.Lock] = {}
        self._cleanup_tasks: set[asyncio.Task] = set()

    @property
    def pool(self) -> dict[TaskIdentifier, AIClient]:
        """Get the underlying pool dictionary."""
        return self._pool

    def _get_task_lock(self, task_id: TaskIdentifier) -> asyncio.Lock:
        """Get or create a per-task_id lock."""
        if task_id not in self._task_locks:
            self._task_locks[task_id] = asyncio.Lock()
        return self._task_locks[task_id]

    def _extract_session_id(self, options: Any) -> str | None:
        """
        Extract session ID from provider-specific options.

        Supports:
        - Claude: options.resume (session ID for resuming conversations)
        - Codex: options.thread_id (thread ID for conversation continuity)
        - Generic: Any options object with session_id attribute

        Args:
            options: Provider-specific options object

        Returns:
            Session ID string if found, None otherwise
        """
        # Try Claude-specific field first (most common)
        if hasattr(options, "resume"):
            return getattr(options, "resume", None)
        # Try Codex-specific field
        if hasattr(options, "thread_id"):
            return getattr(options, "thread_id", None)
        # Try generic session_id field
        if hasattr(options, "session_id"):
            return getattr(options, "session_id", None)
        return None

    @abstractmethod
    async def _create_client(self, options: Any) -> AIClient:
        """
        Create a new AI client with the given options.

        This method must be implemented by provider-specific pools.

        Args:
            options: Provider-specific client options

        Returns:
            Connected AIClient instance ready for use
        """
        ...

    async def get_or_create(self, task_id: TaskIdentifier, options: Any) -> Tuple[AIClient, bool]:
        """
        Get existing client or create new one.

        Args:
            task_id: Identifier for this agent task
            options: Provider-specific client configuration

        Returns:
            (client, is_new) tuple
            - client: AIClient instance
            - is_new: True if newly created, False if reused from pool

        Best Practice: Use lock to prevent race conditions when creating
        multiple clients concurrently.
        """
        # Check if client exists outside the lock (fast path)
        if task_id in self._pool:
            existing_client = self._pool[task_id]
            # Extract session ID using provider-agnostic method
            old_session_id = (
                self._extract_session_id(existing_client.options) if hasattr(existing_client, "options") else None
            )
            new_session_id = self._extract_session_id(options)

            logger.debug(f"Client exists for {task_id} | Old session: {old_session_id} | New session: {new_session_id}")

            # If session changed (especially from something to None), recreate the client
            if old_session_id != new_session_id and (old_session_id is not None or new_session_id is not None):
                logger.info(
                    f"Session changed for {task_id} (old: {old_session_id}, new: {new_session_id}), recreating client"
                )
                # Just remove from pool without calling disconnect()
                # The disconnect() method has internal cancel scopes that can interfere with SQLAlchemy
                # Let GC handle cleanup of the old client
                self._remove_from_pool(task_id)
                # Fall through to create new client below
            else:
                logger.debug(f"Reusing existing client for {task_id}")
                # Update options for the existing client (in case system prompt changed)
                self._pool[task_id].options = options
                return self._pool[task_id], False

        # Use per-task_id lock to prevent duplicate client creation for the same task
        task_lock = self._get_task_lock(task_id)
        async with task_lock:
            # Double-check after acquiring task lock (another coroutine might have created it)
            if task_id in self._pool:
                existing_client = self._pool[task_id]
                # Extract session ID using provider-agnostic method
                old_session_id = (
                    self._extract_session_id(existing_client.options) if hasattr(existing_client, "options") else None
                )
                new_session_id = self._extract_session_id(options)

                # If session changed, remove and recreate (without calling disconnect)
                if old_session_id != new_session_id and (old_session_id is not None or new_session_id is not None):
                    logger.info(f"Session changed for {task_id} while waiting for lock, recreating client")
                    self._remove_from_pool(task_id)
                    # Continue to create new client below
                else:
                    logger.debug(f"Client for {task_id} was created while waiting for lock")
                    self._pool[task_id].options = options
                    return self._pool[task_id], False

            # Use semaphore to limit overall connection concurrency
            async with self._connection_semaphore:
                logger.debug(f"Creating new client for {task_id}")

                # Retry connection with exponential backoff
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        client = await self._create_client(options)
                        self._pool[task_id] = client

                        # Brief delay to let connection stabilize before next connection
                        await asyncio.sleep(self.CONNECTION_STABILIZATION_DELAY)

                        return client, True
                    except Exception as e:
                        error_str = str(e)
                        # Retry on transport-related errors
                        if ("ProcessTransport is not ready" in error_str or "transport" in error_str.lower()) and attempt < max_retries - 1:
                            delay = 0.3 * (2**attempt)  # Exponential backoff: 0.3s, 0.6s
                            logger.warning(
                                f"Connection failed for {task_id}, retrying in {delay}s (attempt {attempt + 1}/{max_retries})"
                            )
                            await asyncio.sleep(delay)
                        else:
                            # Re-raise on final attempt or non-transport errors
                            raise

                # This should never be reached (loop always returns or raises)
                raise RuntimeError(f"Failed to create client for {task_id} after {max_retries} retries")

    def _remove_from_pool(self, task_id: TaskIdentifier):
        """
        Remove a client from the pool without calling disconnect.

        Use this when replacing a client due to session changes.
        The SDK's disconnect() has internal cancel scopes that can interfere
        with SQLAlchemy operations, so we let GC handle cleanup instead.

        Args:
            task_id: Identifier for the client to remove
        """
        if task_id not in self._pool:
            return

        logger.info(f"🗑️  Removing client from pool for {task_id} (no disconnect)")
        del self._pool[task_id]

    async def cleanup(self, task_id: TaskIdentifier):
        """
        Remove and cleanup a specific client.

        Args:
            task_id: Identifier for the client to cleanup

        Best Practice: Disconnect in background task to avoid
        cancel scope issues. The cleanup happens outside the current
        async context to prevent premature cancellation.

        Note: For session changes, use _remove_from_pool() instead to avoid
        cancel scope interference with SQLAlchemy.
        """
        if task_id not in self._pool:
            return

        logger.info(f"🧹 Cleaning up client for {task_id}")
        client = self._pool[task_id]

        # Remove from pool immediately
        del self._pool[task_id]

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
        tasks_to_cleanup = [task_id for task_id in self._pool.keys() if task_id.room_id == room_id]
        for task_id in tasks_to_cleanup:
            await self.cleanup(task_id)

    async def shutdown_all(self):
        """
        Graceful shutdown of all clients.

        Best Practice: Wait for all cleanup tasks to complete
        before final shutdown to prevent resource leaks.
        """
        logger.info(f"🛑 Shutting down ClientPool with {len(self._pool)} pooled clients")

        # Cleanup all clients
        task_ids = list(self._pool.keys())
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
        return [task_id for task_id in self._pool.keys() if task_id.agent_id == agent_id]

    def keys(self):
        """
        Get all pool keys.

        Returns:
            Dict keys view of all TaskIdentifiers in the pool
        """
        return self._pool.keys()

    async def _disconnect_client_background(
        self, client: AIClient, task_id: TaskIdentifier
    ):
        """
        Background task for client disconnection with timeout.

        Isolated in separate async task to avoid cancel scope issues.
        Uses timeout to prevent hanging disconnect operations from accumulating.
        Uses asyncio.shield() to protect from cancellation of parent tasks.

        Args:
            client: The client to disconnect (any AIClient implementation)
            task_id: Identifier for logging purposes
        """
        try:
            # Use shield to protect disconnect from cancellation by parent tasks
            # This prevents CancelledError from propagating when the main task is cancelled
            if hasattr(client, "disconnect"):
                await asyncio.wait_for(
                    asyncio.shield(client.disconnect()),
                    timeout=self.DISCONNECT_TIMEOUT,
                )
                logger.debug(f"Disconnected client for {task_id}")
            elif hasattr(client, "close"):
                await asyncio.wait_for(
                    asyncio.shield(client.close()),
                    timeout=self.DISCONNECT_TIMEOUT,
                )
                logger.debug(f"Closed client for {task_id}")
        except asyncio.TimeoutError:
            logger.warning(f"Timeout disconnecting client {task_id} (>{self.DISCONNECT_TIMEOUT}s)")
        except asyncio.CancelledError:
            # CancelledError is expected when parent task is cancelled
            # Just log and suppress - the client may already be disconnected
            logger.debug(f"Disconnect cancelled for {task_id} (parent task cancelled)")
        except Exception as e:
            # Suppress cancel scope errors and connection-related errors
            # These can happen if the client's internal state is tied to a completed task
            error_msg = str(e).lower()
            if (
                "cancel scope" not in error_msg
                and "cancelled" not in error_msg
                and "no active connection" not in error_msg
            ):
                logger.warning(f"Error disconnecting client {task_id}: {e}")


# Backwards compatibility: alias for existing code
# TODO: Remove after manager.py is updated to use provider-specific pools
ClientPool = BaseClientPool
