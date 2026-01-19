"""
Agent manager for handling AI client lifecycle and response generation.

This module provides the AgentManager class which orchestrates agent responses,
manages client interruption, and handles conversation sessions.

Supports multiple AI providers (Claude, Codex) through the provider abstraction layer.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import AsyncIterator

from config import get_debug_config
from domain.contexts import AgentResponseContext
from domain.task_identifier import TaskIdentifier
from infrastructure.logging.agent_logger import append_response_to_debug_log, write_debug_log
from infrastructure.logging.formatters import format_message_for_debug
from providers import (
    AIClient,
    AIClientOptions,
    ClientPoolInterface,
    ProviderType,
    get_provider,
)

# Configure from settings
DEBUG_MODE = get_debug_config().get("debug", {}).get("enabled", False)

# Suppress apscheduler debug/info logs
logging.getLogger("apscheduler").setLevel(logging.WARNING)

logger = logging.getLogger("AgentManager")


class AgentManager:
    """Manages AI clients for agent response generation and interruption.

    Supports multiple providers (Claude, Codex) through the provider abstraction layer.
    Each provider has its own client pool for managing connection lifecycle.
    """

    def __init__(self):
        # Active clients for interruption support (keyed by task identifier)
        self.active_clients: dict[TaskIdentifier, AIClient] = {}
        # Client pools per provider type (lazy-loaded)
        self._client_pools: dict[ProviderType, ClientPoolInterface] = {}
        # Streaming state: tracks current thinking text per task during generation
        self.streaming_state: dict[TaskIdentifier, dict] = {}

    def _get_pool(self, provider_type: ProviderType) -> ClientPoolInterface:
        """Get or create client pool for a provider.

        Args:
            provider_type: The provider type to get pool for

        Returns:
            ClientPoolInterface for the provider
        """
        if provider_type not in self._client_pools:
            provider = get_provider(provider_type)
            self._client_pools[provider_type] = provider.get_client_pool()
        return self._client_pools[provider_type]

    def get_keys_for_agent(self, agent_id: int) -> list[TaskIdentifier]:
        """Get all pool keys for a specific agent across all providers.

        Args:
            agent_id: Agent ID to filter

        Returns:
            List of task identifiers for this agent
        """
        keys = []
        for pool in self._client_pools.values():
            keys.extend(pool.get_keys_for_agent(agent_id))
        return keys

    async def cleanup_client(self, pool_key: TaskIdentifier):
        """Cleanup a specific client across all provider pools.

        Args:
            pool_key: The task identifier for the client to cleanup
        """
        for pool in self._client_pools.values():
            if pool_key in pool.pool:
                await pool.cleanup(pool_key)

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

        # Shutdown all provider pools
        for provider_type, pool in self._client_pools.items():
            logger.info(f"  Shutting down {provider_type.value} pool...")
            await pool.shutdown_all()

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
        Generate a response from an agent using the AI provider with session persistence.
        This is an async generator that yields streaming events as the response is generated.
        Agent can choose to skip responding by calling the 'skip' tool.
        Agent can record memories by calling the 'memorize' tool.

        Supports multiple providers (Claude, Codex) based on context.provider setting.

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

        # Get provider for this context
        provider_type = ProviderType(context.provider)
        provider = get_provider(provider_type)
        logger.info(f"Using provider: {provider_type.value}")

        # Get the pool for this provider (before try block for exception handler access)
        pool = self._get_pool(provider_type)

        # Log what the agent is receiving
        logger.info(
            f"🤖 Agent generating response | Provider: {provider_type.value} | Session: {context.session_id or 'NEW'} | Task: {task_id} | Temp ID: {temp_id}"
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
            skip_tool_capture = []  # Track skip tool calls (via hook)

            # Determine model based on provider
            from core import get_settings

            settings = get_settings()
            model = ""
            if provider_type == ProviderType.CODEX and settings.codex_model:
                model = settings.codex_model

            # Build provider-agnostic options
            base_options = AIClientOptions(
                system_prompt=final_system_prompt,
                model=model,
                session_id=context.session_id,
                agent_name=context.agent_name,
                agent_id=context.agent_id,
                config_file=context.config.config_file,
                group_name=context.group_name,
                has_situation_builder=context.has_situation_builder,
                long_term_memory_index=context.config.long_term_memory_index,
                mcp_tools={
                    "agent_name": context.agent_name,
                    "agent_group": context.group_name or "default",
                    "agent_id": context.agent_id,
                    "room_id": context.room_id,
                    "config_file": context.config.config_file,
                },
            )

            # Build provider-specific options with tool capture hooks
            options = provider.build_options(base_options, anthropic_calls, skip_tool_capture)

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

            # Get or create client from provider pool (reuses client for same room-agent pair)
            # This prevents creating hundreds of agent session files
            pool_key = task_id
            client, _ = await pool.get_or_create(pool_key, options)

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
                # Build query content based on message type
                if isinstance(message_to_send, list) and has_images:
                    # SDK requires async generator for multimodal content
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

            # Get the parser for this provider
            stream_parser = provider.get_parser()

            # Receive and stream the response
            async for message in client.receive_response():
                # Parse the message using provider's stream parser
                parsed = stream_parser.parse_message(message, response_text, thinking_text)

                # Calculate deltas for yielding
                content_delta = parsed.response_text[len(response_text) :]
                thinking_delta = parsed.thinking_text[len(thinking_text) :]

                # Update session if found
                if parsed.session_id:
                    new_session_id = parsed.session_id

                # Update skip flag via hook capture (MCP tools detected via PostToolUse hook)
                if skip_tool_capture and not skip_tool_called:
                    skip_tool_called = True
                    logger.info("⏭️  Skip tool called")

                # Collect memory entries
                memory_entries.extend(parsed.memory_entries)

                # Note: anthropic_calls are now captured via PostToolUse hook
                # (stream parser may not see tool_use blocks for MCP tools)

                # Update accumulated text
                response_text = parsed.response_text
                thinking_text = parsed.thinking_text

                # Update streaming state for polling access
                # When skip is used, clear response_text and mark as skipped
                # This prevents showing skipped content in UI and saving on interrupt
                if task_id in self.streaming_state:
                    if skip_tool_called:
                        self.streaming_state[task_id]["thinking_text"] = thinking_text
                        self.streaming_state[task_id]["response_text"] = ""
                        self.streaming_state[task_id]["skip_used"] = True
                    else:
                        self.streaming_state[task_id]["thinking_text"] = thinking_text
                        self.streaming_state[task_id]["response_text"] = response_text

                # Yield delta events for content and thinking
                # Don't yield content deltas after skip tool is called
                # (content after skip is the "reason for skipping" which should be hidden)
                if content_delta and not skip_tool_called:
                    yield {
                        "type": "content_delta",
                        "delta": content_delta,
                        "temp_id": temp_id,
                    }

                if thinking_delta:
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
            if task_id in pool.pool:
                # Use cleanup to properly disconnect in background task
                await pool.cleanup(task_id)

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
