"""
Codex provider implementation.

This module provides the CodexProvider class that implements AIProvider
for the Codex MCP backend using persistent `codex mcp-server` connection.
"""

import asyncio
import logging
import os
import platform
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from core import get_settings

from providers.base import AIClient, AIClientOptions, AIProvider, AIStreamParser, ProviderType

from .mcp_client import CodexMCPClient, CodexMCPOptions
from .parser import CodexStreamParser
from .pool import CodexClientPool

logger = logging.getLogger("CodexProvider")

# Get settings singleton
_settings = get_settings()


def _get_codex_working_dir() -> str:
    """Get a valid working directory for Codex subprocess.

    Uses /tmp/codex-empty to provide an isolated, empty workspace.
    """
    temp_dir = Path(tempfile.gettempdir()) / "codex-empty"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return str(temp_dir)


class CodexProvider(AIProvider):
    """Codex provider implementing AIProvider interface.

    This provider wraps the Codex MCP server to provide a unified
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

    def create_client(self, options: CodexMCPOptions) -> AIClient:
        """Create a new Codex MCP client with the given options.

        Args:
            options: CodexMCPOptions for client configuration

        Returns:
            CodexMCPClient ready for connection
        """
        return CodexMCPClient(options)

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
    ) -> CodexMCPOptions:
        """Build Codex MCP options from base configuration.

        Args:
            base_options: Provider-agnostic configuration
            anthropic_calls_capture: Not used for Codex (tool capture via parsing)
            skip_tool_capture: Not used for Codex (tool capture via parsing)

        Returns:
            CodexMCPOptions ready for client creation

        Note:
            Codex doesn't support hooks like Claude SDK, so tool capture
            is done via parsing the JSON stream instead.
        """
        # Unused parameters (tool capture is done via stream parsing)
        _ = anthropic_calls_capture
        _ = skip_tool_capture

        # Build MCP servers dict for the config parameter
        mcp_servers: Dict[str, Any] = {}
        if base_options.mcp_tools:
            mcp_servers = self._build_mcp_server_dict(base_options.mcp_tools)

        # Build extra config for Codex behavior (nested JSON structure)
        # Note: base_instructions and cwd are passed as top-level parameters, not in config
        extra_config: Dict[str, Any] = {
            "features": {
                "shell_tool": False,
                "child_agents_md": False,
            },
            "project_doc_max_bytes": 0,
            "show_raw_agent_reasoning": True,
            "model_verbosity": "medium",
            "model_reasoning_summary": "detailed",
        }

        return CodexMCPOptions(
            system_prompt=base_options.system_prompt,
            model=base_options.model if base_options.model else None,
            thread_id=base_options.session_id,  # Codex uses thread_id
            mcp_servers=mcp_servers,
            approval_policy="never",  # Minimal prompt - non-interactive mode
            sandbox="danger-full-access",  # Minimal prompt - no sandbox restrictions
            extra_config=extra_config,
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

    def _build_mcp_server_dict(self, mcp_tools: dict) -> Dict[str, Any]:
        """Build MCP servers config dict for MCP mode.

        Converts mcp_tools into the format expected by the MCP server's
        config parameter.

        Args:
            mcp_tools: Dict containing agent_name, agent_group, agent_id

        Returns:
            Dict of MCP server configurations
        """
        if not mcp_tools:
            return {}

        agent_name = mcp_tools.get("agent_name", "Agent")
        agent_group = mcp_tools.get("agent_group", "default")
        agent_id = mcp_tools.get("agent_id")
        room_id = mcp_tools.get("room_id")
        config_file = mcp_tools.get("config_file")

        # Get backend path from settings
        backend_path = str(_settings.backend_dir)

        # Determine command and args based on execution mode
        is_frozen = getattr(sys, "frozen", False)

        if is_frozen:
            # Running as PyInstaller bundle - use self-spawn mode
            # The bundled exe handles --mcp-server argument
            exe_path = sys.executable
            action_cmd = exe_path
            action_args = ["--mcp-server", "action"]
            guidelines_cmd = exe_path
            guidelines_args = ["--mcp-server", "guidelines"]
            # In bundled mode, cwd is the exe's directory
            cwd = str(Path(exe_path).parent)
        else:
            # Development mode - use Python interpreter
            python_path = os.environ.get("VIRTUAL_ENV")
            if python_path:
                # Use platform-specific path for Python executable
                if platform.system() == "Windows":
                    python_exe = str(Path(python_path) / "Scripts" / "python.exe")
                else:
                    python_exe = str(Path(python_path) / "bin" / "python")
            else:
                python_exe = "python"

            action_cmd = python_exe
            action_args = ["-m", "mcp_servers.action_server"]
            guidelines_cmd = python_exe
            guidelines_args = ["-m", "mcp_servers.guidelines_server"]
            cwd = backend_path

        # Build environment variables
        action_env: Dict[str, str] = {
            "AGENT_NAME": agent_name,
            "AGENT_GROUP": agent_group,
            "PYTHONPATH": backend_path,
            "PROVIDER": "codex",
        }
        if room_id is not None:
            action_env["ROOM_ID"] = str(room_id)
        if agent_id is not None:
            action_env["AGENT_ID"] = str(agent_id)
        if config_file is not None:
            action_env["CONFIG_FILE"] = config_file

        guidelines_env: Dict[str, str] = {
            "AGENT_NAME": agent_name,
            "PYTHONPATH": backend_path,
            "PROVIDER": "codex",
        }

        return {
            "action": {
                "command": action_cmd,
                "args": action_args,
                "cwd": cwd,
                "env": action_env,
            },
            "guidelines": {
                "command": guidelines_cmd,
                "args": guidelines_args,
                "cwd": cwd,
                "env": guidelines_env,
            },
        }

    def get_session_key_field(self) -> str:
        """Get the database field name for Codex's session ID.

        Returns:
            'codex_thread_id' as the field name
        """
        return "codex_thread_id"
