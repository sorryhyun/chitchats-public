"""
Codex constants, event types, and factory functions.

This module provides:
- Event type constants for consistent event identification
- Item type constants for content classification
- App Server method constants (JSON-RPC)
- Format mapping utilities for kebab-case conversion
- Factory functions for creating standardized event dictionaries
- Custom exceptions for session recovery
"""

import os
import re
import shutil
import sys
from typing import Any, Dict, List, Optional, Tuple

# =============================================================================
# Bundled binary path
# =============================================================================

_BUNDLED_EXE_NAME = "codex-x86_64-pc-windows-msvc.exe"


def _find_bundled_codex() -> Optional[str]:
    """Look for bundled Codex binary next to the running app."""
    # When frozen (PyInstaller exe), look next to the exe
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        # Dev mode: project root is 3 levels up from this file
        base = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    path = os.path.join(base, "bundled", _BUNDLED_EXE_NAME)
    return path if os.path.isfile(path) else None


def resolve_codex_path() -> Optional[str]:
    """Return the path to the Codex binary, preferring bundled alpha over PATH."""
    return _find_bundled_codex() or shutil.which("codex")


# =============================================================================
# Exceptions
# =============================================================================


class SessionRecoveryError(Exception):
    """Raised when Codex session is invalid and needs to be restarted with full history.

    This exception signals to the caller (ResponseGenerator) that:
    1. The existing thread_id is invalid (e.g., Codex MCP server was restarted)
    2. A fresh session needs to be started with FULL conversation history
    3. The caller should rebuild conversation context without limits
    """

    def __init__(self, old_thread_id: str, message: str = "Session recovery needed"):
        self.old_thread_id = old_thread_id
        super().__init__(message)


# =============================================================================
# Event Type Constants
# =============================================================================


class EventType:
    """Event type constants for unified Codex protocol."""

    THREAD_STARTED = "thread.started"
    ITEM_COMPLETED = "item.completed"
    CONTENT_DELTA = "content.delta"
    THINKING_DELTA = "thinking.delta"
    ERROR = "error"


class ItemType:
    """Item type constants for content classification."""

    AGENT_MESSAGE = "agent_message"
    REASONING = "reasoning"
    MCP_TOOL_CALL = "mcp_tool_call"


class AppServerMethod:
    """JSON-RPC method names for Codex App Server protocol.

    These are the notification/response methods returned by `codex app-server`.
    """

    # Turn lifecycle
    TURN_STARTED = "turn/started"
    TURN_COMPLETED = "turn/completed"

    # Item lifecycle
    ITEM_STARTED = "item/started"
    ITEM_COMPLETED = "item/completed"

    # Streaming deltas
    AGENT_MESSAGE_DELTA = "item/agentMessage/delta"
    REASONING_DELTA = "item/reasoning/textDelta"

    # Tool calls
    MCP_TOOL_CALL_STARTED = "item/mcpToolCall/started"
    MCP_TOOL_CALL_COMPLETED = "item/mcpToolCall/completed"

    # Error/status
    EXEC_ERROR = "item/execError"


class RealtimeMethod:
    """JSON-RPC method names for realtime voice sessions."""

    START = "thread/realtime/start"
    APPEND_AUDIO = "thread/realtime/appendAudio"
    APPEND_TEXT = "thread/realtime/appendText"
    STOP = "thread/realtime/stop"


class RealtimeNotification:
    """JSON-RPC notification methods for realtime voice sessions."""

    STARTED = "thread/realtime/started"
    OUTPUT_AUDIO_DELTA = "thread/realtime/outputAudio/delta"
    ITEM_ADDED = "thread/realtime/itemAdded"
    ERROR = "thread/realtime/error"
    CLOSED = "thread/realtime/closed"


class TurnStatus:
    """Turn completion status values."""

    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    NEEDS_APPROVAL = "needs_approval"


# =============================================================================
# Format Mapping (kebab-case conversion)
# =============================================================================

# Sandbox mode mapping to kebab-case
SANDBOX_MAP: Dict[str, str] = {
    # kebab-case (canonical)
    "danger-full-access": "danger-full-access",
    "workspace-write": "workspace-write",
    "read-only": "read-only",
    # camelCase variants
    "dangerFullAccess": "danger-full-access",
    "workspaceWrite": "workspace-write",
    "readOnly": "read-only",
}

