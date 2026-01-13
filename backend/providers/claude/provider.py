"""
Claude Code provider implementation.

This module provides the ClaudeProvider class that implements AIProvider
for the Claude Agent SDK backend.
"""

import asyncio
import logging
import sys
import tempfile
from pathlib import Path
from typing import Any, List, Optional

from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk.types import HookMatcher, McpStdioServerConfig, PostToolUseHookInput, SyncHookJSONOutput

from core import get_settings
from providers.base import AIClientOptions, AIProvider, AIStreamParser, ProviderType

from .client import ClaudeClient
from .parser import ClaudeStreamParser

logger = logging.getLogger("ClaudeProvider")

# Get settings singleton
_settings = get_settings()

# Project root directory (backend directory)
_BACKEND_ROOT = Path(__file__).parent.parent.parent

# Platform detection
_IS_WINDOWS = sys.platform == "win32"


def _get_cli_path() -> Optional[str]:
    """Get the CLI path based on platform.

    On Windows, returns None to use the native Claude Code CLI.
    On Linux/macOS, returns the path to the bundled patched CLI.
    """
    if _IS_WINDOWS:
        return None  # Use native Claude Code CLI
    return str(_BACKEND_ROOT / "bundled" / "cli.js")


def _get_claude_working_dir() -> str:
    """Get a valid working directory for Claude subprocess."""
    temp_dir = Path(tempfile.gettempdir()) / "claude-empty"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return str(temp_dir)


