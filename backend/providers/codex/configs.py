"""
Codex App Server configuration.

This module defines configuration classes for the Codex provider,
separating startup-time settings from per-turn settings.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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

    # Feature flags (passed via --disable <name>)
    disabled_features: List[str] = field(
        default_factory=lambda: [
            "shell_tool",  # Disables: shell, local_shell, container.exec, shell_command
            "unified_exec",  # Disables: exec_command, write_stdin
            "apply_patch_freeform",  # Disables: apply_patch
            "collab",  # Disables: spawn_agent, send_input, wait, close_agent
            "child_agents_md",  # Disables child agents markdown
        ]
    )

    # Config overrides (passed via -c key=value)
    config_overrides: Dict[str, Any] = field(
        default_factory=lambda: {
            "tools.view_image": False,  # Agents receive images directly
            "web_search": "disabled",
            "project_doc_max_bytes": 0,
            "show_raw_agent_reasoning": True,
            "model_verbosity": "medium",
            "model_reasoning_summary": "detailed",
        }
    )

    def to_cli_args(self) -> List[str]:
        """Convert config to CLI arguments for subprocess.

        Returns:
            List of CLI arguments (e.g., ["--disable", "shell_tool", "-c", "web_search=disabled"])
        """
        args: List[str] = []

        # Add --disable flags for features
        for feature in self.disabled_features:
            args.extend(["--disable", feature])

        # Add -c flags for config overrides
        for key, value in self.config_overrides.items():
            # Format value as TOML
            if isinstance(value, bool):
                toml_value = "true" if value else "false"
            elif isinstance(value, str):
                toml_value = f'"{value}"'
            elif isinstance(value, int):
                toml_value = str(value)
            else:
                toml_value = str(value)

            args.extend(["-c", f"{key}={toml_value}"])

        return args


@dataclass
class CodexTurnConfig:
    """Configuration passed per-turn to the App Server.

    These settings can vary per agent/turn and are sent
    in the turn/start JSON-RPC request.
    """

    # System prompt for the agent
    developer_instructions: str = ""

    # Model to use (e.g., "o3", "gpt-4.1")
    model: Optional[str] = None

    # MCP server configurations
    mcp_servers: Dict[str, Any] = field(default_factory=dict)

    # Working directory for the session
    cwd: Optional[str] = None


# Default startup config singleton
DEFAULT_STARTUP_CONFIG = CodexStartupConfig()
