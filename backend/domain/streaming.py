"""
Domain types for streaming responses.

This module provides typed event classes and a ResponseAccumulator
for managing state during agent response streaming.
"""

from dataclasses import dataclass, field
from typing import Any, Optional, Union

# Import ParsedStreamMessage for type hints
from providers.base import ParsedStreamMessage


@dataclass
class StreamStartEvent:
    """Event emitted at the start of a streaming response."""

    temp_id: str

    def to_dict(self) -> dict:
        """Convert to dict for backward compatibility with existing consumers."""
        return {
            "type": "stream_start",
            "temp_id": self.temp_id,
        }


@dataclass
class ContentDeltaEvent:
    """Event emitted when new content is generated."""

    temp_id: str
    delta: str

    def to_dict(self) -> dict:
        """Convert to dict for backward compatibility with existing consumers."""
        return {
            "type": "content_delta",
            "delta": self.delta,
            "temp_id": self.temp_id,
        }


@dataclass
class ThinkingDeltaEvent:
    """Event emitted when new thinking text is generated."""

    temp_id: str
    delta: str

    def to_dict(self) -> dict:
        """Convert to dict for backward compatibility with existing consumers."""
        return {
            "type": "thinking_delta",
            "delta": self.delta,
            "temp_id": self.temp_id,
        }


@dataclass
class StreamEndEvent:
    """Event emitted at the end of a streaming response."""

    temp_id: str
    response_text: Optional[str]
    thinking_text: str
    session_id: Optional[str]
    memory_entries: list[str]
    anthropic_calls: list[str]
    skipped: bool

    def to_dict(self) -> dict:
        """Convert to dict for backward compatibility with existing consumers."""
        return {
            "type": "stream_end",
            "temp_id": self.temp_id,
            "response_text": self.response_text,
            "thinking_text": self.thinking_text,
            "session_id": self.session_id,
            "memory_entries": self.memory_entries,
            "anthropic_calls": self.anthropic_calls,
            "skipped": self.skipped,
        }


# Type alias for all streaming events
StreamEvent = Union[StreamStartEvent, ContentDeltaEvent, ThinkingDeltaEvent, StreamEndEvent]


@dataclass
class ResponseAccumulator:
    """Accumulates state during streaming response generation.

    Replaces the 6+ manual variables that were tracked during streaming
    in generate_sdk_response:
    - response_text, thinking_text, session_id, skip_tool_called
    - memory_entries, anthropic_calls

    Also provides capture lists for tool hooks.
    """

    response_text: str = ""
    thinking_text: str = ""
    session_id: Optional[str] = None
    skip_tool_called: bool = False
    memory_entries: list[str] = field(default_factory=list)
    anthropic_calls: list[str] = field(default_factory=list)
    # Hook capture lists - these get mutated by PostToolUse hooks
    skip_tool_capture: list[bool] = field(default_factory=list)

    def update_from_parsed(
        self,
        parsed: ParsedStreamMessage,
        temp_id: str,
    ) -> list[StreamEvent]:
        """Update accumulator state from a parsed stream message.

        Args:
            parsed: Parsed message from the stream parser
            temp_id: Temporary ID for this streaming session

        Returns:
            List of StreamEvent objects to yield to consumers
        """
        events: list[StreamEvent] = []

        # Calculate deltas
        content_delta = parsed.response_text[len(self.response_text) :]
        thinking_delta = parsed.thinking_text[len(self.thinking_text) :]

        # Update session if found
        if parsed.session_id:
            self.session_id = parsed.session_id

        # Check skip flag via hook capture (MCP tools detected via PostToolUse hook)
        if self.skip_tool_capture and not self.skip_tool_called:
            self.skip_tool_called = True

        # Collect memory entries
        self.memory_entries.extend(parsed.memory_entries)

        # Update accumulated text
        self.response_text = parsed.response_text
        self.thinking_text = parsed.thinking_text

        # Create delta events
        # Don't yield content deltas after skip tool is called
        # (content after skip is the "reason for skipping" which should be hidden)
        if content_delta and not self.skip_tool_called:
            events.append(ContentDeltaEvent(temp_id=temp_id, delta=content_delta))

        if thinking_delta:
            events.append(ThinkingDeltaEvent(temp_id=temp_id, delta=thinking_delta))

        return events

    def get_streaming_state(self) -> dict[str, Any]:
        """Get the current streaming state for external access.

        Returns:
            Dict with thinking_text, response_text, and skip_used flag.
            When skip is used, response_text is cleared to prevent
            showing skipped content in UI.
        """
        if self.skip_tool_called:
            return {
                "thinking_text": self.thinking_text,
                "response_text": "",
                "skip_used": True,
            }
        return {
            "thinking_text": self.thinking_text,
            "response_text": self.response_text,
        }

    def create_end_event(
        self,
        temp_id: str,
        error: Optional[str] = None,
    ) -> StreamEndEvent:
        """Create the final stream_end event.

        Args:
            temp_id: Temporary ID for this streaming session
            error: Optional error message (if set, response_text is replaced)

        Returns:
            StreamEndEvent with final accumulated state
        """
        response = self.response_text if self.response_text else None

        if error:
            response = error
            skipped = False
        elif self.skip_tool_called:
            response = None
            skipped = True
        else:
            skipped = False

        return StreamEndEvent(
            temp_id=temp_id,
            response_text=response,
            thinking_text=self.thinking_text,
            session_id=self.session_id,
            memory_entries=self.memory_entries,
            anthropic_calls=self.anthropic_calls,
            skipped=skipped,
        )

    def create_interrupted_end_event(
        self,
        temp_id: str,
        session_id: Optional[str],
    ) -> StreamEndEvent:
        """Create a stream_end event for interrupted/cancelled responses.

        Args:
            temp_id: Temporary ID for this streaming session
            session_id: Session ID to preserve for resume

        Returns:
            StreamEndEvent indicating interruption (skipped=True, no content)
        """
        return StreamEndEvent(
            temp_id=temp_id,
            response_text=None,
            thinking_text="",
            session_id=session_id,
            memory_entries=[],
            anthropic_calls=[],
            skipped=True,
        )
