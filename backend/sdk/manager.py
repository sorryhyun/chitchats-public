"""
Agent manager for handling Claude SDK client lifecycle and response generation.

This module provides the AgentManager class which orchestrates agent responses,
manages client interruption, and handles conversation sessions.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import uuid
from typing import AsyncIterator

from claude_agent_sdk import ClaudeSDKClient
from core import get_settings
from domain.contexts import AgentResponseContext
from domain.task_identifier import TaskIdentifier
from i18n.korean import format_with_particles
from infrastructure.logging.agent_logger import append_response_to_debug_log, write_debug_log
from infrastructure.logging.formatters import format_message_for_debug

from .client_pool import ClientPool
from .config import get_debug_config
from .options_builder import build_agent_options
from .stream_parser import StreamParser

# Get settings singleton
_settings = get_settings()

# Configure from settings
DEBUG_MODE = get_debug_config().get("debug", {}).get("enabled", False)

# Platform detection - assistant priming requires patched CLI (not available on Windows)
_IS_WINDOWS = sys.platform == "win32"

THINKING_SIGNATURE = "Er0GCkYICxgCKkBRqpTP7V63o71i5XqXREkl0GXK2gaoptTNxx8OsN0NOH3u5Us2kRco+v54R48QVcxxDKEoEk3U7dno2HxnFOXyEgx1pKgFzl5mKzLwqaAaDICB/pukxNvF4DEwOSIwAHSxwJ0rO8V05U+4w7lHm/BB6lBl4P9dPadJr7+e7OSBvjvRm3YjYMUkspOS1BU1KqQFboJ3iObQ68gem0p5XAVik/9yZGvt/uO+sH2nqjTDHVfrQf/d2X8aTva4d56IbADKi4+D4Ozv7wRsBRVikm9ZvWrR68KxjVanvS3fW9drnZINIytmwemxg9Ny+G95fGgRc48NMeoPWcEoriCM5t9zv8ebkFxlYn41sm9aml1GVYYumtt7eEoGOrl0/zR0fSj4I59CDq0vah3vrNI4pLRANYR2kbjiotkyNzTLT8wzWuB7Z+25fyMeH9ThxeJH4JqDM1gAJbUZJKF3tuuH0Y+RDiQzS9G7rBCB2Nr0PNvtcYBqNcAbzY9/zVlbGBhFrrcRdyvSDj/vG6y/cc4IYZzH6FdyEcAe3mkGCGbF/W3wBr/KTY1BkHKq0/4Gu5/oct49BgZsAH1pkxTgm4oVQjMhjMmw3jMDSkj9ndJI3TVqLJmy67I7WdQPApuYVL8LeZHmmPrcOxBN6Hk2qWxEffjsmBudVGy0cxQTIUmiQDBQ23gVrE7g6wVYkZZaG8FoDYDtVIeMZ9j3A8FsmAhlWhdF2CnjKTqODNLnNpIs6E1zIoVnUbiWOcnObb1dmI3VLKNVfTo3kV6jAvJc2n0DVEq2iFhPh8aN0VyppzK/zE3C8LSs/fWWRKhY5wMr8sKxIP1uU6Wuw4iMoNdgtXKJazPZK+mekpT1IDYysDoZ0Q08aDW0gU4whfINGDgk7FEobWnoPVc2j55MQkJv+8zVUCTNQUFSmoRD2Erq5Uc/ZEapKMOqnBxUON5vB6Z4L2IqEqZB6D6n3pMRf9zZnqD9VCkIy50GgTTpioByKVKNqj4UOQJlobYIbuo3Gek5W2F7v2jaJ2efmCh5GZIu91FUSZ7PerbOOCJAg8CKngXyNtNjOt1IBuIfPVhSi00ieMzdNPqrFTamhxgB"

# Suppress apscheduler debug/info logs
logging.getLogger("apscheduler").setLevel(logging.WARNING)

logger = logging.getLogger("AgentManager")


class AgentManager:
    """Manages Claude SDK clients for agent response generation and interruption."""

    def __init__(self):
        # Note: Authentication can be configured in two ways:
        # 1. Set CLAUDE_API_KEY environment variable with your Anthropic API key
        # 2. Use Claude Code web authentication (when running through Claude Code with subscription)
        # If CLAUDE_API_KEY is not set, the SDK will use Claude Code authentication.
        self.active_clients: dict[TaskIdentifier, ClaudeSDKClient] = {}
        # Client pool for managing SDK client lifecycle
        self.client_pool = ClientPool()
        # Stream parser for SDK message parsing
        self.stream_parser = StreamParser()
        # Streaming state: tracks current thinking text per task during generation
        self.streaming_state: dict[TaskIdentifier, dict] = {}

    async def interrupt_all(self):
        """Interrupt all currently active agent responses."""
        logger.info(f"🛑 Interrupting {len(self.active_clients)} active agent(s)")
        for task_id, client in list(self.active_clients.items()):
            try:
                await client.interrupt()
                logger.debug(f"Interrupted task: {task_id}")
            except Exception as e:
                logger.warning(f"Failed to interrupt task {task_id}: {e}")
        # Clear the active clients after interruption
        self.active_clients.clear()

    async def shutdown(self):
        """
        Gracefully shutdown all pooled clients and wait for cleanup tasks to complete.
        Should be called during application shutdown.
        """
        logger.info("🛑 Shutting down AgentManager")

        # Delegate to client pool
        await self.client_pool.shutdown_all()

        logger.info("✅ AgentManager shutdown complete")

    async def interrupt_room(self, room_id: int):
        """Interrupt all agents responding in a specific room."""
        logger.info(f"🛑 Interrupting agents in room {room_id}")
        tasks_to_interrupt = [task_id for task_id in self.active_clients.keys() if task_id.room_id == room_id]
        for task_id in tasks_to_interrupt:
            try:
                client = self.active_clients.get(task_id)
                if client:
                    await client.interrupt()
                    logger.debug(f"Interrupted task: {task_id}")
                    del self.active_clients[task_id]
            except Exception as e:
                logger.warning(f"Failed to interrupt task {task_id}: {e}")

    def get_streaming_state_for_room(self, room_id: int) -> dict[int, dict]:
        """
        Get current streaming state (thinking/response text) for all agents in a room.

        Args:
            room_id: Room ID

        Returns:
            Dict mapping agent_id to their current streaming state
            Example: {1: {"thinking_text": "...", "response_text": "..."}}
        """
        result = {}
        for task_id, state in self.streaming_state.items():
            if task_id.room_id == room_id:
                result[task_id.agent_id] = state
        return result

    def get_and_clear_streaming_state_for_room(self, room_id: int) -> dict[int, dict]:
        """
        Get and clear streaming state for all agents in a room.

        Used during interrupt to capture partial responses before clearing state.
        This ensures we can save any in-progress responses to DB.

        Args:
            room_id: Room ID

        Returns:
            Dict mapping agent_id to their streaming state (thinking_text, response_text)
        """
        result = {}
        task_ids_to_clear = []

        for task_id, state in self.streaming_state.items():
            if task_id.room_id == room_id:
                # Copy the state (don't just reference it)
                result[task_id.agent_id] = {
                    "thinking_text": state.get("thinking_text", ""),
                    "response_text": state.get("response_text", ""),
                }
                task_ids_to_clear.append(task_id)

        # Clear the streaming state for these tasks
        for task_id in task_ids_to_clear:
            del self.streaming_state[task_id]

        return result

    async def generate_sdk_response(self, context: AgentResponseContext) -> AsyncIterator[dict]:
        """
        Generate a response from an agent using Claude Agent SDK with session persistence.
        This is an async generator that yields streaming events as the response is generated.
        Agent can choose to skip responding by calling the 'skip' tool.
        Agent can record memories by calling the 'memorize' tool (if ENABLE_MEMORY_TOOL=true).

        Args:
            context: AgentResponseContext containing all parameters for response generation

        Yields:
            Streaming events:
            - {"type": "stream_start", "temp_id": str, "agent_id": int, ...}
            - {"type": "content_delta", "delta": str}
            - {"type": "thinking_delta", "delta": str}
            - {"type": "stream_end", "response_text": Optional[str], "thinking_text": str,
               "session_id": str, "memory_entries": list[str], "anthropic_calls": list[str]}
        """

        # Create task identifier from room and agent IDs
        task_id = context.task_id or TaskIdentifier(room_id=context.room_id, agent_id=context.agent_id)

        # Generate a temporary ID for this streaming response
        temp_id = f"temp_{task_id}_{uuid.uuid4().hex[:8]}"

        # Log what the agent is receiving
        logger.info(
            f"🤖 Agent generating response | Session: {context.session_id or 'NEW'} | Task: {task_id} | Temp ID: {temp_id}"
        )
        logger.debug(f"System prompt (first 100 chars): {context.system_prompt[:100]}...")
        logger.debug(f"User message: {context.user_message}")
        if context.conversation_history:
            logger.debug(f"Conversation history (length): {len(context.conversation_history)} chars")

        try:
            # Yield stream_start event
            yield {
                "type": "stream_start",
                "temp_id": temp_id,
            }

            # Build final system prompt
            final_system_prompt = context.system_prompt
            if context.conversation_started:
                final_system_prompt = f"{context.system_prompt}\n\n---\n\nCurrent time: {context.conversation_started}"

            response_text = ""
            thinking_text = ""
            new_session_id = context.session_id
            skip_tool_called = False
            memory_entries = []  # Track memory entries from memorize tool calls
            anthropic_calls = []  # Track anthropic tool calls (via hook)

            # Build agent options with hook to capture anthropic tool calls
            options = build_agent_options(context, final_system_prompt, anthropic_calls)

            # Build the message content - can be string or list of content blocks
            # Content blocks may include inline images within <conversation_so_far>
            if isinstance(context.user_message, list):
                # Content blocks with potential inline images
                content_blocks = context.user_message
                if context.conversation_history:
                    # Prepend conversation history to first text block
                    for block in content_blocks:
                        if block.get("type") == "text":
                            block["text"] = f"{context.conversation_history}\n\n{block['text']}"
                            break
                message_to_send = content_blocks
            else:
                # Simple string message
                message_to_send = context.user_message
                if context.conversation_history:
                    message_to_send = f"{context.conversation_history}\n\n{context.user_message}"

            # Get or create client from pool (reuses client for same room-agent pair)
            # This prevents creating hundreds of agent session files
            pool_key = task_id
            client, _ = await self.client_pool.get_or_create(pool_key, options)

            # Register this client for interruption support
            self.active_clients[task_id] = client
            logger.debug(f"Registered client for task: {task_id}")

            # Initialize streaming state for this task
            self.streaming_state[task_id] = {"thinking_text": "", "response_text": ""}

            # Calculate message length for logging
            if isinstance(message_to_send, list):
                msg_len = sum(len(b.get("text", "")) for b in message_to_send if b.get("type") == "text")
                has_images = any(b.get("type") == "image" for b in message_to_send)
            else:
                msg_len = len(message_to_send)
                has_images = False

            # Write debug log with complete agent input
            await write_debug_log(
                agent_name=context.agent_name,
                task_id=str(task_id),
                system_prompt=final_system_prompt,
                message_to_send=str(message_to_send) if isinstance(message_to_send, list) else message_to_send,
                config_data={
                    "in_a_nutshell": context.config.in_a_nutshell,
                    "characteristics": context.config.characteristics,
                    "recent_events": context.config.recent_events,
                },
                options=options,
                has_situation_builder=context.has_situation_builder,
            )

            # Send the message via query() - this is the correct SDK pattern
            logger.info(
                f"📤 Sending message to agent | Task: {context.task_id} | Message length: {msg_len}{' (with images)' if has_images else ''}"
            )

            try:
                # Check if experimental assistant priming is enabled
                # Assistant priming requires patched CLI (not available on Windows)
                use_priming = _settings.experimental_assistant_priming and not _IS_WINDOWS

                if use_priming:
                    # Build query content with assistant priming message + user message
                    # This uses the SDK's async iterable pattern to send multiple messages
                    agent_name = context.agent_name

                    # Build assistant priming message with Korean particles
                    priming_message = format_with_particles(
                        "{agent_name:은는} 어떻게 생각할까요?", agent_name=agent_name
                    )

                    if isinstance(message_to_send, list) and has_images:
                        # SDK requires async generator for multimodal content (per example.md pattern)
                        async def multimodal_message_generator():
                            # First: assistant priming message
                            yield {
                                "type": "assistant",
                                "message": {
                                    "role": "assistant",
                                    "content": [
                                        {
                                            "type": "thinking",
                                            "thinking": priming_message,
                                            "signature": THINKING_SIGNATURE,
                                        }
                                    ],
                                },
                            }
                            # Second: user message with images
                            yield {
                                "type": "user",
                                "message": {
                                    "role": "user",
                                    "content": message_to_send,  # Content blocks with inline images
                                },
                            }

                        logger.info(f"📸 Sending multimodal message with inline images | Task: {context.task_id}")
                        query_content = multimodal_message_generator()
                    else:
                        # Text-only message: use async generator for assistant + user messages
                        if isinstance(message_to_send, list):
                            # Content blocks but no images - extract text
                            text_content = "\n".join(
                                b.get("text", "") for b in message_to_send if b.get("type") == "text"
                            )
                        else:
                            text_content = message_to_send

                        async def message_generator():
                            # First: assistant priming message
                            yield {
                                "type": "assistant",
                                "message": {
                                    "role": "assistant",
                                    "content": [
                                        {
                                            "type": "thinking",
                                            "thinking": priming_message,
                                            "signature": THINKING_SIGNATURE,
                                        }
                                    ],
                                },
                            }
                            # Second: user message
                            yield {
                                "type": "user",
                                "message": {
                                    "role": "user",
                                    "content": text_content,
                                },
                            }

                        query_content = message_generator()
                else:
                    # Standard mode: send message directly without priming
                    if isinstance(message_to_send, list) and has_images:

                        async def multimodal_message_generator():
                            yield {
                                "type": "user",
                                "message": {
                                    "role": "user",
                                    "content": message_to_send,
                                },
                            }

                        logger.info(f"📸 Sending multimodal message with inline images | Task: {context.task_id}")
                        query_content = multimodal_message_generator()
                    elif isinstance(message_to_send, list):
                        # Content blocks but no images - extract text
                        query_content = "\n".join(b.get("text", "") for b in message_to_send if b.get("type") == "text")
                    else:
                        query_content = message_to_send

                # Add timeout to query to prevent hanging
                await asyncio.wait_for(client.query(query_content), timeout=10.0)
                logger.info(f"📬 Message sent, waiting for response | Task: {context.task_id}")
            except asyncio.TimeoutError:
                logger.error(f"⏰ Timeout sending message to agent | Task: {context.task_id}")
                raise Exception("Timeout sending message to agent")

            # Receive and stream the response
            async for message in client.receive_response():
                # Parse the message using StreamParser
                parsed = self.stream_parser.parse_message(message, response_text, thinking_text)

                # Calculate deltas for yielding
                content_delta = parsed.response_text[len(response_text) :]
                thinking_delta = parsed.thinking_text[len(thinking_text) :]

                # Update session if found
                if parsed.session_id:
                    new_session_id = parsed.session_id

                # Update skip flag
                if parsed.skip_used:
                    skip_tool_called = True

                # Collect memory entries
                memory_entries.extend(parsed.memory_entries)

                # Note: anthropic_calls are now captured via PostToolUse hook
                # (stream parser may not see tool_use blocks for MCP tools)

                # Update accumulated text
                response_text = parsed.response_text
                thinking_text = parsed.thinking_text

                # Update streaming state for polling access
                if task_id in self.streaming_state:
                    self.streaming_state[task_id]["thinking_text"] = thinking_text
                    self.streaming_state[task_id]["response_text"] = response_text

                # Yield delta events for content and thinking
                if content_delta:
                    logger.info(f"🔄 YIELDING content delta | Length: {len(content_delta)}")
                    yield {
                        "type": "content_delta",
                        "delta": content_delta,
                        "temp_id": temp_id,
                    }

                if thinking_delta:
                    logger.info(f"🔄 YIELDING thinking delta | Length: {len(thinking_delta)}")
                    yield {
                        "type": "thinking_delta",
                        "delta": thinking_delta,
                        "temp_id": temp_id,
                    }

                # Debug log each message received from the SDK
                # Configuration loaded from debug.yaml
                if DEBUG_MODE:
                    # Get streaming config from debug.yaml
                    config = get_debug_config()
                    streaming_config = config.get("debug", {}).get("logging", {}).get("streaming", {})

                    if streaming_config.get("enabled", True):
                        # Skip system init messages if configured
                        is_system_init = (
                            message.__class__.__name__ == "SystemMessage"
                            and hasattr(message, "subtype")
                            and message.subtype == "init"
                        )
                        skip_system_init = streaming_config.get("skip_system_init", True)

                        if not (is_system_init and skip_system_init):
                            logger.debug(f"📨 Received message:\n{format_message_for_debug(message)}")

            # Unregister the client when done
            if context.task_id and context.task_id in self.active_clients:
                del self.active_clients[context.task_id]
                logger.debug(f"Unregistered client for task: {context.task_id}")

            # Clean up streaming state
            if task_id in self.streaming_state:
                del self.streaming_state[task_id]

            # Log response summary
            final_response = response_text if response_text else None
            if skip_tool_called:
                logger.info(f"⏭️  Agent skipped | Session: {new_session_id}")
                final_response = None
            else:
                logger.info(
                    f"✅ Response generated | Length: {len(response_text)} chars | Thinking: {len(thinking_text)} chars | Session: {new_session_id}"
                )
            if memory_entries:
                logger.info(f"💾 Recorded {len(memory_entries)} memory entries")
            if anthropic_calls:
                logger.info(f"🔒 Agent called anthropic {len(anthropic_calls)} times: {anthropic_calls}")

            # Append response to debug log
            append_response_to_debug_log(
                agent_name=context.agent_name,
                task_id=context.task_id or "default",
                response_text=final_response or "",
                thinking_text=thinking_text,
                skipped=skip_tool_called,
            )

            # Yield stream_end event with final data
            yield {
                "type": "stream_end",
                "temp_id": temp_id,
                "response_text": final_response,
                "thinking_text": thinking_text,
                "session_id": new_session_id,
                "memory_entries": memory_entries,
                "anthropic_calls": anthropic_calls,
                "skipped": skip_tool_called,
            }

        except asyncio.CancelledError:
            # Task was cancelled due to interruption - this is expected
            # Clean up client from active_clients (but keep it in pool for reuse)
            if context.task_id and context.task_id in self.active_clients:
                del self.active_clients[context.task_id]
                logger.debug(f"Unregistered client for task (interrupted): {context.task_id}")

            # Clean up streaming state
            if task_id in self.streaming_state:
                del self.streaming_state[task_id]

            logger.info(f"🛑 Agent response interrupted | Task: {context.task_id}")
            # Yield stream_end to indicate interruption
            yield {
                "type": "stream_end",
                "temp_id": temp_id,
                "response_text": None,
                "thinking_text": "",
                "session_id": context.session_id,
                "memory_entries": [],
                "anthropic_calls": [],
                "skipped": True,
            }

        except Exception as e:
            # Clean up client on error
            if context.task_id and context.task_id in self.active_clients:
                del self.active_clients[context.task_id]
                logger.debug(f"Unregistered client for task (error cleanup): {context.task_id}")

            # Clean up streaming state
            if task_id in self.streaming_state:
                del self.streaming_state[task_id]

            # Check if this is an interruption-related error
            error_str = str(e).lower()
            if "interrupt" in error_str or "cancelled" in error_str:
                logger.info(f"🛑 Agent response interrupted | Task: {context.task_id}")
                # Yield stream_end to indicate interruption
                yield {
                    "type": "stream_end",
                    "temp_id": temp_id,
                    "response_text": None,
                    "thinking_text": "",
                    "session_id": context.session_id,
                    "memory_entries": [],
                    "anthropic_calls": [],
                    "skipped": True,
                }
                return

            # Remove client from pool on any error to ensure fresh client next time
            # task_id was already created at the beginning of the function
            if task_id in self.client_pool.pool:
                # Use cleanup to properly disconnect in background task
                await self.client_pool.cleanup(task_id)

            logger.error(f"❌ Error generating response: {str(e)}", exc_info=DEBUG_MODE)
            # Yield error as stream_end
            yield {
                "type": "stream_end",
                "temp_id": temp_id,
                "response_text": f"Error generating response: {str(e)}",
                "thinking_text": "",
                "session_id": context.session_id,
                "memory_entries": [],
                "anthropic_calls": [],
                "skipped": False,
            }
