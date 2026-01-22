"""
Codex event types and factory functions.

This module provides:
- Event type constants for consistent event identification
- Item type constants for content classification
- Factory functions for creating standardized event dictionaries
- Reasoning extraction utilities
- Custom exceptions for session recovery
"""

import re
from typing import Any, Dict, List, Optional, Tuple


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


class EventType:
    """Event type constants for Codex MCP protocol."""

    THREAD_STARTED = "thread.started"
    ITEM_COMPLETED = "item.completed"
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


class TurnStatus:
    """Turn completion status values."""

    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    NEEDS_APPROVAL = "needs_approval"


# Factory functions for creating event dictionaries


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


# Reasoning extraction utilities

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
