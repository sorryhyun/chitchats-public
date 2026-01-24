"""
Claude provider configuration.

This module defines configuration classes for the Claude provider,
separating static settings from dynamic per-session settings.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ClaudeStaticConfig:
    """Static configuration for Claude sessions.

    These settings are the same for all Claude sessions and don't
    change based on agent or conversation context.
    """

    # Permission mode for the Claude CLI
    # "default" = standard permission handling
    permission_mode: str = "default"

    # Setting sources (empty = no external settings)
    setting_sources: List[str] = field(default_factory=list)

    # Include partial messages in streaming output
    include_partial_messages: bool = True

    # Environment variables for Claude subprocess
    # These disable telemetry and unnecessary traffic
    env: Dict[str, str] = field(
        default_factory=lambda: {
            "CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK": "true",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "true",
            "DISABLE_TELEMETRY": "true",
            "DISABLE_ERROR_REPORTING": "true",
            "CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY": "true",
        }
    )


@dataclass
class ClaudeSessionConfig:
    """Configuration for a Claude session.

    These settings vary per agent/session and are passed
    when creating a new ClaudeAgentOptions.
    """

    # System prompt for the agent
    system_prompt: str = ""

    # Model to use (e.g., "claude-opus-4-5-20251101")
    model: Optional[str] = None

    # Maximum thinking tokens
    max_thinking_tokens: Optional[int] = None

    # MCP server configurations
    mcp_servers: Dict[str, Any] = field(default_factory=dict)

    # Allowed tools list
    allowed_tools: List[str] = field(default_factory=list)

    # Working directory for the session
    cwd: Optional[str] = None

    # Session ID for resuming conversations
    session_id: Optional[str] = None


# Default static config singleton
DEFAULT_STATIC_CONFIG = ClaudeStaticConfig()
