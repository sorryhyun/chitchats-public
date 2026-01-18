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

        logger.info(f"[CodexParser] Event type: {event_type}")

        content_delta = ""
        thinking_delta = ""
        new_session_id = None
        skip_tool_called = False
        memory_entries = []
        anthropic_calls = []

        # Handle different event types
        if event_type == "thread.started":
            # Extract thread_id for session resume
            # Try multiple locations: message root, item, payload, data
            new_session_id = (
                message.get("thread_id")
                or message.get("id")
                or message.get("item", {}).get("thread_id")
                or message.get("item", {}).get("id")
                or message.get("payload", {}).get("thread_id")
                or message.get("payload", {}).get("id")
                or data.get("thread_id")
                or data.get("id")
            )
            logger.info(
                f"[CodexParser] thread.started: session_id={new_session_id}, message_keys={list(message.keys())}"
            )

        elif event_type == "item.completed":
            # Completed response item - extract content
            # Codex uses message["item"] directly (not data or payload)
            item = message.get("item", {})
            item_type = item.get("type", "")

            logger.info(f"[CodexParser] item.completed: item_type={item_type}, keys={list(item.keys())}")

            if item_type == "agent_message":
                # Direct text in item["text"]
                text = item.get("text", "")
                if text:
                    content_delta = text
                    logger.info(f"[CodexParser] Extracted agent_message: {len(text)} chars")

            elif item_type == "message":
                # Content array format (fallback for other structures)
                content_list = item.get("content", [])
                logger.info(f"[CodexParser] item.completed message: {len(content_list)} content blocks")
                for content_block in content_list:
                    block_type = content_block.get("type", "")
                    if block_type == "text":
                        text = content_block.get("text", "")
                        content_delta += text
                    elif block_type == "output_text":
                        text = content_block.get("text", "")
                        content_delta += text
                    elif block_type == "thinking":
                        thinking_delta += content_block.get("text", "")
                        thinking_delta += content_block.get("thinking", "")

            elif item_type == "reasoning":
                # Reasoning content from MCP response
                text = item.get("text", "")
                if text:
                    thinking_delta = text
                    logger.info(f"[CodexParser] Extracted reasoning: {len(text)} chars")

            elif item_type == "mcp_tool_call":
                # Handle MCP tool calls (uses "tool" key instead of "name")
                tool_name = item.get("tool", "")
                tool_args = item.get("arguments", {})

                if tool_name.endswith("skip") or tool_name == "skip":
                    skip_tool_called = True
                    logger.info("Codex MCP skip tool called")

                elif tool_name.endswith("memorize") or tool_name == "memorize":
                    memory_entry = tool_args.get("memory_entry", "")
                    if memory_entry:
                        memory_entries.append(memory_entry)
                        logger.info(f"Codex MCP memorize: {memory_entry}")

                elif tool_name.endswith("anthropic") or tool_name == "anthropic":
                    situation = tool_args.get("situation", "")
                    if situation:
                        anthropic_calls.append(situation)
                        logger.info(f"Codex MCP anthropic call: {situation[:50]}...")

            elif item_type == "function_call":
                # Handle tool calls (CLI mode)
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

        elif event_type == "response_item":
            # Response item - extract from payload.content array
            payload = message.get("payload", {})
            payload_type = payload.get("type", "")
            logger.info(f"[CodexParser] response_item payload_type={payload_type}")
            if payload_type == "message":
                content_list = payload.get("content", [])
                logger.info(f"[CodexParser] content_list has {len(content_list)} blocks")
                for content_block in content_list:
                    block_type = content_block.get("type", "")
                    logger.info(f"[CodexParser] block_type={block_type}")
                    if block_type == "output_text":
                        text = content_block.get("text", "")
                        content_delta += text
                        logger.info(f"[CodexParser] Extracted output_text: {len(text)} chars")
                    elif block_type == "text":
                        text = content_block.get("text", "")
                        content_delta += text
                        logger.info(f"[CodexParser] Extracted text: {len(text)} chars")
                    elif block_type == "thinking":
                        thinking_delta += content_block.get("text", "")
                        thinking_delta += content_block.get("thinking", "")
            elif payload_type == "reasoning":
                # Reasoning/thinking content - extract from summary array
                summary_list = payload.get("summary", [])
                logger.info(f"[CodexParser] reasoning summary has {len(summary_list)} blocks")
                for summary_block in summary_list:
                    block_type = summary_block.get("type", "")
                    if block_type == "summary_text":
                        text = summary_block.get("text", "")
                        thinking_delta += text
                        logger.info(f"[CodexParser] Extracted reasoning: {len(text)} chars")

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
