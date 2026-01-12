"""
Codex CLI stream parser implementation.

This module parses streaming JSON output from the Codex CLI
and converts it to the unified ParsedStreamMessage format.

Codex Event Types:
    - thread.started: Thread creation, contains thread_id
    - turn.started: New turn in conversation
    - item.started: Start of a response item
    - item.completed: Completed response item with content
    - error: Error event
"""

import json
import logging
from typing import Any, Dict

from providers.base import AIStreamParser, ParsedStreamMessage

logger = logging.getLogger("CodexStreamParser")


class CodexStreamParser(AIStreamParser):
    """Parser for Codex CLI streaming JSON output.

    Codex outputs newline-delimited JSON events that need to be
    translated to our unified message format.

    Event Structure:
        {
            "type": "event_type",
            "data": { ... event-specific data ... }
        }
    """

    @staticmethod
    def parse_message(
        message: Any,
        current_response: str,
        current_thinking: str,
    ) -> ParsedStreamMessage:
        """Parse a streaming message from Codex CLI.

        Args:
            message: JSON event dict from Codex CLI
            current_response: Accumulated response text so far
            current_thinking: Accumulated thinking text so far

        Returns:
            ParsedStreamMessage with extracted fields and updated accumulated text
        """
        # Handle raw JSON string
        if isinstance(message, str):
            try:
                message = json.loads(message)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse JSON: {message[:100]}...")
                return ParsedStreamMessage(
                    response_text=current_response,
                    thinking_text=current_thinking,
                )

        # Handle dict events
        if not isinstance(message, dict):
            return ParsedStreamMessage(
                response_text=current_response,
                thinking_text=current_thinking,
            )

        event_type = message.get("type", "")
        data = message.get("data", {})

        content_delta = ""
        thinking_delta = ""
        new_session_id = None
        skip_tool_called = False
        memory_entries = []
        anthropic_calls = []

        # Handle different event types
        if event_type == "thread.started":
            # Extract thread_id for session resume
            new_session_id = data.get("thread_id") or data.get("id")
            logger.debug(f"Codex thread started: {new_session_id}")

        elif event_type == "item.completed":
            # Completed response item - extract content
            item = data.get("item", data)
            item_type = item.get("type", "")

            if item_type == "message":
                # Extract message content
                content_list = item.get("content", [])
                for content_block in content_list:
                    block_type = content_block.get("type", "")
                    if block_type == "text":
                        content_delta += content_block.get("text", "")
                    elif block_type == "thinking":
                        thinking_delta += content_block.get("text", "")
                        thinking_delta += content_block.get("thinking", "")

            elif item_type == "function_call":
                # Handle tool calls
                tool_name = item.get("name", "")
                tool_args = item.get("arguments", {})

                if tool_name.endswith("skip") or tool_name == "skip":
                    skip_tool_called = True
                    logger.info("Codex skip tool called")

                elif tool_name.endswith("memorize") or tool_name == "memorize":
                    memory_entry = tool_args.get("memory_entry", "")
                    if memory_entry:
                        memory_entries.append(memory_entry)
                        logger.info(f"Codex memorize: {memory_entry}")

                elif tool_name.endswith("anthropic") or tool_name == "anthropic":
                    situation = tool_args.get("situation", "")
                    if situation:
                        anthropic_calls.append(situation)
                        logger.info(f"Codex anthropic call: {situation[:50]}...")

        elif event_type == "item.started":
            # Item starting - might have initial content
            item = data.get("item", data)
            item_type = item.get("type", "")

            if item_type == "message":
                content_list = item.get("content", [])
                for content_block in content_list:
                    block_type = content_block.get("type", "")
                    if block_type == "text":
                        content_delta += content_block.get("text", "")

        elif event_type == "content.delta":
            # Streaming content delta
            delta_data = data.get("delta", data)
            content_delta = delta_data.get("text", "")

        elif event_type == "thinking.delta":
            # Streaming thinking delta
            delta_data = data.get("delta", data)
            thinking_delta = delta_data.get("text", "")
            thinking_delta += delta_data.get("thinking", "")

        elif event_type == "error":
            # Error event
            error_msg = data.get("message", data.get("error", str(data)))
            logger.error(f"Codex error: {error_msg}")
            content_delta = f"Error: {error_msg}"

        # Return accumulated text with deltas applied
        return ParsedStreamMessage(
            response_text=current_response + content_delta,
            thinking_text=current_thinking + thinking_delta,
            session_id=new_session_id,
            skip_used=skip_tool_called,
            memory_entries=memory_entries,
            anthropic_calls=anthropic_calls,
        )

    @staticmethod
    def parse_json_line(line: str) -> Dict[str, Any]:
        """Parse a single JSON line from Codex output.

        Args:
            line: Raw line from Codex CLI stdout

        Returns:
            Parsed dict or empty dict on parse failure
        """
        line = line.strip()
        if not line:
            return {}

        try:
            return json.loads(line)
        except json.JSONDecodeError:
            logger.debug(f"Non-JSON line: {line[:100]}")
            return {}
