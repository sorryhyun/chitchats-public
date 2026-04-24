"""
Codex constants, event types, and factory functions.

This module provides:
- Event type constants for consistent event identification
- Item type constants for content classification
- App Server method constants (JSON-RPC)
- Factory functions for creating standardized event dictionaries
"""

from typing import Any, Dict

from providers.base import SessionRecoveryError as SessionRecoveryError

__all__ = ["SessionRecoveryError"]


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
    GENERATED_IMAGE = "generated_image"


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


def generated_image(url: str, media_type: str, prompt: str = "") -> Dict[str, Any]:
    """Create an item.completed event with generated_image type."""
    return {
        "type": EventType.ITEM_COMPLETED,
        "item": {
            "type": ItemType.GENERATED_IMAGE,
            "url": url,
            "media_type": media_type,
            "prompt": prompt,
        },
    }


def error(message: str) -> Dict[str, Any]:
    """Create an error event."""
    return {
        "type": EventType.ERROR,
        "data": {"message": message},
    }


