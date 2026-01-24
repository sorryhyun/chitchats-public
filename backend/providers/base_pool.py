"""
Base client pool implementation with template method pattern.

This module provides the BaseClientPool class that consolidates common
pooling logic between Claude and Codex providers.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Generic, Tuple, TypeVar

from domain.task_identifier import TaskIdentifier

from providers.base import AIClient, ClientPoolInterface

# Type variables for provider-specific types
TClient = TypeVar("TClient", bound=AIClient)
TOptions = TypeVar("TOptions")

logger = logging.getLogger("BaseClientPool")


class BaseClientPool(ClientPoolInterface, ABC, Generic[TClient, TOptions]):
    """
    Base client pool with template method pattern.

    Manages pooling and lifecycle of AI clients with:
    - Concurrent connection management (semaphore)
    - Per-task locking to prevent duplicate client creation
    - Background cleanup of disconnected clients
    - Session ID tracking for client reuse decisions

    Subclasses must implement:
    - _get_session_id_from_options(options) -> str | None
    - _get_session_id_from_client(client) -> str | None
    - _create_client_impl(task_id, options) -> TClient
    - _get_pool_name() -> str
    """

    # Allow up to 10 concurrent connections
    MAX_CONCURRENT_CONNECTIONS = 10
    # Timeout for disconnect operations (seconds)
    DISCONNECT_TIMEOUT = 5.0

    def __init__(self):
        """Initialize the client pool."""
        self._pool: dict[TaskIdentifier, TClient] = {}
        self._connection_semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_CONNECTIONS)
        self._task_locks: dict[TaskIdentifier, asyncio.Lock] = {}
        self._cleanup_tasks: set[asyncio.Task] = set()
        self._logger = logging.getLogger(self._get_pool_name())

    @property
    def pool(self) -> dict:
        """Get the underlying pool dictionary."""
        return self._pool

    def _get_task_lock(self, task_id: TaskIdentifier) -> asyncio.Lock:
        """Get or create a per-task_id lock."""
        if task_id not in self._task_locks:
            self._task_locks[task_id] = asyncio.Lock()
        return self._task_locks[task_id]

    # =========================================================================
    # Abstract methods - provider-specific implementations
    # =========================================================================

    @abstractmethod
    def _get_pool_name(self) -> str:
        """Get the pool name for logging."""
        ...

    @abstractmethod
    def _get_session_id_from_options(self, options: TOptions) -> str | None:
        """Extract session/thread ID from options.

        Args:
            options: Provider-specific options object

        Returns:
            Session ID or None if not present
        """
        ...

    @abstractmethod
    def _get_session_id_from_client(self, client: TClient) -> str | None:
        """Extract session/thread ID from a client.

        Args:
            client: Provider-specific client instance

        Returns:
            Session ID or None if not present
        """
        ...

    @abstractmethod
    async def _create_client_impl(
        self,
        task_id: TaskIdentifier,
        options: TOptions,
    ) -> TClient:
        """Create and connect a new client.

        Provider-specific implementation for client creation.
        May include retry logic, connection stabilization, etc.

        Args:
            task_id: Identifier for this agent task
            options: Provider-specific options

        Returns:
            Connected client instance

        Raises:
            Exception: If client creation fails
        """
        ...

    # =========================================================================
    # Common implementation
    # =========================================================================

    async def get_or_create(
        self,
        task_id: TaskIdentifier,
        options: TOptions,
    ) -> Tuple[AIClient, bool]:
        """Get existing client or create new one.

        Args:
            task_id: Identifier for this agent task
            options: Provider-specific options for client configuration

        Returns:
            (client, is_new) tuple
        """
        # Check if client exists (fast path)
        if task_id in self._pool:
            existing_client = self._pool[task_id]
            old_session_id = self._get_session_id_from_client(existing_client)
            new_session_id = self._get_session_id_from_options(options)

            self._logger.debug(
                f"Client exists for {task_id} | Old session: {old_session_id} | New session: {new_session_id}"
            )

            # If session changed, recreate the client
            if old_session_id != new_session_id and (old_session_id is not None or new_session_id is not None):
                self._logger.info(f"Session changed for {task_id}, recreating client")
                self._remove_from_pool(task_id)
            else:
                self._logger.debug(f"Reusing existing client for {task_id}")
                self._pool[task_id].options = options
                return self._pool[task_id], False

        # Use per-task lock to prevent duplicate client creation
        task_lock = self._get_task_lock(task_id)
        async with task_lock:
            # Double-check after acquiring lock
            if task_id in self._pool:
                existing_client = self._pool[task_id]
                old_session_id = self._get_session_id_from_client(existing_client)
                new_session_id = self._get_session_id_from_options(options)

                if old_session_id != new_session_id and (old_session_id is not None or new_session_id is not None):
                    self._logger.info(f"Session changed for {task_id} while waiting for lock, recreating client")
                    self._remove_from_pool(task_id)
                else:
                    self._logger.debug(f"Client for {task_id} was created while waiting for lock")
                    self._pool[task_id].options = options
                    return self._pool[task_id], False

            # Use semaphore to limit overall connection concurrency
            async with self._connection_semaphore:
                self._logger.debug(f"Creating new client for {task_id}")
                client = await self._create_client_impl(task_id, options)
                self._pool[task_id] = client
                return client, True

    def _remove_from_pool(self, task_id: TaskIdentifier):
        """Remove a client from the pool without calling disconnect."""
        if task_id not in self._pool:
            return
        self._logger.info(f"Removing client from pool for {task_id}")
        del self._pool[task_id]

    async def cleanup(self, task_id: Any) -> None:
        """Remove and cleanup a specific client."""
        if task_id not in self._pool:
            return

        self._logger.info(f"Cleaning up client for {task_id}")
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
        self._logger.info(f"Shutting down {self._get_pool_name()} with {len(self._pool)} pooled clients")

        task_ids = list(self._pool.keys())
        for task_id in task_ids:
            await self.cleanup(task_id)

        if self._cleanup_tasks:
            self._logger.info(f"Waiting for {len(self._cleanup_tasks)} cleanup tasks to complete")
            await asyncio.gather(*self._cleanup_tasks, return_exceptions=True)

        self._logger.info(f"{self._get_pool_name()} shutdown complete")

    def get_keys_for_agent(self, agent_id: int) -> list[TaskIdentifier]:
        """Get all pool keys for a specific agent."""
        return [task_id for task_id in self._pool.keys() if task_id.agent_id == agent_id]

    def keys(self):
        """Get all pool keys."""
        return self._pool.keys()

    async def _disconnect_client_background(self, client: TClient, task_id: TaskIdentifier):
        """Background task for client disconnection with timeout."""
        try:
            await asyncio.wait_for(
                asyncio.shield(client.disconnect()),
                timeout=self.DISCONNECT_TIMEOUT,
            )
            self._logger.debug(f"Disconnected client for {task_id}")
        except asyncio.TimeoutError:
            self._logger.warning(f"Timeout disconnecting client {task_id}")
        except asyncio.CancelledError:
            self._logger.debug(f"Disconnect cancelled for {task_id}")
        except Exception as e:
            error_msg = str(e).lower()
            if "cancel" not in error_msg:
                self._logger.warning(f"Error disconnecting client {task_id}: {e}")
