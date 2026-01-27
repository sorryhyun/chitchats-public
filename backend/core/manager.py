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
from typing import TYPE_CHECKING, AsyncIterator, Optional, Union

from mcp_servers.config import get_debug_config
from domain.contexts import AgentResponseContext
from domain.streaming import (
    ResponseAccumulator,
    StreamEndEvent,
    StreamEvent,
    StreamStartEvent,
)
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
from providers.codex.constants import SessionRecoveryError

if TYPE_CHECKING:
    from core.sse import EventBroadcaster

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
        # Event broadcaster for SSE streaming (optional, set via set_event_broadcaster)
        self.event_broadcaster: Optional[EventBroadcaster] = None

    def set_event_broadcaster(self, broadcaster: EventBroadcaster) -> None:
        """Set the event broadcaster for SSE streaming.

        Args:
            broadcaster: EventBroadcaster instance to use for broadcasting events
        """
        self.event_broadcaster = broadcaster
        logger.info("Event broadcaster configured for SSE streaming")

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

    async def _cleanup_response_state(
        self,
        task_id: TaskIdentifier,
        pool: ClientPoolInterface,
        remove_from_pool: bool = False,
    ) -> None:
        """Consolidate cleanup logic from exception handlers.

        Args:
            task_id: The task identifier for cleanup
            pool: The client pool to cleanup from
            remove_from_pool: If True, also remove client from pool
        """
        # Unregister from active clients
        if task_id in self.active_clients:
            del self.active_clients[task_id]
            logger.debug(f"Unregistered client for task: {task_id}")

        # Clean up streaming state
        if task_id in self.streaming_state:
            del self.streaming_state[task_id]

        # Optionally remove from pool (for errors requiring fresh client)
        if remove_from_pool and task_id in pool.pool:
            await pool.cleanup(task_id)

    def _build_final_system_prompt(self, context: AgentResponseContext) -> str:
        """Build the final system prompt with timestamp if conversation has started.

        Args:
            context: The agent response context

        Returns:
            Final system prompt string
        """
        if context.conversation_started:
            return f"{context.system_prompt}\n\n---\n\nCurrent time: {context.conversation_started}"
        return context.system_prompt

    def _build_message_content(
        self,
        context: AgentResponseContext,
    ) -> Union[str, list[dict]]:
        """Build the message content, handling both string and content block formats.

        Args:
            context: The agent response context

        Returns:
            Message content (string or list of content blocks)
        """
        if isinstance(context.user_message, list):
            # Content blocks with potential inline images
            content_blocks = context.user_message
            if context.conversation_history:
                # Prepend conversation history to first text block
                for block in content_blocks:
                    if block.get("type") == "text":
                        block["text"] = f"{context.conversation_history}\n\n{block['text']}"
                        break
            return content_blocks
        else:
            # Simple string message
            message = context.user_message
            if context.conversation_history:
                message = f"{context.conversation_history}\n\n{context.user_message}"
            return message

    async def _prepare_query_content(
        self,
        message_to_send: Union[str, list[dict]],
        has_images: bool,
        task_id: TaskIdentifier,
    ) -> Union[str, AsyncIterator]:
        """Prepare the query content based on message type.

        Args:
            message_to_send: The message to send (string or content blocks)
            has_images: Whether the message contains images
            task_id: Task identifier for logging

        Returns:
            Query content ready for client.query()
        """
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

            logger.info(f"📸 Sending multimodal message with inline images | Task: {task_id}")
            return multimodal_message_generator()
        elif isinstance(message_to_send, list):
            # Content blocks but no images - extract text
            return "\n".join(b.get("text", "") for b in message_to_send if b.get("type") == "text")
        else:
            return message_to_send

    def _is_interruption_error(self, error: Exception) -> bool:
        """Check if an exception is related to interruption.

        Args:
            error: The exception to check

        Returns:
            True if the error is interruption-related
        """
        error_str = str(error).lower()
        return "interrupt" in error_str or "cancelled" in error_str

    async def generate_sdk_response(self, context: AgentResponseContext) -> AsyncIterator[StreamEvent]:
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
            start_event = StreamStartEvent(temp_id=temp_id)
            yield start_event

            # Broadcast stream_start via SSE
            if self.event_broadcaster:
                sse_start = {
                    **start_event.to_dict(),
                    "agent_id": context.agent_id,
                    "agent_name": context.agent_name,
                    "agent_profile_pic": context.config.profile_pic,
                }
                await self.event_broadcaster.broadcast(context.room_id, sse_start)

            # Build final system prompt using helper
            final_system_prompt = self._build_final_system_prompt(context)

            # Initialize response accumulator (replaces 6 separate variables)
            accumulator = ResponseAccumulator(session_id=context.session_id)

            # Build provider-agnostic options from context (model is determined by provider_type)
            base_options = AIClientOptions.from_context(context, final_system_prompt, provider_type)

            # Build provider-specific options with tool capture hooks
            options = provider.build_options(base_options, accumulator.anthropic_calls, accumulator.skip_tool_capture)

            # Build the message content using helper
            message_to_send = self._build_message_content(context)

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
                # Build query content using helper
                query_content = await self._prepare_query_content(message_to_send, has_images, task_id)

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
                # Parse the message and update accumulator
                parsed = stream_parser.parse_message(message, accumulator.response_text, accumulator.thinking_text)

                # Log skip tool if just detected
                if accumulator.skip_tool_capture and not accumulator.skip_tool_called:
                    logger.info("⏭️  Skip tool called")

                # Update accumulator and get delta events
                events = accumulator.update_from_parsed(parsed, temp_id)

                # Update streaming state for polling access
                if task_id in self.streaming_state:
                    self.streaming_state[task_id] = accumulator.get_streaming_state()

                # Yield delta events and broadcast via SSE
                for event in events:
                    event_dict = event.to_dict()
                    yield event_dict

                    # Broadcast to SSE clients if broadcaster is configured
                    if self.event_broadcaster:
                        # Add agent_id to event for client-side routing
                        sse_event = {**event_dict, "agent_id": task_id.agent_id}
                        await self.event_broadcaster.broadcast(task_id.room_id, sse_event)

                # Debug log each message received from the SDK
                if DEBUG_MODE:
                    config = get_debug_config()
                    streaming_config = config.get("debug", {}).get("logging", {}).get("streaming", {})

                    if streaming_config.get("enabled", True):
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
            if accumulator.skip_tool_called:
                logger.info(f"⏭️  Agent skipped | Session: {accumulator.session_id}")
            else:
                logger.info(
                    f"✅ Response generated | Length: {len(accumulator.response_text)} chars | "
                    f"Thinking: {len(accumulator.thinking_text)} chars | Session: {accumulator.session_id}"
                )
            if accumulator.memory_entries:
                logger.info(f"💾 Recorded {len(accumulator.memory_entries)} memory entries")
            if accumulator.anthropic_calls:
                logger.info(
                    f"🔒 Agent called anthropic {len(accumulator.anthropic_calls)} times: {accumulator.anthropic_calls}"
                )

            # Create the end event
            end_event = accumulator.create_end_event(temp_id)

            # Append response to debug log
            append_response_to_debug_log(
                agent_name=context.agent_name,
                task_id=str(context.task_id) if context.task_id else "default",
                response_text=end_event.response_text or "",
                thinking_text=end_event.thinking_text,
                skipped=end_event.skipped,
            )

            # Yield stream_end event with final data
            # NOTE: SSE broadcast is now handled by ResponseGenerator AFTER save decision
            # to prevent race condition where frontend polls before message is saved
            yield end_event

        except asyncio.CancelledError:
            # Task was cancelled due to interruption - this is expected
            await self._cleanup_response_state(task_id, pool)
            logger.info(f"🛑 Agent response interrupted | Task: {context.task_id}")

            # Yield stream_end to indicate interruption
            end_event = StreamEndEvent(
                temp_id=temp_id,
                response_text=None,
                thinking_text="",
                session_id=context.session_id,
                memory_entries=[],
                anthropic_calls=[],
                skipped=True,
            )
            yield end_event

            # Broadcast stream_end via SSE (exception handlers still broadcast since response_generator won't reach its broadcast)
            if self.event_broadcaster:
                sse_end = {**end_event.to_dict(), "agent_id": context.agent_id}
                await self.event_broadcaster.broadcast(context.room_id, sse_end)

        except SessionRecoveryError:
            # Session recovery needed - propagate to ResponseGenerator for retry with full history
            await self._cleanup_response_state(task_id, pool, remove_from_pool=True)
            # Re-raise so ResponseGenerator can handle retry with full history
            raise

        except Exception as e:
            # Check if this is an interruption-related error
            if self._is_interruption_error(e):
                await self._cleanup_response_state(task_id, pool)
                logger.info(f"🛑 Agent response interrupted | Task: {context.task_id}")

                end_event = StreamEndEvent(
                    temp_id=temp_id,
                    response_text=None,
                    thinking_text="",
                    session_id=context.session_id,
                    memory_entries=[],
                    anthropic_calls=[],
                    skipped=True,
                )
                yield end_event

                # Broadcast stream_end via SSE (exception handlers still broadcast since response_generator won't reach its broadcast)
                if self.event_broadcaster:
                    sse_end = {**end_event.to_dict(), "agent_id": context.agent_id}
                    await self.event_broadcaster.broadcast(context.room_id, sse_end)
                return

            # Clean up and remove from pool on error to ensure fresh client next time
            await self._cleanup_response_state(task_id, pool, remove_from_pool=True)

            logger.error(f"❌ Error generating response: {str(e)}", exc_info=DEBUG_MODE)

            # Yield error as stream_end
            end_event = StreamEndEvent(
                temp_id=temp_id,
                response_text=f"Error generating response: {str(e)}",
                thinking_text="",
                session_id=context.session_id,
                memory_entries=[],
                anthropic_calls=[],
                skipped=False,
            )
            yield end_event

            # Broadcast stream_end via SSE (exception handlers still broadcast since response_generator won't reach its broadcast)
            if self.event_broadcaster:
                sse_end = {**end_event.to_dict(), "agent_id": context.agent_id}
                await self.event_broadcaster.broadcast(context.room_id, sse_end)
