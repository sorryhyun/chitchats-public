"""MCP server mode and Tauri sidecar detection."""

import os
import sys

from .paths import setup_paths


def is_tauri_sidecar() -> bool:
    """Check if running as a Tauri sidecar."""
    return os.environ.get("TAURI_SIDECAR") == "1" or "--sidecar" in sys.argv


def run_mcp_server(server_type: str) -> None:
    """Run in MCP server mode (for self-spawn from bundled exe).

    This is called when the exe is invoked with --mcp-server argument,
    allowing Codex to spawn this exe as an MCP server subprocess.

    Args:
        server_type: One of "action", "guidelines", "etc", "image", "social"
    """
    setup_paths()

    from mcp_servers.base import run_stdio

    if server_type == "action":
        from mcp_servers.action_server import from_env
    elif server_type == "guidelines":
        from mcp_servers.guidelines_server import from_env
    elif server_type == "etc":
        from mcp_servers.etc_server import from_env
    elif server_type == "image":
        from mcp_servers.image_server import from_env
    elif server_type == "social":
        from mcp_servers.social_server import from_env
    else:
        print(f"Unknown MCP server type: {server_type}", file=sys.stderr)
        print("Valid types: action, guidelines, etc, image, social", file=sys.stderr)
        sys.exit(1)

    run_stdio(server_type.capitalize(), from_env)
