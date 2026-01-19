"""
Codex-specific client pool implementation.

This module provides a client pool class for managing Codex MCP client lifecycle.
The pool tracks client instances for session management and cleanup, while the
actual server connection is shared via CodexMCPServerManager singleton.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Tuple

from domain.task_identifier import TaskIdentifier

from providers.base import AIClient, ClientPoolInterface

from .mcp_client import CodexMCPClient, CodexMCPOptions

logger = logging.getLogger("CodexClientPool")


class CodexClientPool(ClientPoolInterface):
    """
    Codex client pool for MCP mode.

    Manages pooling and lifecycle of Codex MCP clients.
    The MCP pool uses a shared server connection managed by CodexMCPServerManager.
    The pool tracks individual clients for session management and cleanup.
    """

    # Allow up to 10 concurrent "connections" (lightweight for MCP)
    MAX_CONCURRENT_CONNECTIONS = 10
    # Timeout for disconnect operations (seconds)
    DISCONNECT_TIMEOUT = 5.0

    def __init__(self):
        """Initialize the MCP client pool."""
        self._pool: dict[TaskIdentifier, CodexMCPClient] = {}
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
        options: CodexMCPOptions,
    ) -> Tuple[AIClient, bool]:
        """Get existing client or create new one.

        Args:
            task_id: Identifier for this agent task
            options: CodexMCPOptions for client configuration

        Returns:
            (client, is_new) tuple
        """
        # Check if client exists (fast path)
        if task_id in self._pool:
            existing_client = self._pool[task_id]
            old_thread_id = existing_client.options.thread_id if existing_client.options else None
            new_thread_id = options.thread_id

            logger.debug(f"Client exists for {task_id} | Old thread: {old_thread_id} | New thread: {new_thread_id}")

            # If thread changed, recreate the client
            if old_thread_id != new_thread_id and (old_thread_id is not None or new_thread_id is not None):
                logger.info(f"Thread changed for {task_id}, recreating client")
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
                old_thread_id = existing_client.options.thread_id if existing_client.options else None
                new_thread_id = options.thread_id

                if old_thread_id != new_thread_id and (old_thread_id is not None or new_thread_id is not None):
                    logger.info(f"Thread changed for {task_id} while waiting for lock, recreating client")
                    self._remove_from_pool(task_id)
                else:
                    logger.debug(f"Client for {task_id} was created while waiting for lock")
                    self._pool[task_id].options = options
                    return self._pool[task_id], False

            # Use semaphore to limit overall connection concurrency
            async with self._connection_semaphore:
                logger.debug(f"Creating new Codex client for {task_id}")

                try:
                    client = CodexMCPClient(options)
                    await client.connect()
                    self._pool[task_id] = client
                    return client, True
                except Exception as e:
                    logger.error(f"Failed to create Codex client for {task_id}: {e}")
                    raise

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
        logger.info(f"Shutting down CodexClientPool with {len(self._pool)} pooled clients")

        task_ids = list(self._pool.keys())
        for task_id in task_ids:
            await self.cleanup(task_id)

        if self._cleanup_tasks:
            logger.info(f"Waiting for {len(self._cleanup_tasks)} cleanup tasks to complete")
            await asyncio.gather(*self._cleanup_tasks, return_exceptions=True)

        logger.info("CodexClientPool shutdown complete")

    def get_keys_for_agent(self, agent_id: int) -> list[TaskIdentifier]:
        """Get all pool keys for a specific agent."""
        return [task_id for task_id in self._pool.keys() if task_id.agent_id == agent_id]

    def keys(self):
        """Get all pool keys."""
        return self._pool.keys()

    async def _disconnect_client_background(self, client: CodexMCPClient, task_id: TaskIdentifier):
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
            if "cancel" not in error_msg:
                logger.warning(f"Error disconnecting client {task_id}: {e}")
