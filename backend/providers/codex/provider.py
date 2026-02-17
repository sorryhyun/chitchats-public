"""
Codex provider implementation.

This module provides the CodexProvider class that implements AIProvider
for Codex backend using `codex app-server` with JSON-RPC streaming.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from domain.task_identifier import TaskIdentifier

from providers.base import AIClient, AIClientOptions, AIProvider, AIStreamParser, ProviderType
from providers.base_pool import BaseClientPool
from providers.configs import CodexStartupConfig
from providers.mcp_config import MCPConfigBuilder, MCPServerEnv

from .app_server_client import CodexAppServerClient, CodexAppServerOptions
from .parser import CodexStreamParser

logger = logging.getLogger("CodexProvider")

# Cached working directory (created once per process)
_CODEX_WORKING_DIR: str | None = None


class CodexClientPool(BaseClientPool[AIClient, CodexAppServerOptions]):
    """Codex client pool for App Server mode.

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


def _get_codex_working_dir() -> str:
    """Get a valid working directory for Codex subprocess.

    Uses /tmp/codex-empty to provide an isolated, empty workspace.
    The result is cached to avoid redundant filesystem operations.
    """
    global _CODEX_WORKING_DIR
    if _CODEX_WORKING_DIR is None:
        temp_dir = Path(tempfile.gettempdir()) / "codex-empty"
        temp_dir.mkdir(parents=True, exist_ok=True)
        _CODEX_WORKING_DIR = str(temp_dir)
    return _CODEX_WORKING_DIR


class CodexProvider(AIProvider):
    """Codex provider implementing AIProvider interface.

    This provider wraps Codex app-server to provide a unified
    interface compatible with the multi-provider abstraction.

    Note: Codex uses threads instead of sessions for conversation state.
    """

    def __init__(self):
        """Initialize the Codex provider."""
        self._parser = CodexStreamParser()
        self._pool: Optional[CodexClientPool] = None

    @property
    def provider_type(self) -> ProviderType:
        """Get the provider type identifier."""
        return ProviderType.CODEX

    def create_client(self, options: CodexAppServerOptions) -> AIClient:
        """Create a new Codex client with the given options.

        Args:
            options: CodexAppServerOptions for client configuration

        Returns:
            CodexAppServerClient instance
        """
        return CodexAppServerClient(options)

    def get_client_pool(self) -> CodexClientPool:
        """Get the client pool for this provider."""
        if self._pool is None:
            self._pool = CodexClientPool()
        return self._pool

    def build_options(
        self,
        base_options: AIClientOptions,
        anthropic_calls_capture: Optional[List[str]] = None,
        skip_tool_capture: Optional[List[bool]] = None,
        excuse_reasons_capture: Optional[List[str]] = None,
    ) -> CodexAppServerOptions:
        """Build Codex App Server options from base configuration.

        Args:
            base_options: Provider-agnostic configuration
            anthropic_calls_capture: Not used for Codex (tool capture via parsing)
            skip_tool_capture: Not used for Codex (tool capture via parsing)
            excuse_reasons_capture: Not used for Codex (tool capture via parsing)

        Returns:
            CodexAppServerOptions ready for client creation

        Note:
            Codex doesn't support hooks like Claude SDK, so tool capture
            is done via parsing the JSON stream instead.
            MCP servers are configured at app-server startup via -c flags,
            not passed per-turn.
        """
        # Unused parameters (tool capture is done via stream parsing)
        _ = anthropic_calls_capture
        _ = skip_tool_capture
        _ = excuse_reasons_capture

        # Build agent key for instance identification
        agent_id = base_options.mcp_tools.get("agent_id") if base_options.mcp_tools else None
        room_id = base_options.mcp_tools.get("room_id") if base_options.mcp_tools else None
        agent_key = f"room_{room_id}_agent_{agent_id}" if room_id and agent_id else "default"

        # Build MCP servers for startup config (passed via -c flags)
        mcp_servers: Dict[str, Any] = {}
        if base_options.mcp_tools:
            env_config = MCPServerEnv(
                agent_name=base_options.mcp_tools.get("agent_name", "Agent"),
                provider="codex",
                group_name=base_options.mcp_tools.get("agent_group"),
                agent_id=base_options.mcp_tools.get("agent_id"),
                config_file=base_options.mcp_tools.get("config_file"),
                room_id=base_options.mcp_tools.get("room_id"),
            )
            mcp_servers = MCPConfigBuilder.build_all_servers(env_config, include_etc=False, prefer_venv=True)

        # Build startup config with MCP servers (passed via -c flags at startup)
        startup_config = CodexStartupConfig(mcp_servers=mcp_servers)

        return CodexAppServerOptions(
            agent_key=agent_key,
            startup_config=startup_config,
            system_prompt=base_options.system_prompt,
            model=base_options.model if base_options.model else None,
            thread_id=base_options.session_id,  # Codex uses thread_id
            cwd=base_options.working_dir or _get_codex_working_dir(),
        )

    def get_parser(self) -> AIStreamParser:
        """Get the stream parser for Codex messages."""
        return self._parser

    async def check_availability(self) -> bool:
        """Check if Codex CLI is available and authenticated.

        Returns:
            True if Codex CLI is installed and authenticated
        """
        # Check if codex is installed via npm
        codex_path = shutil.which("codex")
        if not codex_path:
            logger.warning("Codex CLI not found in PATH")
            return False

        # Check if authenticated using "codex login status"
        try:
            process = await asyncio.create_subprocess_exec(
                "codex",
                "login",
                "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=10.0)

            # Exit code 0 = logged in, non-zero = not logged in
            if process.returncode == 0:
                output = stdout.decode("utf-8").lower()
                if "logged in" in output:
                    return True
                logger.warning(f"Codex login status unclear: {output}")
                return False

            logger.info("Codex not logged in")
            return False

        except asyncio.TimeoutError:
            logger.warning("Codex auth check timed out")
            return False
        except Exception as e:
            logger.warning(f"Codex availability check failed: {e}")
            return False

    def get_session_key_field(self) -> str:
        """Get the database field name for Codex's session ID.

        Returns:
            'codex_thread_id' as the field name
        """
        return "codex_thread_id"
