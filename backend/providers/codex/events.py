"""
Codex event types and factory functions.

This module provides:
- Event type constants for consistent event identification
- Item type constants for content classification
- Factory functions for creating standardized event dictionaries
- Reasoning extraction utilities
"""

import re
from typing import Any, Dict, List, Optional, Tuple


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
