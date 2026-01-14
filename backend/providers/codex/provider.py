"""
Codex provider implementation.

This module provides the CodexProvider class that implements AIProvider
for the Codex CLI backend.
"""

import asyncio
import logging
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, List, Optional

# Windows detection for subprocess handling
IS_WINDOWS = sys.platform == "win32"

from providers.base import AIClientOptions, AIProvider, AIStreamParser, ProviderType

from .client import CodexClient, CodexOptions
from .mcp_config import build_mcp_overrides
from .parser import CodexStreamParser

logger = logging.getLogger("CodexProvider")


def _get_codex_working_dir() -> str:
    """Get a valid working directory for Codex subprocess.

    Uses /tmp/codex-empty to provide an isolated, empty workspace
    similar to Claude Code's behavior.
    """
    temp_dir = Path(tempfile.gettempdir()) / "codex-empty"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return str(temp_dir)


class CodexProvider(AIProvider):
    """Codex provider implementing AIProvider interface.

    This provider wraps the Codex CLI to provide a unified
    interface compatible with the multi-provider abstraction.

    Note: Codex uses threads instead of sessions for conversation state.
    """

    def __init__(self):
        """Initialize the Codex provider."""
        self._parser = CodexStreamParser()

    @property
    def provider_type(self) -> ProviderType:
        """Get the provider type identifier."""
        return ProviderType.CODEX

    def create_client(self, options: CodexOptions) -> CodexClient:
        """Create a new Codex client with the given options.

        Args:
            options: CodexOptions for client configuration

        Returns:
            CodexClient ready for connection
        """
        return CodexClient(options)

    def build_options(
        self,
        base_options: AIClientOptions,
        anthropic_calls_capture: Optional[List[str]] = None,
        skip_tool_capture: Optional[List[bool]] = None,
    ) -> CodexOptions:
        """Build Codex CLI options from base configuration.

        Args:
            base_options: Provider-agnostic configuration
            anthropic_calls_capture: Not used for Codex (tool capture via parsing)
            skip_tool_capture: Not used for Codex (tool capture via parsing)

        Returns:
            CodexOptions ready for client creation

        Note:
            Codex doesn't support hooks like Claude SDK, so tool capture
            is done via parsing the JSON stream instead.
        """
        # Build MCP config overrides if tools are defined
        mcp_overrides = []
        if base_options.mcp_tools:
            mcp_overrides = self._build_mcp_overrides(base_options.mcp_tools)

        # Disable shell/bash tool for security (similar to Claude Code's isolated mode)
        mcp_overrides.append('features.shell_tool=false')

        # Prevent Codex from reading project instruction files (AGENTS.md, etc.)
        mcp_overrides.append('project_doc_max_bytes=1')

        options = CodexOptions(
            system_prompt=base_options.system_prompt,
            model=base_options.model if base_options.model else None,
            thread_id=base_options.session_id,  # Codex uses thread_id
            full_auto=True,
            skip_git_repo_check=True,
            working_dir=base_options.working_dir or _get_codex_working_dir(),
            mcp_config_overrides=mcp_overrides,
            timeout=300.0,
        )

        return options

    def get_parser(self) -> AIStreamParser:
        """Get the stream parser for Codex messages."""
        return self._parser

    async def check_availability(self) -> bool:
        """Check if Codex CLI is available and authenticated.

        Returns:
            True if Codex CLI is installed and authenticated
        """
        # Check if codex is installed
        codex_path = shutil.which("codex")
        if not codex_path:
            logger.warning("Codex CLI not found in PATH")
            return False

        # Check if authenticated
        try:
            if IS_WINDOWS:
                # On Windows, use shell=True for .cmd batch scripts
                process = await asyncio.create_subprocess_shell(
                    "codex auth status",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                process = await asyncio.create_subprocess_exec(
                    "codex",
                    "auth",
                    "status",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=10.0
            )

            if process.returncode == 0:
                output = stdout.decode("utf-8").lower()
                # Check for authenticated status
                if "authenticated" in output or "logged in" in output:
                    return True
                logger.warning(f"Codex not authenticated: {output}")
                return False

            logger.warning(f"Codex auth check failed: {stderr.decode('utf-8')}")
            return False

        except asyncio.TimeoutError:
            logger.warning("Codex auth check timed out")
            return False
        except Exception as e:
            logger.warning(f"Codex availability check failed: {e}")
            return False

    def _build_mcp_overrides(self, mcp_tools: dict) -> List[str]:
        """Build MCP config overrides for Codex CLI.

        Uses -c flags to configure MCP servers at runtime without
        modifying ~/.codex/config.toml.

        Args:
            mcp_tools: Dict containing agent_name, agent_group, agent_id

        Returns:
            List of -c override strings for Codex CLI
        """
        if not mcp_tools:
            return []

        agent_name = mcp_tools.get("agent_name", "Agent")
        agent_group = mcp_tools.get("agent_group", "default")
        agent_id = mcp_tools.get("agent_id")
        room_id = mcp_tools.get("room_id")

        # Get backend path (parent of providers directory)
        backend_path = str(Path(__file__).parent.parent.parent)

        try:
            return build_mcp_overrides(
                agent_name=agent_name,
                agent_group=agent_group,
                backend_path=backend_path,
                room_id=room_id,
                agent_id=agent_id,
            )
        except Exception as e:
            logger.warning(f"Failed to build MCP overrides: {e}")
            return []

    def get_session_key_field(self) -> str:
        """Get the database field name for Codex's session ID.

        Returns:
            'codex_thread_id' as the field name
        """
        return "codex_thread_id"