class ClaudeProvider(AIProvider):
    """Claude Code provider implementing AIProvider interface.

    This provider wraps the Claude Agent SDK to provide a unified
    interface compatible with the multi-provider abstraction.
    """

    def __init__(self):
        """Initialize the Claude provider."""
        self._parser = ClaudeStreamParser()

    @property
    def provider_type(self) -> ProviderType:
        """Get the provider type identifier."""
        return ProviderType.CLAUDE

    def create_client(self, options: ClaudeAgentOptions) -> ClaudeClient:
        """Create a new Claude client with the given options.

        Args:
            options: ClaudeAgentOptions for client configuration

        Returns:
            ClaudeClient ready for connection
        """
        return ClaudeClient(options)

    def build_options(
        self,
        base_options: AIClientOptions,
        anthropic_calls_capture: Optional[List[str]] = None,
        skip_tool_capture: Optional[List[bool]] = None,
    ) -> ClaudeAgentOptions:
        """Build Claude SDK options from base configuration.

        Args:
            base_options: Provider-agnostic configuration
            anthropic_calls_capture: List to capture anthropic tool calls
            skip_tool_capture: List to capture skip tool usage

        Returns:
            ClaudeAgentOptions ready for client creation
        """
        # Import here to avoid circular imports
        from core.config.tool_config import get_tool_names_by_group

        # Build standalone MCP server configurations
        mcp_servers = self._build_mcp_server_config(base_options)

        # Build allowed tools list
        allowed_tool_names = [
            *get_tool_names_by_group("guidelines"),
            *get_tool_names_by_group("action"),
        ]

        # Create PostToolUse hooks
        hooks = self._build_tool_capture_hooks(anthropic_calls_capture, skip_tool_capture)

        # Determine model
        model = base_options.model
        if not model:
            model = (
                "claude-opus-4-5-20251101"
                if not _settings.use_haiku
                else "claude-haiku-4-5-20251001"
            )

        # Build options
        options = ClaudeAgentOptions(
            model=model,
            system_prompt=base_options.system_prompt,
            cli_path=_get_cli_path(),
            permission_mode="default",
            max_thinking_tokens=base_options.max_thinking_tokens,
            mcp_servers=mcp_servers,
            allowed_tools=allowed_tool_names,
            tools=allowed_tool_names,
            setting_sources=[],
            cwd=base_options.working_dir or _get_claude_working_dir(),
            env={
                "CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK": "true",
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "true",
                "DISABLE_TELEMETRY": "true",
                "DISABLE_ERROR_REPORTING": "true",
                "CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY": "true",
            },
            hooks=hooks,
            include_partial_messages=True,
        )

        # Set session ID for resume
        if base_options.session_id:
            options.resume = base_options.session_id

        return options

    def get_parser(self) -> AIStreamParser:
        """Get the stream parser for Claude messages."""
        return self._parser

    async def check_availability(self) -> bool:
        """Check if Claude Code is available and authenticated.

        Returns:
            True if Claude Code CLI is available
        """
        try:
            # Try to run a simple command to check availability
            process = await asyncio.create_subprocess_exec(
                "claude",
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(process.wait(), timeout=5.0)
            return process.returncode == 0
        except Exception as e:
            logger.warning(f"Claude Code availability check failed: {e}")
            return False

    def _build_mcp_server_config(
        self,
        base_options: AIClientOptions,
    ) -> dict[str, McpStdioServerConfig]:
        """Build MCP server configurations for standalone servers.

        Args:
            base_options: Provider-agnostic configuration

        Returns:
            Dict mapping server names to McpStdioServerConfig
        """
        python_exe = sys.executable
        backend_path = str(_BACKEND_ROOT)

        # Base environment for all MCP servers
        base_env = {
            "PYTHONPATH": backend_path,
            "AGENT_NAME": base_options.agent_name,
        }

        # Add optional environment variables
        if base_options.group_name:
            base_env["AGENT_GROUP"] = base_options.group_name
        if base_options.agent_id is not None:
            base_env["AGENT_ID"] = str(base_options.agent_id)
        if base_options.config_file:
            base_env["CONFIG_FILE"] = base_options.config_file

        # Build action server config
        action_config: McpStdioServerConfig = {
            "command": python_exe,
            "args": ["-m", "mcp_servers.action_server"],
            "env": {**base_env},
        }

        # Build guidelines server config
        guidelines_env = {
            "PYTHONPATH": backend_path,
            "AGENT_NAME": base_options.agent_name,
            "HAS_SITUATION_BUILDER": str(base_options.has_situation_builder).lower(),
        }
        if base_options.group_name:
            guidelines_env["AGENT_GROUP"] = base_options.group_name

        guidelines_config: McpStdioServerConfig = {
            "command": python_exe,
            "args": ["-m", "mcp_servers.guidelines_server"],
            "env": guidelines_env,
        }

        return {
            "action": action_config,
            "guidelines": guidelines_config,
        }

    def _build_tool_capture_hooks(
        self,
        anthropic_calls_capture: Optional[List[str]],
        skip_tool_capture: Optional[List[bool]],
    ) -> Optional[dict]:
        """Build PostToolUse hooks for capturing tool calls.

        Args:
            anthropic_calls_capture: List to append captured situations to
            skip_tool_capture: List to append True when skip tool is called

        Returns:
            Hooks dict for ClaudeAgentOptions, or None if no capture needed
        """
        hook_matchers = []

        # Hook for anthropic tool calls
        if anthropic_calls_capture is not None:

            async def capture_anthropic_tool(
                input_data: PostToolUseHookInput,
                _tool_use_id: Optional[str],
                _ctx: dict,
            ) -> SyncHookJSONOutput:
                """Hook to capture anthropic tool calls."""
                tool_name = input_data.get("tool_name", "")
                if tool_name.endswith("__anthropic"):
                    tool_input = input_data.get("tool_input", {})
                    situation = tool_input.get("situation", "")
                    if situation:
                        anthropic_calls_capture.append(situation)
                        logger.info(f"Captured anthropic tool call: {situation[:100]}...")
                return {"continue_": True}

            hook_matchers.append(
                HookMatcher(matcher="mcp__guidelines__anthropic", hooks=[capture_anthropic_tool])
            )

        # Hook for skip tool calls
        if skip_tool_capture is not None:

            async def capture_skip_tool(
                input_data: PostToolUseHookInput,
                _tool_use_id: Optional[str],
                _ctx: dict,
            ) -> SyncHookJSONOutput:
                """Hook to capture skip tool calls."""
                tool_name = input_data.get("tool_name", "")
                if tool_name.endswith("__skip"):
                    skip_tool_capture.append(True)
                    logger.info("Skip tool detected via hook!")
                return {"continue_": True}

            hook_matchers.append(
                HookMatcher(matcher="mcp__action__skip", hooks=[capture_skip_tool])
            )

        if not hook_matchers:
            return None

        return {"PostToolUse": hook_matchers}
