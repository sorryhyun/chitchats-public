"""
Agent manager for handling multi-provider AI client lifecycle and response generation.

This module provides the AgentManager class which orchestrates agent responses,
manages client interruption, and handles conversation sessions.

Supports multiple AI providers:
- Claude: Uses Claude Agent SDK with MCP tools
- Codex: Uses Codex CLI subprocess with MCP config
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import AsyncIterator, List

from config import get_debug_config
from domain.contexts import AgentResponseContext
from domain.task_identifier import TaskIdentifier
from infrastructure.logging.agent_logger import append_response_to_debug_log, write_debug_log
from infrastructure.logging.formatters import format_message_for_debug
from providers import AIClient, AIClientOptions, AIProvider, ProviderType, get_provider
from providers.claude import ClaudeClientPool

# Configure from settings
DEBUG_MODE = get_debug_config().get("debug", {}).get("enabled", False)

# Suppress apscheduler debug/info logs
logging.getLogger("apscheduler").setLevel(logging.WARNING)

logger = logging.getLogger("AgentManager")


class AgentManager:
    """Manages AI clients for agent response generation and interruption.

    Supports multiple providers:
    - Claude: Uses Claude Agent SDK with MCP tools
    - Codex: Uses Codex CLI subprocess with MCP config
    """

    def __init__(self):
        # Note: Authentication can be configured in two ways:
        # 1. Set CLAUDE_API_KEY environment variable with your Anthropic API key
        # 2. Use Claude Code web authentication (when running through Claude Code with subscription)
        # If CLAUDE_API_KEY is not set, the SDK will use Claude Code authentication.
        # For Codex: Uses Codex CLI with existing authentication
        self.active_clients: dict[TaskIdentifier, AIClient] = {}
        # Client pool for managing SDK client lifecycle (Claude-specific)
        # TODO: Phase 3 will add per-provider pool management
        self.client_pool = ClaudeClientPool()
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

    # ========== Helper Methods for Response Generation (Phase 4 Refactoring) ==========

    def _setup_task_identifiers(self, context: AgentResponseContext) -> tuple[TaskIdentifier, str]:
        """
        Generate task identifier and temporary streaming ID.

        Args:
            context: Agent response context

        Returns:
            Tuple of (task_id, temp_id)
        """
        task_id = context.task_id or TaskIdentifier(room_id=context.room_id, agent_id=context.agent_id)
        temp_id = f"temp_{task_id}_{uuid.uuid4().hex[:8]}"
        return task_id, temp_id

    def _build_final_system_prompt(self, context: AgentResponseContext) -> str:
        """
        Build final system prompt with optional timestamp.

        Args:
            context: Agent response context

        Returns:
            System prompt with timestamp appended if conversation_started exists
        """
        if context.conversation_started:
            return f"{context.system_prompt}\n\n---\n\nCurrent time: {context.conversation_started}"
        return context.system_prompt

    def _cleanup_streaming_task(self, task_id: TaskIdentifier, log_message: str | None = None) -> None:
        """
        Unregister client and clear streaming state for task.

        Args:
            task_id: Task identifier to clean up
            log_message: Optional custom log message
        """
        if task_id in self.active_clients:
            del self.active_clients[task_id]
            if log_message:
                logger.debug(log_message)

        if task_id in self.streaming_state:
            del self.streaming_state[task_id]

    def _build_stream_end_event(
        self,
        temp_id: str,
        response_text: str,
        thinking_text: str,
        session_id: str | None,
        memory_entries: list[str],
        anthropic_calls: list[str],
        skip_used: bool,
    ) -> dict:
        """
        Build stream_end event from response state.

        Args:
            temp_id: Temporary streaming ID
            response_text: Final response text
            thinking_text: Final thinking text
            session_id: Session ID
            memory_entries: List of memory entries
            anthropic_calls: List of anthropic calls
            skip_used: Whether skip tool was used

        Returns:
            Stream end event dictionary
        """
        # Determine final response (None if skipped or empty)
        final_response = None
        if response_text and not skip_used:
            final_response = response_text

        return {
            "type": "stream_end",
            "temp_id": temp_id,
            "response_text": final_response,
            "thinking_text": thinking_text,
            "session_id": session_id,
            "memory_entries": memory_entries,
            "anthropic_calls": anthropic_calls,
            "skipped": skip_used,
        }

    def _build_cancellation_event(self, temp_id: str, context: AgentResponseContext) -> dict:
        """
        Build stream_end event for cancelled/interrupted tasks.

        Args:
            temp_id: Temporary streaming ID
            context: Original request context

        Returns:
            Stream end event indicating interruption
        """
        return {
            "type": "stream_end",
            "temp_id": temp_id,
            "response_text": None,
            "thinking_text": "",
            "session_id": context.session_id,
            "memory_entries": [],
            "anthropic_calls": [],
            "skipped": True,
        }

    def _build_error_event(self, temp_id: str, context: AgentResponseContext, error: Exception) -> dict:
        """
        Build stream_end event for errors.

        Args:
            temp_id: Temporary streaming ID
            context: Original request context
            error: Exception that occurred

        Returns:
            Stream end event with error message
        """
        return {
            "type": "stream_end",
            "temp_id": temp_id,
            "response_text": f"Error generating response: {str(error)}",
            "thinking_text": "",
            "session_id": context.session_id,
            "memory_entries": [],
            "anthropic_calls": [],
            "skipped": False,
        }

    # ========== End Helper Methods ==========

    async def generate_sdk_response(self, context: AgentResponseContext) -> AsyncIterator[dict]:
        """
        Generate a response from an agent using the appropriate AI provider.
        This is an async generator that yields streaming events as the response is generated.
        Agent can choose to skip responding by calling the 'skip' tool.
        Agent can record memories by calling the 'memorize' tool (if ENABLE_MEMORY_TOOL=true).

        Supports multiple providers:
        - Claude: Uses Claude Agent SDK with MCP tools
        - Codex: Uses Codex CLI subprocess with MCP config

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
        # Determine provider and route to appropriate implementation
        provider_type = context.provider or "claude"
        provider = get_provider(provider_type)

        if provider.provider_type == ProviderType.CODEX:
            # Use Codex CLI-based implementation
            async for event in self._generate_codex_response(context, provider):
                yield event
            return

        # Claude provider: continue with existing SDK implementation below

        # Setup task identifiers
        task_id, temp_id = self._setup_task_identifiers(context)

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
            final_system_prompt = self._build_final_system_prompt(context)

            response_text = ""
            thinking_text = ""
            new_session_id = context.session_id
            skip_tool_called = False
            memory_entries = []  # Track memory entries from memorize tool calls
            anthropic_calls = []  # Track anthropic tool calls (via hook)
            skip_tool_capture = []  # Track skip tool calls (via hook)

            # Build provider-agnostic options, then convert via provider
            provider = get_provider(provider_type)
            base_options = AIClientOptions(
                system_prompt=final_system_prompt,
                model="",  # Use provider default
                session_id=context.session_id,
                agent_name=context.agent_name,
                agent_id=context.agent_id,
                config_file=context.config.config_file if context.config else None,
                group_name=context.group_name,
                has_situation_builder=context.has_situation_builder,
            )
            options = provider.build_options(base_options, anthropic_calls, skip_tool_capture)
            parser = provider.get_parser()

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
                # Build query content
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

            # Receive and stream the response
            async for message in client.receive_response():
                # Parse the message using provider's parser
                parsed = parser.parse_message(message, response_text, thinking_text)

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

            # Cleanup streaming task
            self._cleanup_streaming_task(task_id, f"Unregistered client for task: {task_id}")

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
            yield self._build_stream_end_event(
                temp_id=temp_id,
                response_text=response_text,
                thinking_text=thinking_text,
                session_id=new_session_id,
                memory_entries=memory_entries,
                anthropic_calls=anthropic_calls,
                skip_used=skip_tool_called,
            )

        except asyncio.CancelledError:
            # Task was cancelled due to interruption - this is expected
            self._cleanup_streaming_task(task_id)
            logger.info(f"🛑 Agent response interrupted | Task: {task_id}")
            yield self._build_cancellation_event(temp_id, context)

        except Exception as e:
            # Clean up client on error
            self._cleanup_streaming_task(task_id)

            # Check if this is an interruption-related error
            error_str = str(e).lower()
            if "interrupt" in error_str or "cancelled" in error_str:
                logger.info(f"🛑 Agent response interrupted | Task: {task_id}")
                yield self._build_cancellation_event(temp_id, context)
                return

            # Remove client from pool on any error to ensure fresh client next time
            if task_id in self.client_pool.pool:
                await self.client_pool.cleanup(task_id)

            logger.error(f"❌ Error generating response: {str(e)}", exc_info=DEBUG_MODE)
            yield self._build_error_event(temp_id, context, e)

    async def _generate_codex_response(
        self,
        context: AgentResponseContext,
        provider: AIProvider,
    ) -> AsyncIterator[dict]:
        """Generate response using Codex CLI with MCP tools.

        This method handles the Codex-specific response generation flow:
        1. Build provider-agnostic options with MCP tool config
        2. Create Codex client via provider
        3. Stream response and parse events
        4. Handle skip/memorize tools via stream parsing

        Args:
            context: AgentResponseContext with all parameters
            provider: The Codex AIProvider instance

        Yields:
            Streaming events matching the same format as Claude:
            - stream_start, content_delta, thinking_delta, stream_end
        """
        # Setup task identifiers
        task_id, temp_id = self._setup_task_identifiers(context)

        logger.info(f"🤖 [Codex] Agent generating response | Session: {context.session_id or 'NEW'} | Task: {task_id}")

        yield {"type": "stream_start", "temp_id": temp_id}

        try:
            # Build final system prompt with timestamp
            final_system_prompt = self._build_final_system_prompt(context)

            # Build provider-agnostic options
            # MCP tools will be configured via TOML config generation
            base_options = AIClientOptions(
                system_prompt=final_system_prompt,
                model="",  # Use Codex default
                session_id=context.session_id,
                mcp_tools={
                    "agent_name": context.agent_name,
                    "agent_group": context.group_name or "default",
                    "agent_id": context.agent_id,
                    "config_file": context.config.config_file if context.config else None,
                },
                agent_name=context.agent_name,
                agent_id=context.agent_id,
                group_name=context.group_name,
                has_situation_builder=context.has_situation_builder,
            )

            # Build message content first (needed for session recovery)
            message_content = self._build_codex_message_content(context)

            # Build full conversation for session recovery (when thread is lost)
            # This includes more history than the regular message_content
            full_conversation = None
            if context.full_conversation_for_recovery:
                full_conversation = self._content_blocks_to_text(context.full_conversation_for_recovery)
                logger.debug(f"[Codex] Full conversation for recovery: {len(full_conversation)} chars, message_content: {len(message_content)} chars")
            else:
                logger.debug(f"[Codex] No full_conversation_for_recovery available")

            # Build Codex-specific options via provider
            # Include full_conversation for session recovery when thread is lost
            codex_options = provider.build_options(base_options)
            codex_options.full_conversation = full_conversation or message_content
            client = provider.create_client(codex_options)
            parser = provider.get_parser()

            # Connect and register for interruption
            await client.connect()
            self.active_clients[task_id] = client
            self.streaming_state[task_id] = {"thinking_text": "", "response_text": ""}

            logger.info(f"📤 [Codex] Sending message | Task: {task_id} | Length: {len(message_content)}")
            await client.query(message_content)

            response_text = ""
            thinking_text = ""
            new_session_id = context.session_id
            skip_used = False
            memory_entries: list[str] = []
            anthropic_calls: list[str] = []

            # Stream and parse response
            async for raw_event in client.receive_response():
                parsed = parser.parse_message(raw_event, response_text, thinking_text)

                # Calculate deltas
                content_delta = parsed.response_text[len(response_text) :]
                thinking_delta = parsed.thinking_text[len(thinking_text) :]

                # Update session if found
                if parsed.session_id:
                    new_session_id = parsed.session_id

                # Track tool usage
                if parsed.skip_used:
                    skip_used = True
                memory_entries.extend(parsed.memory_entries)
                anthropic_calls.extend(parsed.anthropic_calls)

                # Update accumulated text
                response_text = parsed.response_text
                thinking_text = parsed.thinking_text

                # Update streaming state
                if task_id in self.streaming_state:
                    if skip_used:
                        self.streaming_state[task_id]["thinking_text"] = thinking_text
                        self.streaming_state[task_id]["response_text"] = ""
                        self.streaming_state[task_id]["skip_used"] = True
                    else:
                        self.streaming_state[task_id]["thinking_text"] = thinking_text
                        self.streaming_state[task_id]["response_text"] = response_text

                # Yield deltas
                if content_delta and not skip_used:
                    yield {"type": "content_delta", "delta": content_delta, "temp_id": temp_id}
                if thinking_delta:
                    yield {"type": "thinking_delta", "delta": thinking_delta, "temp_id": temp_id}

            # Cleanup
            self._cleanup_streaming_task(task_id)
            await client.disconnect()

            # Log summary
            if skip_used:
                logger.info(f"⏭️  [Codex] Agent skipped | Session: {new_session_id}")
            else:
                logger.info(
                    f"✅ [Codex] Response generated | Length: {len(response_text)} chars | Session: {new_session_id}"
                )

            yield self._build_stream_end_event(
                temp_id=temp_id,
                response_text=response_text,
                thinking_text=thinking_text,
                session_id=new_session_id,
                memory_entries=memory_entries,
                anthropic_calls=anthropic_calls,
                skip_used=skip_used,
            )

        except asyncio.CancelledError:
            # Task was cancelled
            self._cleanup_streaming_task(task_id)
            logger.info(f"🛑 [Codex] Agent response interrupted | Task: {task_id}")
            yield self._build_cancellation_event(temp_id, context)

        except Exception as e:
            # Cleanup on error
            self._cleanup_streaming_task(task_id)
            logger.error(f"❌ [Codex] Error generating response: {str(e)}", exc_info=DEBUG_MODE)
            yield self._build_error_event(temp_id, context, e)

    def _build_codex_message_content(self, context: AgentResponseContext) -> str:
        """Build message content string for Codex CLI.

        Codex CLI expects a simple string message (no multimodal support via CLI).

        Args:
            context: AgentResponseContext with user_message

        Returns:
            String message content
        """
        if isinstance(context.user_message, list):
            # Extract text from content blocks
            text_parts = []
            for block in context.user_message:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
            message = "\n".join(text_parts)
        else:
            message = str(context.user_message)

        # Prepend conversation history if present
        if context.conversation_history:
            message = f"{context.conversation_history}\n\n{message}"

        return message

    def _content_blocks_to_text(self, content_blocks: List[dict]) -> str:
        """Convert content blocks to plain text string.

        Args:
            content_blocks: List of content blocks (text/image dicts)

        Returns:
            String with text content extracted from blocks
        """
        text_parts = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
        return "\n".join(text_parts)
