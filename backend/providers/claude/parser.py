"""
Claude SDK stream parser implementation.

This module wraps the existing StreamParser from sdk/stream_parser.py
to provide the AIStreamParser interface for the provider abstraction.
"""

import logging

from claude_agent_sdk import (
    AssistantMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)
from claude_agent_sdk.types import StreamEvent

from providers.base import AIStreamParser, ParsedStreamMessage

logger = logging.getLogger("ClaudeStreamParser")


class ClaudeStreamParser(AIStreamParser):
    """Parser for Claude SDK streaming messages.

    SDK Message Types:
        - StreamEvent: Partial message updates with raw Anthropic API events
        - AssistantMessage: content=[TextBlock, ThinkingBlock, ToolUseBlock, ...]
        - SystemMessage: subtype='sessionStarted', data={'session_id': ...}
        - ResultMessage: Final result with session_id, duration_ms, is_error
    """

    @staticmethod
    def parse_message(
        message: AssistantMessage | SystemMessage | StreamEvent | object,
        current_response: str,
        current_thinking: str,
    ) -> ParsedStreamMessage:
        """Parse a streaming message from Claude SDK.

        Args:
            message: SDK message object (StreamEvent, AssistantMessage, SystemMessage, etc.)
            current_response: Accumulated response text so far
            current_thinking: Accumulated thinking text so far

        Returns:
            ParsedStreamMessage with extracted fields and updated accumulated text
        """
        content_delta = ""
        thinking_delta = ""
        new_session_id: str | None = None
        memory_entries: list[str] = []

        # Handle StreamEvent for partial message updates (real-time streaming)
        if isinstance(message, StreamEvent):
            event = message.event
            if isinstance(event, dict):
                event_type = event.get("type", "")

                # Handle content_block_delta events (text streaming)
                if event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    delta_type = delta.get("type", "")

                    if delta_type == "text_delta":
                        content_delta = delta.get("text", "")
                    elif delta_type == "thinking_delta":
                        thinking_delta = delta.get("thinking", "")

            # Extract session_id from StreamEvent
            if message.session_id:
                new_session_id = message.session_id

            return ParsedStreamMessage(
                response_text=current_response + content_delta,
                thinking_text=current_thinking + thinking_delta,
                session_id=new_session_id,
                skip_used=False,
                memory_entries=memory_entries,
                anthropic_calls=[],
            )

        # Extract session_id from SystemMessage
        if isinstance(message, SystemMessage):
            if message.subtype == "rate_limit":
                logger.warning(f"Rate limited by API (concurrent usage?): {message.data}")
            elif isinstance(message.data, dict) and "session_id" in message.data:
                new_session_id = message.data["session_id"]
                logger.debug(f"Extracted session_id: {new_session_id}")

        # Handle AssistantMessage content
        if isinstance(message, AssistantMessage):
            # Track if we've already streamed content via StreamEvent
            # If so, skip adding text to avoid duplication
            skip_content = bool(current_response)
            skip_thinking = bool(current_thinking)

            for block in message.content:
                # Check for memorize tool calls
                if isinstance(block, ToolUseBlock):
                    if block.name.endswith("__memorize"):
                        if isinstance(block.input, dict):
                            memory_entry = block.input.get("memory_entry", "")
                            if memory_entry:
                                memory_entries.append(memory_entry)
                                logger.info(f"Agent recorded memory: {memory_entry}")

                # Handle thinking blocks (skip if already streamed)
                elif isinstance(block, ThinkingBlock):
                    if not skip_thinking:
                        thinking_delta = block.thinking

                # Handle text blocks (skip if already streamed)
                elif isinstance(block, TextBlock):
                    if not skip_content:
                        content_delta += block.text

        # Return accumulated text with deltas applied
        return ParsedStreamMessage(
            response_text=current_response + content_delta,
            thinking_text=current_thinking + thinking_delta,
            session_id=new_session_id,
            skip_used=False,
            memory_entries=memory_entries,
            anthropic_calls=[],
        )
