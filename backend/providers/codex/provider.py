"""
Codex provider implementation.

This module provides the CodexProvider class that implements AIProvider
for the Codex CLI backend.

Supports two modes:
    - CLI Mode (default): Spawns `codex exec` subprocess per query
    - MCP Mode: Uses persistent `codex mcp-server` connection

Set CODEX_USE_MCP=true to enable MCP mode.
"""

import asyncio
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Windows detection for subprocess handling
IS_WINDOWS = sys.platform == "win32"

from providers.base import AIClient, AIClientOptions, AIProvider, AIStreamParser, ProviderType

from .client import CodexClient, CodexOptions, _get_bundled_codex_path, _get_codex_executable
from .mcp_client import CodexMCPClient, CodexMCPOptions
from .mcp_config import build_mcp_overrides
from .parser import CodexStreamParser
from .pool import CodexClientPool, CodexMCPClientPool

logger = logging.getLogger("CodexProvider")


def _get_codex_working_dir() -> str:
    """Get a valid working directory for Codex subprocess.

    Uses /tmp/codex-empty to provide an isolated, empty workspace
    similar to Claude Code's behavior.
    """
    temp_dir = Path(tempfile.gettempdir()) / "codex-empty"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return str(temp_dir)


def _is_mcp_mode_enabled() -> bool:
    """Check if MCP mode is enabled via settings."""
    from core import get_settings

    return get_settings().codex_use_mcp


