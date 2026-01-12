"""
Claude SDK stream parser implementation.

This module wraps the existing StreamParser from sdk/stream_parser.py
to provide the AIStreamParser interface for the provider abstraction.
"""

import logging
from typing import Any

from providers.base import AIStreamParser, ParsedStreamMessage

logger = logging.getLogger("ClaudeStreamParser")


class ClaudeStreamParser(AIStreamParser):
    """Parser for Claude SDK streaming messages.

    This wraps the existing parsing logic from sdk/stream_parser.py
    and adapts it to the unified ParsedStreamMessage format.

    SDK Message Types:
        - AssistantMessage: content=[TextBlock, ThinkingBlock, ToolUseBlock, ...]
        - SystemMessage: subtype='sessionStarted', data={'session_id': ...}
        - ResultMessage: Final result with session_id, duration_ms, is_error
    """

    @staticmethod
    def parse_message(
        message: Any,
        current_response: str,
        current_thinking: str,
    ) -> ParsedStreamMessage:
        """Parse a streaming message from Claude SDK.

        Args:
            message: SDK message object (AssistantMessage, SystemMessage, etc.)
            current_response: Accumulated response text so far
            current_thinking: Accumulated thinking text so far

        Returns:
            ParsedStreamMessage with extracted fields and updated accumulated text
        """
        content_delta = ""
        thinking_delta = ""
        new_session_id = None
        skip_tool_called = False
        memory_entries = []
        anthropic_calls = []

        # Extract session_id from SystemMessage
        if hasattr(message, "__class__") and message.__class__.__name__ == "SystemMessage":
            if hasattr(message, "data") and isinstance(message.data, dict):
                if "session_id" in message.data:
                    new_session_id = message.data["session_id"]
                    logger.debug(f"Extracted session_id: {new_session_id}")

        # Handle content
        if hasattr(message, "text"):
            content_delta = message.text
        elif hasattr(message, "content"):
            if isinstance(message.content, str):
                content_delta = message.content
            elif isinstance(message.content, list):
                for block in message.content:
                    block_type = getattr(block, "type", None) or (
                        block.get("type") if isinstance(block, dict) else None
                    )

                    # Check for tool calls
                    # Note: MCP tools (skip, anthropic) are detected via PostToolUse hooks
                    # Only memorize is detected here as fallback for memory_entries
                    if block_type == "tool_use":
                        tool_name = getattr(block, "name", None) or (
                            block.get("name") if isinstance(block, dict) else None
                        )

                        if tool_name and tool_name.endswith("__memorize"):
                            tool_input = getattr(block, "input", None) or (
                                block.get("input") if isinstance(block, dict) else None
                            )
                            if tool_input and isinstance(tool_input, dict):
                                memory_entry = tool_input.get("memory_entry", "")
                                if memory_entry:
                                    memory_entries.append(memory_entry)
                                    logger.info(f"Agent recorded memory: {memory_entry}")

                    # Handle thinking blocks
                    block_class_name = block.__class__.__name__ if hasattr(block, "__class__") else ""
                    if block_class_name == "ThinkingBlock" or (
                        hasattr(block, "type") and block.type == "thinking"
                    ):
                        if hasattr(block, "thinking"):
                            thinking_delta = block.thinking
                        elif hasattr(block, "text"):
                            thinking_delta = block.text
                    elif isinstance(block, dict) and block.get("type") == "thinking":
                        thinking_delta = block.get("thinking", block.get("text", ""))
                    else:
                        # Handle text content blocks
                        if hasattr(block, "text"):
                            content_delta += block.text
                        elif isinstance(block, dict) and block.get("type") == "text":
                            content_delta += block.get("text", "")

        # Return accumulated text with deltas applied
        return ParsedStreamMessage(
            response_text=current_response + content_delta,
            thinking_text=current_thinking + thinking_delta,
            session_id=new_session_id,
            skip_used=skip_tool_called,
            memory_entries=memory_entries,
            anthropic_calls=anthropic_calls,
        )
