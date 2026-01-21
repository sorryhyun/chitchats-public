"""
Codex MCP stream parser implementation.

This module parses events from the CodexMCPClient and converts them
to the unified ParsedStreamMessage format.

Event Types (from MCP client):
    - thread.started: Thread creation, contains thread_id
    - item.completed: Completed response item
        - item.type="agent_message": Final response text
        - item.type="reasoning": Thinking/reasoning text
        - item.type="mcp_tool_call": MCP tool call
    - error: Error event
"""

import logging
from typing import Any

from providers.base import AIStreamParser, ParsedStreamMessage

from .events import EventType, ItemType

logger = logging.getLogger("CodexStreamParser")


class CodexStreamParser(AIStreamParser):
    """Parser for Codex MCP client events.

    Translates events from CodexMCPClient to the unified ParsedStreamMessage format.
    """

    @staticmethod
    def parse_message(
        message: Any,
        current_response: str,
        current_thinking: str,
    ) -> ParsedStreamMessage:
        """Parse a message from the Codex MCP client.

        Args:
            message: Event dict from CodexMCPClient
            current_response: Accumulated response text so far
            current_thinking: Accumulated thinking text so far

        Returns:
            ParsedStreamMessage with extracted fields and updated accumulated text
        """
        if not isinstance(message, dict):
            return ParsedStreamMessage(
                response_text=current_response,
                thinking_text=current_thinking,
            )

        event_type = message.get("type", "")
        data = message.get("data", {})

        logger.info(f"[CodexParser] Event type: {event_type}")

        content_delta = ""
        thinking_delta = ""
        new_session_id = None
        skip_tool_called = False
        memory_entries: list[str] = []

        if event_type == EventType.THREAD_STARTED:
            # Extract thread_id for session resume
            new_session_id = data.get("thread_id")
            logger.info(f"[CodexParser] thread.started: session_id={new_session_id}")

        elif event_type == EventType.ITEM_COMPLETED:
            # Completed response item - extract content
            item = message.get("item", {})
            item_type = item.get("type", "")

            logger.info(f"[CodexParser] item.completed: item_type={item_type}")

            if item_type == ItemType.AGENT_MESSAGE:
                # Direct text response
                text = item.get("text", "")
                if text:
                    content_delta = text
                    logger.info(f"[CodexParser] Extracted agent_message: {len(text)} chars")

            elif item_type == ItemType.REASONING:
                # Reasoning/thinking text
                text = item.get("text", "")
                if text:
                    thinking_delta = text
                    logger.info(f"[CodexParser] Extracted reasoning: {len(text)} chars")

            elif item_type == ItemType.MCP_TOOL_CALL:
                # Handle MCP tool calls
                tool_name = item.get("tool", "")
                tool_args = item.get("arguments", {})

                if tool_name == "skip":
                    skip_tool_called = True
                    logger.info("[CodexParser] skip tool called")

                elif tool_name == "memorize":
                    memory_entry = tool_args.get("memory_entry", "")
                    if memory_entry:
                        memory_entries.append(memory_entry)
                        logger.info(f"[CodexParser] memorize: {memory_entry[:50]}...")

        elif event_type == EventType.ERROR:
            # Error event
            error_msg = data.get("message", str(data))
            logger.error(f"[CodexParser] error: {error_msg}")
            content_delta = f"Error: {error_msg}"

        return ParsedStreamMessage(
            response_text=current_response + content_delta,
            thinking_text=current_thinking + thinking_delta,
            session_id=new_session_id,
            skip_used=skip_tool_called,
            memory_entries=memory_entries,
        )