# Approval policy mapping to kebab-case
APPROVAL_POLICY_MAP: Dict[str, str] = {
    # kebab-case (canonical)
    "never": "never",
    "on-request": "on-request",
    "on-failure": "on-failure",
    "untrusted": "untrusted",
    # camelCase variants
    "onRequest": "on-request",
    "onFailure": "on-failure",
}

# Default values
DEFAULT_SANDBOX = "danger-full-access"
DEFAULT_APPROVAL_POLICY = "never"


def map_sandbox(value: str) -> str:
    """Map sandbox value to kebab-case format.

    Args:
        value: Sandbox value in any format (kebab-case or camelCase)

    Returns:
        Kebab-case sandbox value for Codex App Server API
    """
    return SANDBOX_MAP.get(value, DEFAULT_SANDBOX)


def map_approval_policy(value: str) -> str:
    """Map approval policy value to kebab-case format.

    Args:
        value: Approval policy in any format (kebab-case or camelCase)

    Returns:
        Kebab-case approval policy for Codex App Server API
    """
    return APPROVAL_POLICY_MAP.get(value, DEFAULT_APPROVAL_POLICY)


# =============================================================================
# Event Factory Functions
# =============================================================================


def thread_started(thread_id: str) -> Dict[str, Any]:
    """Create a thread.started event."""
    return {
        "type": EventType.THREAD_STARTED,
        "data": {"thread_id": thread_id},
    }


def agent_message(text: str) -> Dict[str, Any]:
    """Create an item.completed event with agent_message type."""
    return {
        "type": EventType.ITEM_COMPLETED,
        "item": {
            "type": ItemType.AGENT_MESSAGE,
            "text": text,
        },
    }


def reasoning(text: str) -> Dict[str, Any]:
    """Create an item.completed event with reasoning type."""
    return {
        "type": EventType.ITEM_COMPLETED,
        "item": {
            "type": ItemType.REASONING,
            "text": text,
        },
    }


def tool_call(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Create an item.completed event with mcp_tool_call type."""
    return {
        "type": EventType.ITEM_COMPLETED,
        "item": {
            "type": ItemType.MCP_TOOL_CALL,
            "tool": name,
            "arguments": arguments,
        },
    }


def error(message: str) -> Dict[str, Any]:
    """Create an error event."""
    return {
        "type": EventType.ERROR,
        "data": {"message": message},
    }


def content_delta(delta: str) -> Dict[str, Any]:
    """Create a content.delta event for streaming text."""
    return {
        "type": EventType.CONTENT_DELTA,
        "delta": delta,
    }


def thinking_delta(delta: str) -> Dict[str, Any]:
    """Create a thinking.delta event for streaming reasoning."""
    return {
        "type": EventType.THINKING_DELTA,
        "delta": delta,
    }


# =============================================================================
# Reasoning Extraction Utilities
# =============================================================================

# Patterns for extracting reasoning from raw notification messages
# Each tuple: (regex pattern, source description for logging)
REASONING_PATTERNS: List[Tuple[str, str]] = [
    # msg.type='agent_reasoning' with msg.text='...' (Python repr style)
    (r"'type':\s*'agent_reasoning'.*?'text':\s*'([^']*)'", "agent_reasoning"),
    # JSON style double quotes
    (r'"type":\s*"agent_reasoning".*?"text":\s*"([^"]*)"', "agent_reasoning"),
    # summary_text patterns
    (r"'type':\s*'summary_text'.*?'text':\s*'([^']*)'", "summary_text"),
    (r'"type":\s*"summary_text".*?"text":\s*"([^"]*)"', "summary_text"),
]


def extract_reasoning_from_raw(raw_msg: str) -> Optional[Tuple[str, str]]:
    """Extract reasoning text from raw notification message.

    Codex notifications have structure:
    params={'_meta': {...}, 'msg': {'type': 'agent_reasoning', 'text': '...'}}

    Args:
        raw_msg: Raw notification message string

    Returns:
        Tuple of (text, source) if found, None otherwise
    """
    for pattern, source in REASONING_PATTERNS:
        match = re.search(pattern, raw_msg, re.DOTALL)
        if match:
            text = match.group(1)
            try:
                text = text.encode().decode('unicode_escape')
            except Exception:
                pass
            if text:
                return (text, source)
    return None