class CodexProvider(AIProvider):
    """Codex provider implementing AIProvider interface.

    This provider wraps the Codex CLI to provide a unified
    interface compatible with the multi-provider abstraction.

    Supports two modes:
        - CLI Mode (default): Spawns subprocess per query
        - MCP Mode (CODEX_USE_MCP=true): Uses persistent MCP server

    Note: Codex uses threads instead of sessions for conversation state.
    """

    def __init__(self):
        """Initialize the Codex provider."""
        self._parser = CodexStreamParser()
        self._cli_pool: Optional[CodexClientPool] = None
        self._mcp_pool: Optional[CodexMCPClientPool] = None

    @property
    def provider_type(self) -> ProviderType:
        """Get the provider type identifier."""
        return ProviderType.CODEX

    @property
    def use_mcp(self) -> bool:
        """Check if MCP mode is enabled."""
        return _is_mcp_mode_enabled()

    def create_client(self, options: Union[CodexOptions, CodexMCPOptions]) -> AIClient:
        """Create a new Codex client with the given options.

        Args:
            options: CodexOptions or CodexMCPOptions for client configuration

        Returns:
            CodexClient or CodexMCPClient ready for connection
        """
        if isinstance(options, CodexMCPOptions):
            return CodexMCPClient(options)
        return CodexClient(options)

    def get_client_pool(self) -> Union[CodexClientPool, CodexMCPClientPool]:
        """Get the client pool for this provider.

        Returns the appropriate pool based on whether MCP mode is enabled.
        """
        if self.use_mcp:
            if self._mcp_pool is None:
                self._mcp_pool = CodexMCPClientPool()
            return self._mcp_pool
        else:
            if self._cli_pool is None:
                self._cli_pool = CodexClientPool()
            return self._cli_pool

    def build_options(
        self,
        base_options: AIClientOptions,
        anthropic_calls_capture: Optional[List[str]] = None,
        skip_tool_capture: Optional[List[bool]] = None,
    ) -> Union[CodexOptions, CodexMCPOptions]:
        """Build Codex options from base configuration.

        Routes to CLI or MCP options based on CODEX_USE_MCP setting.

        Args:
            base_options: Provider-agnostic configuration
            anthropic_calls_capture: Not used for Codex (tool capture via parsing)
            skip_tool_capture: Not used for Codex (tool capture via parsing)

        Returns:
            CodexOptions or CodexMCPOptions ready for client creation

        Note:
            Codex doesn't support hooks like Claude SDK, so tool capture
            is done via parsing the JSON stream instead.
        """
        # Unused parameters (tool capture is done via stream parsing)
        _ = anthropic_calls_capture
        _ = skip_tool_capture

        if self.use_mcp:
            return self._build_mcp_options(base_options)
        return self._build_cli_options(base_options)

    def _build_cli_options(self, base_options: AIClientOptions) -> CodexOptions:
        """Build Codex CLI options for subprocess mode."""
        # Build CLI option overrides
        options_overrides = []
        if base_options.mcp_tools:
            options_overrides = self._build_mcp_overrides(base_options.mcp_tools)

        # Disable shell/bash tool for security (similar to Claude Code's isolated mode)
        options_overrides.append('features.shell_tool=false')

        # Prevent Codex from reading project instruction files (AGENTS.md, etc.)
        options_overrides.append('project_doc_max_bytes=0')

        # Enable reasoning output so we can capture and display thinking
        options_overrides.append('show_raw_agent_reasoning=true')

        # Set verbosity and reasoning summary for detailed output
        options_overrides.append('model_verbosity="medium"')
        options_overrides.append('model_reasoning_summary="detailed"')
        options_overrides.append('features.child_agents_md=false')

        # Clear base_instructions since developer_instructions is already set
        options_overrides.append('base_instructions=""')

        return CodexOptions(
            system_prompt=base_options.system_prompt,
            model=base_options.model if base_options.model else 'gpt-5.2',
            thread_id=base_options.session_id,  # Codex uses thread_id
            full_auto=True,
            skip_git_repo_check=True,
            working_dir=base_options.working_dir or _get_codex_working_dir(),
            mcp_config_overrides=options_overrides,
            timeout=300.0,
        )

    def _build_mcp_options(self, base_options: AIClientOptions) -> CodexMCPOptions:
        """Build Codex MCP options for persistent server mode."""
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
            model=base_options.model if base_options.model else 'gpt-5.2',
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
        # Determine if we're using bundled executable or npm-installed
        bundled_path = _get_bundled_codex_path()
        codex_exe = _get_codex_executable()

        if bundled_path:
            logger.debug(f"Using bundled Codex executable: {codex_exe}")
        else:
            # Check if codex is installed via npm
            codex_path = shutil.which("codex")
            if not codex_path:
                logger.warning("Codex CLI not found in PATH")
                return False

        # Check if authenticated using "codex login status"
        try:
            if IS_WINDOWS and not bundled_path:
                # On Windows with npm-installed CLI, use shell=True for .cmd batch scripts
                process = await asyncio.create_subprocess_shell(
                    "codex login status",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                # Native executable (bundled on Windows, or Unix)
                process = await asyncio.create_subprocess_exec(
                    codex_exe,
                    "login",
                    "status",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            stdout, _ = await asyncio.wait_for(
                process.communicate(), timeout=10.0
            )

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

    async def trigger_login(self) -> bool:
        """Trigger interactive Codex login (opens browser for OAuth).

        This is used for Windows onboarding when user runs the app for the first time.
        The login process opens a browser window for OAuth authentication.

        Returns:
            True if login was successful, False otherwise
        """
        # Only use bundled executable on Windows
        if not IS_WINDOWS:
            logger.warning("trigger_login() is only supported on Windows")
            return False

        bundled_path = _get_bundled_codex_path()
        if not bundled_path:
            logger.warning("Bundled Codex executable not found")
            return False

        codex_exe = str(bundled_path)
        logger.info(f"Triggering Codex login with: {codex_exe}")

        try:
            # Run login interactively (this will open a browser)
            # We don't capture stdout/stderr since it's interactive
            process = await asyncio.create_subprocess_exec(
                codex_exe,
                "login",
                # Don't pipe stdout/stderr - let it be interactive
            )

            # Wait for the login process to complete (user interaction required)
            # Use a longer timeout since user needs to complete OAuth in browser
            await asyncio.wait_for(process.wait(), timeout=300.0)  # 5 minutes

            if process.returncode == 0:
                logger.info("Codex login successful")
                return True
            else:
                logger.warning(f"Codex login failed with exit code: {process.returncode}")
                return False

        except asyncio.TimeoutError:
            logger.warning("Codex login timed out (user did not complete OAuth in time)")
            return False
        except Exception as e:
            logger.error(f"Codex login failed: {e}")
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

        # Get backend path (parent of providers directory)
        backend_path = str(Path(__file__).parent.parent.parent)

        # Get Python executable path
        python_path = os.environ.get("VIRTUAL_ENV")
        if python_path:
            python_exe = str(Path(python_path) / "bin" / "python")
        else:
            python_exe = "python"

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
            "AGENT_GROUP": agent_group,
            "PYTHONPATH": backend_path,
            "PROVIDER": "codex",
        }

        return {
            "chitchats_action": {
                "command": python_exe,
                "args": ["-m", "mcp_servers.action_server"],
                "cwd": backend_path,
                "env": action_env,
            },
            "chitchats_guidelines": {
                "command": python_exe,
                "args": ["-m", "mcp_servers.guidelines_server"],
                "cwd": backend_path,
                "env": guidelines_env,
            },
        }

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
        config_file = mcp_tools.get("config_file")

        # Get backend path (parent of providers directory)
        backend_path = str(Path(__file__).parent.parent.parent)

        # Get work_dir (where agents folder lives)
        # In bundled mode: next to the exe
        # In dev mode: project root (parent of backend)
        is_bundled = getattr(sys, "frozen", False)
        if is_bundled:
            work_dir = str(Path(sys.executable).parent)
        else:
            work_dir = str(Path(__file__).parent.parent.parent.parent)

        try:
            return build_mcp_overrides(
                agent_name=agent_name,
                agent_group=agent_group,
                backend_path=backend_path,
                work_dir=work_dir,
                room_id=room_id,
                agent_id=agent_id,
                config_file=config_file,
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
