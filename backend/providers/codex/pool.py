"""
Codex-specific client pool implementation.

This module provides a client pool class for managing Codex client lifecycle.
The pool supports two modes based on USE_CODEX_APP_SERVER setting:
- MCP mode: Uses CodexMCPClient with codex mcp-server
- App Server mode: Uses CodexAppServerClient with codex app-server
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Tuple, Union

from core import get_settings
from domain.task_identifier import TaskIdentifier

from providers.base import AIClient, ClientPoolInterface

from .app_server_client import CodexAppServerClient, CodexAppServerOptions
from .mcp_client import CodexMCPClient, CodexMCPOptions

logger = logging.getLogger("CodexClientPool")

# Type alias for either client type
CodexClient = Union[CodexMCPClient, CodexAppServerClient]
CodexOptions = Union[CodexMCPOptions, CodexAppServerOptions]


class CodexClientPool(ClientPoolInterface):
    """
    Codex client pool supporting both MCP and App Server modes.

    Manages pooling and lifecycle of Codex clients.
    Mode is determined by USE_CODEX_APP_SERVER setting:
    - MCP mode (default=false): Uses CodexMCPClient
    - App Server mode (default=true): Uses CodexAppServerClient
    """

    # Allow up to 10 concurrent "connections" (lightweight for MCP)
    MAX_CONCURRENT_CONNECTIONS = 10
    # Timeout for disconnect operations (seconds)
    DISCONNECT_TIMEOUT = 5.0

    def __init__(self):
        """Initialize the client pool."""
        self._pool: dict[TaskIdentifier, CodexClient] = {}
        self._settings = get_settings()
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

    def _use_app_server(self) -> bool:
        """Check if App Server mode is enabled."""
        return self._settings.use_codex_app_server

    def _create_client(self, options: CodexMCPOptions) -> CodexClient:
        """Create the appropriate client based on mode setting.

        Args:
            options: CodexMCPOptions (will be converted for App Server mode)

        Returns:
            CodexMCPClient or CodexAppServerClient
        """
        if self._use_app_server():
            # Convert MCP options to App Server options
            app_options = CodexAppServerOptions(
                system_prompt=options.system_prompt,
                model=options.model,
                thread_id=options.thread_id,
                mcp_servers=options.mcp_servers,
                approval_policy=options.approval_policy,
                sandbox=options.sandbox,
                extra_config=options.extra_config,
                cwd=options.cwd,
            )
            logger.debug("Creating Codex App Server client")
            return CodexAppServerClient(app_options)
        else:
            logger.debug("Creating Codex MCP client")
            return CodexMCPClient(options)

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
                # Update options - handle both client types
                if self._use_app_server():
                    app_options = CodexAppServerOptions(
                        system_prompt=options.system_prompt,
                        model=options.model,
                        thread_id=options.thread_id,
                        mcp_servers=options.mcp_servers,
                        approval_policy=options.approval_policy,
                        sandbox=options.sandbox,
                        extra_config=options.extra_config,
                        cwd=options.cwd,
                    )
                    self._pool[task_id].options = app_options
                else:
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
                    # Update options - handle both client types
                    if self._use_app_server():
                        app_options = CodexAppServerOptions(
                            system_prompt=options.system_prompt,
                            model=options.model,
                            thread_id=options.thread_id,
                            mcp_servers=options.mcp_servers,
                            approval_policy=options.approval_policy,
                            sandbox=options.sandbox,
                            extra_config=options.extra_config,
                            cwd=options.cwd,
                        )
                        self._pool[task_id].options = app_options
                    else:
                        self._pool[task_id].options = options
                    return self._pool[task_id], False

            # Use semaphore to limit overall connection concurrency
            async with self._connection_semaphore:
                mode = "App Server" if self._use_app_server() else "MCP"
                logger.debug(f"Creating new Codex {mode} client for {task_id}")

                try:
                    client = self._create_client(options)
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

    async def _disconnect_client_background(self, client: CodexClient, task_id: TaskIdentifier):
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
