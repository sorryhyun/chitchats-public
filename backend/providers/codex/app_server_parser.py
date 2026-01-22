"""
Codex App Server stream parser.

This module parses streaming events from Codex App Server and converts them
to the unified ParsedStreamMessage format.

App Server Streaming Format:
    {"timestamp": "...", "type": "response_item", "payload": {...}}
    {"timestamp": "...", "type": "response_completed", "payload": {...}}

Event Types:
    - response_item: A response item (message, tool call, etc.)
        - payload.type = "message": Chat message
            - payload.role = "assistant": Assistant response (what we want)
            - payload.role = "user"/"developer": Context messages (skip)
        - payload.content[]: Array of content blocks
            - type = "output_text": Text response
            - type = "reasoning": Thinking/reasoning text
            - type = "tool_use": Tool call
    - response_completed: Turn/response finished
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("AppServerParser")


@dataclass
class AppServerEvent:
    """Parsed App Server streaming event."""

    event_type: str  # "response_item", "response_completed", etc.
    timestamp: Optional[str] = None

    # For response_item events
    payload_type: Optional[str] = None  # "message", "tool_use", etc.
    role: Optional[str] = None  # "assistant", "user", "developer"
    content_blocks: Optional[List[Dict[str, Any]]] = None

    # Extracted content
    text_delta: str = ""
    reasoning_delta: str = ""
    tool_calls: Optional[List[Dict[str, Any]]] = None

    # Flags
    is_completed: bool = False
    is_assistant_message: bool = False


def parse_streaming_event(raw_event: Dict[str, Any]) -> AppServerEvent:
    """Parse a raw App Server streaming event.

    Args:
        raw_event: Raw event dict from App Server stdout

    Returns:
        Parsed AppServerEvent
    """
    event_type = raw_event.get("type", "")
    timestamp = raw_event.get("timestamp")
    payload = raw_event.get("payload", {})

    event = AppServerEvent(
        event_type=event_type,
        timestamp=timestamp,
    )

    # Handle completion events
    if event_type in ("response_completed", "turn_completed"):
        event.is_completed = True
        logger.debug(f"[AppServerParser] {event_type}")
        return event

    # Handle response_item format (messages with role)
    if event_type == "response_item":
        event.payload_type = payload.get("type", "")
        event.role = payload.get("role", "")
        event.content_blocks = payload.get("content", [])

        # Only process assistant messages for response text
        if event.payload_type == "message" and event.role == "assistant":
            event.is_assistant_message = True
            _extract_content(event)

        logger.debug(
            f"[AppServerParser] response_item: type={event.payload_type}, "
            f"role={event.role}, is_assistant={event.is_assistant_message}"
        )

    # Handle event_msg format (direct message events)
    elif event_type == "event_msg":
        payload_type = payload.get("type", "")

        if payload_type == "agent_message":
            # This is the assistant's response
            event.is_assistant_message = True
            message = payload.get("message", "")
            if message:
                event.text_delta = message
            logger.debug(f"[AppServerParser] event_msg/agent_message: {len(message)} chars")

        elif payload_type == "agent_reasoning":
            # Reasoning text
            text = payload.get("text", "")
            if text:
                event.reasoning_delta = text
            logger.debug(f"[AppServerParser] event_msg/agent_reasoning: {len(text)} chars")

        elif payload_type == "turn_completed":
            event.is_completed = True
            logger.debug("[AppServerParser] event_msg/turn_completed")

    return event


def _extract_content(event: AppServerEvent) -> None:
    """Extract text and reasoning from content blocks.

    Args:
        event: AppServerEvent to populate with extracted content
    """
    if not event.content_blocks:
        return

    text_parts: List[str] = []
    reasoning_parts: List[str] = []
    tool_calls: List[Dict[str, Any]] = []

    for block in event.content_blocks:
        block_type = block.get("type", "")

        if block_type == "output_text":
            text = block.get("text", "")
            if text:
                text_parts.append(text)

        elif block_type == "text":
            # Alternative text block format
            text = block.get("text", "")
            if text:
                text_parts.append(text)

        elif block_type == "reasoning":
            text = block.get("text", "")
            if text:
                reasoning_parts.append(text)

        elif block_type == "tool_use":
            tool_calls.append({
                "id": block.get("id", ""),
                "name": block.get("name", ""),
                "input": block.get("input", {}),
            })

    event.text_delta = "".join(text_parts)
    event.reasoning_delta = "".join(reasoning_parts)
    if tool_calls:
        event.tool_calls = tool_calls

    if event.text_delta:
        logger.debug(f"[AppServerParser] Extracted text: {len(event.text_delta)} chars")
    if event.reasoning_delta:
        logger.debug(f"[AppServerParser] Extracted reasoning: {len(event.reasoning_delta)} chars")
    if event.tool_calls:
        logger.debug(f"[AppServerParser] Extracted {len(event.tool_calls)} tool calls")


class AppServerStreamAccumulator:
    """Accumulates streaming events into final response.

    Usage:
        accumulator = AppServerStreamAccumulator()
        for event in stream:
            parsed = parse_streaming_event(event)
            accumulator.add_event(parsed)
            if parsed.is_completed:
                break
        result = accumulator.get_result()
    """

    def __init__(self):
        """Initialize accumulator."""
        self._text_parts: List[str] = []
        self._reasoning_parts: List[str] = []
        self._tool_calls: List[Dict[str, Any]] = []
        self._completed = False

    def add_event(self, event: AppServerEvent) -> None:
        """Add a parsed event to the accumulator.

        Args:
            event: Parsed AppServerEvent
        """
        if event.is_completed:
            self._completed = True
            return

        if event.is_assistant_message:
            if event.text_delta:
                self._text_parts.append(event.text_delta)
            if event.reasoning_delta:
                self._reasoning_parts.append(event.reasoning_delta)
            if event.tool_calls:
                self._tool_calls.extend(event.tool_calls)

    def add_text(self, text: str) -> None:
        """Add text directly (for JSON-RPC format).

        Args:
            text: Text to add
        """
        if text:
            self._text_parts.append(text)

    def add_reasoning(self, text: str) -> None:
        """Add reasoning text directly (for JSON-RPC format).

        Args:
            text: Reasoning text to add
        """
        if text:
            self._reasoning_parts.append(text)

    def mark_completed(self) -> None:
        """Mark the response as completed."""
        self._completed = True

    @property
    def is_completed(self) -> bool:
        """Check if response is complete."""
        return self._completed

    @property
    def accumulated_text(self) -> str:
        """Get accumulated text."""
        return "".join(self._text_parts)

    @property
    def accumulated_reasoning(self) -> str:
        """Get accumulated reasoning."""
        return "".join(self._reasoning_parts)

    @property
    def tool_calls(self) -> List[Dict[str, Any]]:
        """Get all tool calls."""
        return self._tool_calls

    def get_result(self) -> Dict[str, Any]:
        """Get final accumulated result.

        Returns:
            Dict with text, reasoning, and tool_calls
        """
        return {
            "text": self.accumulated_text,
            "reasoning": self.accumulated_reasoning,
            "tool_calls": self._tool_calls,
            "completed": self._completed,
        }
