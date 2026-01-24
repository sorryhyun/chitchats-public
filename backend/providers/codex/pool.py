"""
Codex-specific client pool implementation.

This module provides a client pool class for managing Codex client lifecycle.
The pool tracks client instances for session management and cleanup using
CodexAppServerClient with CodexAppServerPool.
"""

from __future__ import annotations

import logging

from domain.task_identifier import TaskIdentifier

from providers.base import AIClient
from providers.base_pool import BaseClientPool

from .app_server_client import CodexAppServerClient, CodexAppServerOptions

logger = logging.getLogger("CodexClientPool")


class CodexClientPool(BaseClientPool[AIClient, CodexAppServerOptions]):
    """
    Codex client pool for App Server mode.

    Manages pooling and lifecycle of Codex clients using
    CodexAppServerClient with CodexAppServerPool.

    The pool tracks individual clients for session management and cleanup.
    """

    def _get_pool_name(self) -> str:
        """Get the pool name for logging."""
        return "CodexClientPool"

    def _get_session_id_from_options(self, options: CodexAppServerOptions) -> str | None:
        """Extract thread ID from Codex options."""
        return options.thread_id

    def _get_session_id_from_client(self, client: AIClient) -> str | None:
        """Extract thread ID from Codex client."""
        if client.options:
            return client.options.thread_id
        return None

    async def _create_client_impl(
        self,
        task_id: TaskIdentifier,
        options: CodexAppServerOptions,
    ) -> AIClient:
        """Create and connect a new Codex App Server client.

        Simple creation without retry (App Server pool handles connection management).
        """
        try:
            client: AIClient = CodexAppServerClient(options)
            await client.connect()
            return client
        except Exception as e:
            self._logger.error(f"Failed to create Codex client for {task_id}: {e}")
            raise
