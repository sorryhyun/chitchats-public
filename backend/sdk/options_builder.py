"""
Agent options builder for Claude SDK client configuration.

This module handles the construction of ClaudeAgentOptions, including:
- MCP server creation (action tools, guidelines tools)
- Allowed tools configuration
- Hook setup for capturing tool calls
"""

import logging
from typing import TYPE_CHECKING

from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk.types import HookMatcher, PostToolUseHookInput, SyncHookJSONOutput
from core import get_settings

from .action_tools import create_action_mcp_server
from .config import get_tool_names_by_group
from .guidelines_tools import create_guidelines_mcp_server

if TYPE_CHECKING:
    from domain.contexts import AgentResponseContext

logger = logging.getLogger("OptionsBuilder")

# Get settings singleton
_settings = get_settings()


def build_agent_options(
    context: "AgentResponseContext",
    final_system_prompt: str,
    anthropic_calls_capture: list[str] | None = None,
) -> ClaudeAgentOptions:
    """Build Claude Agent SDK options for an agent.

    Args:
        context: Agent response context containing agent config and metadata
        final_system_prompt: The final system prompt to use
        anthropic_calls_capture: Optional list to capture anthropic tool call situations

    Returns:
        Configured ClaudeAgentOptions ready for client creation
    """
    # Create action MCP server with skip, memorize, and optionally recall tools
    logger.debug(f"Creating action MCP server for agent: '{context.agent_name}'")
    action_mcp_server = create_action_mcp_server(
        agent_name=context.agent_name,
        agent_id=context.agent_id,
        config_file=context.config.config_file,
        long_term_memory_index=context.config.long_term_memory_index,
        group_name=context.group_name,
    )

    # Create guidelines MCP server (handles both DESCRIPTION and ACTIVE_TOOL modes)
    # - DESCRIPTION mode: Guidelines passively injected via tool description
    # - ACTIVE_TOOL mode: Agents call mcp__guidelines__read to retrieve guidelines
    logger.debug(
        f"Creating guidelines MCP server for agent: '{context.agent_name}' (mode: {_settings.read_guideline_by})"
    )
    guidelines_mcp_server = create_guidelines_mcp_server(
        agent_name=context.agent_name,
        has_situation_builder=context.has_situation_builder,
        group_name=context.group_name,
    )

    # Build allowed tools list using group-based approach
    allowed_tool_names = [*get_tool_names_by_group("guidelines"), *get_tool_names_by_group("action")]

    # Build MCP servers dict
    mcp_servers = {
        "guidelines": guidelines_mcp_server,
        "action": action_mcp_server,
    }

    # Create PostToolUse hook to capture anthropic tool calls
    hooks = _build_anthropic_capture_hooks(anthropic_calls_capture)

    options = ClaudeAgentOptions(
        model="claude-opus-4-5-20251101" if not _settings.use_haiku else "claude-haiku-4-5-20251001",
        system_prompt=final_system_prompt,
        permission_mode="default",
        max_thinking_tokens=32768,
        mcp_servers=mcp_servers,
        allowed_tools=allowed_tool_names,
        tools=allowed_tool_names,
        setting_sources=[],
        cwd="/tmp/claude-empty",
        env={"CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK": "true"},
        hooks=hooks,
        include_partial_messages=True,
    )

    if context.session_id:
        options.resume = context.session_id

    return options


def _build_anthropic_capture_hooks(
    anthropic_calls_capture: list[str] | None,
) -> dict | None:
    """Build PostToolUse hooks for capturing anthropic tool calls.

    Args:
        anthropic_calls_capture: List to append captured situations to, or None to skip

    Returns:
        Hooks dict for ClaudeAgentOptions, or None if no capture needed
    """
    if anthropic_calls_capture is None:
        return None

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
                logger.info(f"Captured anthropic tool call: {situation[:100]}...")
        return {"continue_": True}

    return {"PostToolUse": [HookMatcher(matcher="mcp__guidelines__anthropic", hooks=[capture_anthropic_tool])]}
