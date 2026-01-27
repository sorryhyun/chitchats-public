"""
Claude Code provider implementation.

This module provides the ClaudeProvider class that implements AIProvider
for the Claude Agent SDK backend.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import List, Optional

from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk.types import HookMatcher, PostToolUseHookInput, SyncHookJSONOutput
from core import get_settings
from domain.task_identifier import TaskIdentifier

from providers.base import AIClientOptions, AIProvider, AIStreamParser, ProviderType
from providers.base_pool import BaseClientPool
from providers.configs import DEFAULT_CLAUDE_CONFIG
from providers.mcp_config import MCPConfigBuilder, MCPServerEnv

from .client import ClaudeClient
from .parser import ClaudeStreamParser

logger = logging.getLogger("ClaudeProvider")

# Get settings singleton
_settings = get_settings()


class ClaudeClientPool(BaseClientPool[ClaudeClient, ClaudeAgentOptions]):
    """Claude-specific client pool.

    Manages pooling and lifecycle of Claude SDK clients with:
    - Concurrent connection management (semaphore)
    - Per-task locking to prevent duplicate client creation
    - Background cleanup of disconnected clients
    - Session ID tracking for client reuse decisions
    - Retry logic with exponential backoff for transport errors
    - Connection stabilization delay
    """

    # Stabilization delay after each connection (seconds)
    CONNECTION_STABILIZATION_DELAY = 0.05

    def _get_pool_name(self) -> str:
        """Get the pool name for logging."""
        return "ClaudeClientPool"

    def _get_session_id_from_options(self, options: ClaudeAgentOptions) -> str | None:
        """Extract session ID from Claude options (resume field)."""
        return getattr(options, "resume", None)

    def _get_session_id_from_client(self, client: ClaudeClient) -> str | None:
        """Extract session ID from Claude client."""
        if client.options:
            return getattr(client.options, "resume", None)
        return None

    async def _create_client_impl(
        self,
        task_id: TaskIdentifier,
        options: ClaudeAgentOptions,
    ) -> ClaudeClient:
        """Create and connect a new Claude client with retry logic.

        Implements exponential backoff for transport errors.
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                client = ClaudeClient(options)
                await client.connect()

                # Brief delay to let connection stabilize
                await asyncio.sleep(self.CONNECTION_STABILIZATION_DELAY)

                return client
            except Exception as e:
                error_str = str(e)
                if (
                    "ProcessTransport is not ready" in error_str or "transport" in error_str.lower()
                ) and attempt < max_retries - 1:
                    delay = 0.3 * (2**attempt)
                    self._logger.warning(
                        f"Connection failed for {task_id}, retrying in {delay}s (attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(delay)
                else:
                    raise

        raise RuntimeError(f"Failed to create client for {task_id} after {max_retries} retries")


def _get_cli_path() -> Optional[str]:
    """Get the CLI path based on platform and settings.

    Returns None to use the native Claude Code CLI when:
    - EXPERIMENTAL_CUSTOM_CLI is set to false

    Returns the bundled patched CLI path when:
    - EXPERIMENTAL_CUSTOM_CLI is set to true
    """
    # Check if custom CLI is enabled
    if not _settings.experimental_custom_cli:
        return None  # Use native Claude Code CLI

    return str(_settings.project_root / "bundled" / "cli.js")


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
        self._pool: Optional[ClaudeClientPool] = None

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

    def get_client_pool(self) -> ClaudeClientPool:
        """Get the client pool for this provider."""
        if self._pool is None:
            self._pool = ClaudeClientPool()
        return self._pool

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
        from mcp_servers.config import get_tool_names_by_group

        # Build MCP servers using centralized builder
        env_config = MCPServerEnv(
            agent_name=base_options.agent_name,
            provider="claude",
            group_name=base_options.group_name,
            agent_id=base_options.agent_id,
            config_file=base_options.config_file,
            has_situation_builder=base_options.has_situation_builder,
        )
        mcp_servers = MCPConfigBuilder.build_all_servers(
            env_config,
            include_etc=True,  # Claude uses etc server
            prefer_venv=False,  # Claude uses sys.executable
        )

        # Build allowed tools list
        allowed_tool_names = [
            *get_tool_names_by_group("guidelines"),
            *get_tool_names_by_group("action"),
            *get_tool_names_by_group("etc"),
        ]

        # Create PostToolUse hooks
        hooks = self._build_tool_capture_hooks(anthropic_calls_capture, skip_tool_capture)

        # Determine model
        model = base_options.model
        if not model:
            model = "claude-opus-4-5-20251101" if not _settings.use_haiku else "claude-haiku-4-5-20251001"

        # Use static config for unchanging settings
        static = DEFAULT_CLAUDE_CONFIG

        # Build options
        options = ClaudeAgentOptions(
            model=model,
            system_prompt=base_options.system_prompt,
            cli_path=_get_cli_path(),
            permission_mode=static.permission_mode,
            max_thinking_tokens=base_options.max_thinking_tokens,
            mcp_servers=mcp_servers,
            allowed_tools=allowed_tool_names,
            tools=allowed_tool_names,
            setting_sources=static.setting_sources,
            cwd=base_options.working_dir or _get_claude_working_dir(),
            env=static.env,
            hooks=hooks,
            include_partial_messages=static.include_partial_messages,
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

    def _build_tool_capture_hooks(
        self,
        anthropic_calls_capture: Optional[List[str]],
        skip_tool_capture: Optional[List[bool]],
    ) -> Optional[dict]:
        """Build PostToolUse hooks for capturing tool calls."""
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

            hook_matchers.append(HookMatcher(matcher="mcp__guidelines__anthropic", hooks=[capture_anthropic_tool]))

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

            hook_matchers.append(HookMatcher(matcher="mcp__action__skip", hooks=[capture_skip_tool]))

        if not hook_matchers:
            return None

        return {"PostToolUse": hook_matchers}
