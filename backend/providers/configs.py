"""
Provider configuration classes.

This module defines configuration classes for all AI providers,
separating static/startup settings from dynamic per-session settings.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# =============================================================================
# Claude Provider Configs
# =============================================================================


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
            # Prevent subprocess from opening browser (Windows fix)
            "BROWSER": "",
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

    # Model to use (e.g., "claude-opus-4-6")
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


# =============================================================================
# Codex Provider Configs
# =============================================================================


@dataclass
class CodexStartupConfig:
    """Configuration passed to `codex app-server` at launch time.

    These settings are static and apply to all turns/threads.
    Passed via -c flags and --disable/--enable options.
    """

    # Approval policy: "never", "on-request", "on-failure", "untrusted"
    # "never" = non-interactive mode, auto-approve all actions
    approval_policy: str = "never"

    # Sandbox mode: "danger-full-access", "workspace-write", "read-only"
    # "danger-full-access" = no sandbox restrictions
    sandbox: str = "danger-full-access"

    # Config overrides (passed via -c key=value)
    config_overrides: Dict[str, Any] = field(
        default_factory=lambda: {
            # Feature flags
            "features.shell_tool": False,  # Disables: shell, local_shell, container.exec, shell_command
            "features.unified_exec": False,  # Disables: exec_command, write_stdin
            "features.apply_patch_freeform": False,  # Disables: apply_patch
            "features.collab": False,  # Disables: spawn_agent, send_input, wait, close_agent
            "features.child_agents_md": False,  # Disables child agents markdown
            # Tool settings
            "tools.view_image": False,  # Agents receive images directly
            "web_search": "disabled",
            # "project_doc_max_bytes": 0,
            "show_raw_agent_reasoning": True,
            "model_verbosity": "medium",
            "model_reasoning_summary": "detailed",
        }
    )

    # MCP server configurations (passed via -c mcp_servers.*)
    # Format: {"server_name": {"command": "...", "args": [...], "env": {...}, "cwd": "..."}}
    mcp_servers: Dict[str, Any] = field(default_factory=dict)

    def to_cli_args(self) -> List[str]:
        """Convert config to CLI arguments for subprocess.

        Returns:
            List of CLI arguments (e.g., ["-c", "features.shell_tool=false", "-c", "web_search=disabled"])
        """
        args: List[str] = []

        # Add -c flags for config overrides
        for key, value in self.config_overrides.items():
            args.extend(["-c", f"{key}={_to_toml_value(value)}"])

        # Add -c flags for MCP servers
        for server_name, server_config in self.mcp_servers.items():
            prefix = f"mcp_servers.{server_name}"
            args.extend(_flatten_mcp_config(prefix, server_config))

        return args


def _to_toml_value(value: Any) -> str:
    """Convert a Python value to TOML format string."""
    if isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, str):
        # Escape backslashes and quotes for TOML
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    elif isinstance(value, int):
        return str(value)
    elif isinstance(value, list):
        # Format as TOML array
        items = [_to_toml_value(item) for item in value]
        return f"[{', '.join(items)}]"
    else:
        return str(value)


def _flatten_mcp_config(prefix: str, config: Dict[str, Any]) -> List[str]:
    """Flatten MCP server config to -c flags.

    Args:
        prefix: Key prefix (e.g., "mcp_servers.action")
        config: Server config dict with command, args, env, cwd

    Returns:
        List of ["-c", "key=value", ...] arguments
    """
    args: List[str] = []

    for key, value in config.items():
        full_key = f"{prefix}.{key}"

        if key == "env" and isinstance(value, dict):
            # Flatten env vars: mcp_servers.action.env.AGENT_NAME="value"
            for env_key, env_value in value.items():
                args.extend(["-c", f"{full_key}.{env_key}={_to_toml_value(env_value)}"])
        else:
            args.extend(["-c", f"{full_key}={_to_toml_value(value)}"])

    return args


@dataclass
class CodexTurnConfig:
    """Configuration passed per-turn to the App Server.

    These settings can vary per agent/turn and are sent
    in the turn/start JSON-RPC request.

    Note: MCP servers are now configured at app-server startup via
    CodexStartupConfig, not passed per-turn.
    """

    # System prompt for the agent
    developer_instructions: str = ""

    # Model to use (e.g., "o3", "gpt-4.1")
    model: Optional[str] = None

    # Working directory for the session
    cwd: Optional[str] = None


# =============================================================================
# Default Singletons
# =============================================================================

DEFAULT_CLAUDE_CONFIG = ClaudeStaticConfig()
DEFAULT_CODEX_CONFIG = CodexStartupConfig()
