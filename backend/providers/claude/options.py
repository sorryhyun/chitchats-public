"""
Agent options builder for Claude SDK client configuration.

This module handles the construction of ClaudeAgentOptions, including:
- MCP server configuration (standalone stdio servers)
- Allowed tools configuration
- Hook setup for capturing tool calls
"""

import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk.types import HookMatcher, McpStdioServerConfig, PostToolUseHookInput, SyncHookJSONOutput
from core import get_settings
# Import directly from submodule to avoid circular import through sdk/__init__.py
from sdk.config.tool_config import get_tool_names_by_group

if TYPE_CHECKING:
    from domain.contexts import AgentResponseContext

logger = logging.getLogger("OptionsBuilder")

# Get settings singleton
_settings = get_settings()


# Project root directory (backend directory)
_BACKEND_ROOT = Path(__file__).parent.parent.parent

# Platform detection
_IS_WINDOWS = sys.platform == "win32"


def _get_cli_path() -> str | None:
    """Get the CLI path based on environment configuration.

    Returns the bundled CLI path only if experimental_custom_cli=true is set
    and not on Windows. Otherwise returns None to use the default Claude Code CLI.
    """
    if _IS_WINDOWS:
        return None
    if os.environ.get("EXPERIMENTAL_CUSTOM_CLI", "").lower() == "true":
        return str(_BACKEND_ROOT / "bundled" / "cli.js")
    return None


def _get_claude_working_dir() -> str:
    """Get a valid working directory for Claude subprocess.

    Creates and returns a cross-platform temporary directory.
    """
    # Use system temp directory for cross-platform compatibility
    temp_dir = Path(tempfile.gettempdir()) / "claude-empty"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return str(temp_dir)


def _get_python_executable() -> str:
    """Get the Python executable path for MCP servers."""
    return sys.executable


def _build_mcp_server_config(
    context: "AgentResponseContext",
) -> dict[str, McpStdioServerConfig]:
    """Build MCP server configurations for standalone servers.

    Args:
        context: Agent response context containing agent config and metadata

    Returns:
        Dict mapping server names to McpStdioServerConfig
    """
    python_exe = _get_python_executable()
    backend_path = str(_BACKEND_ROOT)

    # Base environment for all MCP servers
    base_env = {
        "PYTHONPATH": backend_path,
        "AGENT_NAME": context.agent_name,
    }

    # Add optional environment variables
    if context.group_name:
        base_env["AGENT_GROUP"] = context.group_name
    if context.agent_id is not None:
        base_env["AGENT_ID"] = str(context.agent_id)
    if context.config.config_file:
        base_env["CONFIG_FILE"] = context.config.config_file

    # Build action server config
    action_config: McpStdioServerConfig = {
        "command": python_exe,
        "args": ["-m", "mcp_servers.action_server"],
        "env": {**base_env},
    }

    # Build guidelines server config
    guidelines_env = {
        "PYTHONPATH": backend_path,
        "AGENT_NAME": context.agent_name,
        "HAS_SITUATION_BUILDER": str(context.has_situation_builder).lower(),
    }
    if context.group_name:
        guidelines_env["AGENT_GROUP"] = context.group_name

    guidelines_config: McpStdioServerConfig = {
        "command": python_exe,
        "args": ["-m", "mcp_servers.guidelines_server"],
        "env": guidelines_env,
    }

    return {
        "action": action_config,
        "guidelines": guidelines_config,
    }


def build_agent_options(
    context: "AgentResponseContext",
    final_system_prompt: str,
    anthropic_calls_capture: list[str] | None = None,
    skip_tool_capture: list[bool] | None = None,
) -> ClaudeAgentOptions:
    """Build Claude Agent SDK options for an agent.

    Args:
        context: Agent response context containing agent config and metadata
        final_system_prompt: The final system prompt to use
        anthropic_calls_capture: Optional list to capture anthropic tool call situations
        skip_tool_capture: Optional list to capture skip tool usage (append True when skip is called)

    Returns:
        Configured ClaudeAgentOptions ready for client creation
    """
    # Build standalone MCP server configurations
    logger.debug(f"Building MCP server configs for agent: '{context.agent_name}'")
    mcp_servers = _build_mcp_server_config(context)

    # Build allowed tools list using group-based approach
    allowed_tool_names = [*get_tool_names_by_group("guidelines"), *get_tool_names_by_group("action")]

    # Create PostToolUse hooks to capture tool calls (anthropic, skip)
    hooks = _build_tool_capture_hooks(anthropic_calls_capture, skip_tool_capture)

    options = ClaudeAgentOptions(
        model="claude-opus-4-5-20251101" if not _settings.use_haiku else "claude-haiku-4-5-20251001",
        system_prompt=final_system_prompt,
        cli_path=_get_cli_path(),
        permission_mode="default",
        max_thinking_tokens=32768,
        mcp_servers=mcp_servers,
        allowed_tools=allowed_tool_names,
        tools=allowed_tool_names,
        setting_sources=[],
        cwd=_get_claude_working_dir(),
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

    if context.session_id:
        options.resume = context.session_id

    return options


def _build_tool_capture_hooks(
    anthropic_calls_capture: list[str] | None,
    skip_tool_capture: list[bool] | None,
) -> dict | None:
    """Build PostToolUse hooks for capturing tool calls (anthropic, skip).

    Args:
        anthropic_calls_capture: List to append captured situations to, or None to skip
        skip_tool_capture: List to append True when skip tool is called, or None to skip

    Returns:
        Hooks dict for ClaudeAgentOptions, or None if no capture needed
    """
    hook_matchers = []

    # Hook for anthropic tool calls
    if anthropic_calls_capture is not None:

        async def capture_anthropic_tool(
            input_data: PostToolUseHookInput, _tool_use_id: str | None, _ctx: dict
        ) -> SyncHookJSONOutput:
            """Hook to capture anthropic tool calls."""
            tool_name = input_data.get("tool_name", "")
            if tool_name.endswith("__anthropic"):
                tool_input = input_data.get("tool_input", {})
                situation = tool_input.get("situation", "")
                if situation:
                    anthropic_calls_capture.append(situation)
                    logger.info(f"🔒 Captured anthropic tool call: {situation[:100]}...")
            return {"continue_": True}

        hook_matchers.append(HookMatcher(matcher="mcp__guidelines__anthropic", hooks=[capture_anthropic_tool]))

    # Hook for skip tool calls
    if skip_tool_capture is not None:

        async def capture_skip_tool(
            input_data: PostToolUseHookInput, _tool_use_id: str | None, _ctx: dict
        ) -> SyncHookJSONOutput:
            """Hook to capture skip tool calls."""
            tool_name = input_data.get("tool_name", "")
            if tool_name.endswith("__skip"):
                skip_tool_capture.append(True)
                logger.info("⏭️  Skip tool detected via hook!")
            return {"continue_": True}

        hook_matchers.append(HookMatcher(matcher="mcp__action__skip", hooks=[capture_skip_tool]))

    if not hook_matchers:
        return None

    return {"PostToolUse": hook_matchers}
