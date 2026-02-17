"""
Agent response generation for multi-agent conversations.

This module handles the logic for generating individual agent responses,
including context building, API calls, and message broadcasting.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import crud
from chatroom_orchestration.context import build_conversation_context, detect_conversation_type
from chatroom_orchestration.critic import save_critic_report
from chatroom_orchestration.handlers import save_agent_message
from providers.prompt_builder import build_system_prompt
from domain.contexts import AgentMessageData, AgentResponseContext, MessageContext, OrchestrationContext
from domain.streaming import ContentDeltaEvent, StreamEndEvent, StreamStartEvent, ThinkingDeltaEvent
from domain.task_identifier import TaskIdentifier
from i18n.timezone import format_kst_timestamp
from providers.codex.constants import SessionRecoveryError

logger = logging.getLogger("ResponseGenerator")


class ResponseGenerator:
    """
    Handles the generation of responses from individual agents.

    This class is responsible for:
    - Building conversation context for each agent
    - Generating agent responses via AgentManager
    - Handling interruption checks
    - Broadcasting responses to clients
    """

    def __init__(self, last_user_message_time: dict[int, float]):
        """
        Initialize the response generator.

        Args:
            last_user_message_time: Shared dict tracking last user message timestamp per room
        """
        self.last_user_message_time = last_user_message_time

    async def generate_response(
        self,
        orch_context: OrchestrationContext,
        agent,
        user_message_content: Optional[str] = None,
        is_critic: bool = False,
    ) -> bool:
        """
        Generate a response from a single agent.
        In initial responses, this runs concurrently with other agents.
        In follow-up rounds, this runs sequentially.

        Args:
            orch_context: OrchestrationContext containing db, room_id, manager, agent_manager
            agent: Agent object
            user_message_content: The user's message (for initial responses), or None for follow-ups
            is_critic: If True, stores feedback but doesn't broadcast to main chat

        Returns:
            True if agent responded, False if agent skipped
        """
        # Record when this response generation started
        # Used to check if it was interrupted by a new user message
        response_start_time = time.time()

        # Generate unique task ID for interruption tracking
        task_id = TaskIdentifier(room_id=orch_context.room_id, agent_id=agent.id)

        # Fetch room to get created_at timestamp and provider (use cache for performance)
        room = await crud.get_room_cached(orch_context.db, orch_context.room_id)

        # Get the provider for this room (defaults to claude)
        provider = room.default_provider if room else "claude"

        # Fetch only the messages since this agent's last response (cache for performance)
        room_messages = await crud.get_messages_after_agent_response_cached(
            orch_context.db,
            orch_context.room_id,
            agent.id,
            limit=120,
        )

        # Get agent config data
        agent_config = agent.get_config_data()

        # Get number of agents in the room
        agent_count = len(room.agents) if room else 0

        # Determine conversation type and participants using shared utility
        _, user_name, has_situation_builder = detect_conversation_type(room_messages, agent_count)

        # Build conversation context from room messages (only new messages since agent's last response)
        # Returns list of content blocks with images inline inside <conversation_so_far>
        conversation_content_blocks = build_conversation_context(
            room_messages,
            limit=25,
            agent_id=agent.id,
            agent_name=agent.name,
            agent_count=agent_count,
            user_name=user_name,
            provider=provider,
        )

        # For follow-up rounds, skip if there are no new messages since this agent's last response
        if user_message_content is None:
            if not self._has_new_messages(conversation_content_blocks):
                return False

        # Create message context for handlers
        msg_context = MessageContext(db=orch_context.db, room_id=orch_context.room_id, agent=agent)

        # Get this agent's session for this specific room and provider
        session_id = await crud.get_room_agent_session(orch_context.db, orch_context.room_id, agent.id, provider)

        # Use conversation content blocks which include messages and images inline
        message_to_agent = (
            conversation_content_blocks
            if conversation_content_blocks
            else [{"type": "text", "text": "Continue the conversation naturally."}]
        )

        # Format current timestamp with day of week
        conversation_started = format_kst_timestamp(datetime.now(timezone.utc), "%Y-%m-%d (%a) %H:%M KST")

        # Build agent response context
        # Build system prompt dynamically based on provider (for Codex-specific prompts)
        logger.debug(f"Building response context for agent: '{agent.name}' (id: {agent.id})")
        system_prompt = build_system_prompt(agent.name, agent_config, provider)
        response_context = AgentResponseContext(
            system_prompt=system_prompt,
            user_message=message_to_agent,  # Content blocks with inline images
            agent_name=agent.name,
            config=agent.get_config_data(),
            room_id=orch_context.room_id,
            agent_id=agent.id,
            group_name=agent.group,
            session_id=session_id,
            conversation_history=None,  # Not needed - already in message_to_agent
            task_id=task_id,
            conversation_started=conversation_started,
            has_situation_builder=has_situation_builder,
            provider=provider,
        )

        # Handle streaming response events with session recovery support
        response_text = ""
        thinking_text = ""
        new_session_id = session_id
        memory_entries = []
        anthropic_calls = []
        excuse_reasons = []
        skipped = False
        stream_started = False
        end_event = None  # Store the end event for later SSE broadcast

        try:
            # Iterate over streaming events from agent manager
            async for event in orch_context.agent_manager.generate_sdk_response(response_context):
                match event:
                    case StreamStartEvent():
                        stream_started = True

                    case ContentDeltaEvent(delta=delta):
                        response_text += delta

                    case ThinkingDeltaEvent(delta=delta):
                        thinking_text += delta

                    case StreamEndEvent() as end:
                        # Extract final data
                        end_event = end  # Store for SSE broadcast after save decision
                        response_text = end.response_text or response_text
                        thinking_text = end.thinking_text or thinking_text
                        new_session_id = end.session_id or session_id
                        memory_entries = end.memory_entries
                        anthropic_calls = end.anthropic_calls
                        excuse_reasons = end.excuse_reasons
                        skipped = end.skipped

        except SessionRecoveryError as e:
            # Session is invalid - rebuild context with FULL conversation history and retry
            logger.warning(
                f"Session recovery for {agent.name}: old thread_id={e.old_thread_id}. "
                "Rebuilding context with full conversation history..."
            )

            # Fetch ALL messages from room (no agent_id filter)
            full_room_messages = await crud.get_messages_cached(
                orch_context.db,
                orch_context.room_id,
            )

            # Rebuild conversation context with full history
            # Use high limit and no agent_id to include all messages
            full_conversation_blocks = build_conversation_context(
                full_room_messages,
                limit=len(full_room_messages),  # Include all messages
                agent_name=agent.name,
                agent_count=agent_count,
                user_name=user_name,
                provider=provider,
            )

            logger.info(
                f"Rebuilt context with {len(full_room_messages)} messages for {agent.name}. "
                "Retrying with fresh session..."
            )

            # Update context with full history and no session_id (fresh session)
            response_context.user_message = (
                full_conversation_blocks
                if full_conversation_blocks
                else [{"type": "text", "text": "Continue the conversation naturally."}]
            )
            response_context.session_id = None  # Fresh session

            # Retry with full history
            async for event in orch_context.agent_manager.generate_sdk_response(response_context):
                match event:
                    case StreamStartEvent():
                        stream_started = True

                    case ContentDeltaEvent(delta=delta):
                        response_text += delta

                    case ThinkingDeltaEvent(delta=delta):
                        thinking_text += delta

                    case StreamEndEvent() as end:
                        end_event = end  # Store for SSE broadcast after save decision
                        response_text = end.response_text or response_text
                        thinking_text = end.thinking_text or thinking_text
                        new_session_id = end.session_id or session_id
                        memory_entries = end.memory_entries
                        anthropic_calls = end.anthropic_calls
                        excuse_reasons = end.excuse_reasons
                        skipped = end.skipped

        # Memory entries are now written directly by the memorize tool
        # So we can skip this section (kept for reference/debugging)
        if memory_entries:
            logger.debug(
                f"Agent {agent.name} recorded {len(memory_entries)} memories (handled by memorize tool directly)"
            )

        # Log anthropic tool calls if any
        if anthropic_calls:
            logger.info(f"Agent {agent.name} called anthropic tool: {anthropic_calls}")

        # Update this room-agent session_id if it changed
        if new_session_id and new_session_id != session_id:
            await crud.update_room_agent_session(
                orch_context.db, orch_context.room_id, agent.id, new_session_id, provider
            )

        # Helper to broadcast stream_end via SSE
        async def broadcast_stream_end(is_skipped: bool):
            if not end_event:
                logger.warning(f"Cannot broadcast stream_end: end_event is None | Agent: {agent.name}")
                return
            if not orch_context.agent_manager.event_broadcaster:
                logger.warning(f"Cannot broadcast stream_end: event_broadcaster is None | Agent: {agent.name}")
                return

            # Create appropriate end event based on whether message was saved or discarded
            if is_skipped:
                # Message was discarded - broadcast with skipped=True and no content
                sse_end = {
                    "type": "stream_end",
                    "temp_id": end_event.temp_id,
                    "response_text": None,
                    "thinking_text": "",
                    "session_id": end_event.session_id,
                    "memory_entries": [],
                    "anthropic_calls": [],
                    "skipped": True,
                    "agent_id": agent.id,
                }
            else:
                # Message was saved - broadcast the full end event
                sse_end = {**end_event.to_dict(), "agent_id": agent.id}

            logger.debug(f"Broadcasting stream_end | Agent: {agent.name} | Skipped: {is_skipped}")
            await orch_context.agent_manager.event_broadcaster.broadcast(
                orch_context.room_id, sse_end
            )

        # Skip if agent chose not to respond - don't persist anything
        if skipped or not response_text:
            logger.info(f"⏭️ Agent {agent.name} skipped | skipped={skipped} | response_text_len={len(response_text) if response_text else 0}")
            await broadcast_stream_end(is_skipped=True)
            return False

        # Check if this response was interrupted by a new user message
        # If a user message arrived after this response started, skip broadcasting it
        if self._was_interrupted(orch_context.room_id, response_start_time, agent.name):
            logger.info(f"⏭️ Agent {agent.name} interrupted by new user message")
            await broadcast_stream_end(is_skipped=True)
            return False

        # Check if room was paused while this agent was generating
        # This prevents messages from being saved after pause button is pressed
        if room and room.is_paused:
            logger.info(f"⏭️ Agent {agent.name} discarded because room {orch_context.room_id} was paused")
            await broadcast_stream_end(is_skipped=True)
            return False

        # For critic agents, automatically save their output to report.md
        if is_critic:
            save_critic_report(agent.name, response_text, thinking_text)

        # Save message to database
        message_data = AgentMessageData(
            content=response_text,
            thinking=thinking_text,
            anthropic_calls=anthropic_calls if anthropic_calls else None,
            excuse_reasons=excuse_reasons if excuse_reasons else None,
        )
        await save_agent_message(msg_context, message_data)

        # Broadcast stream_end AFTER message is saved - this prevents race condition
        # where frontend polls for message before it exists in database
        await broadcast_stream_end(is_skipped=False)

        return True

    def _has_new_messages(self, content_blocks: list) -> bool:
        """
        Check if content_blocks contains new messages for the agent to respond to.

        Args:
            content_blocks: List of content blocks (text and image dicts)

        Returns:
            True if there are new messages, False otherwise
        """
        # Check if content_blocks is empty
        if not content_blocks:
            return False

        # Check if there are any image blocks (indicates new content)
        has_image = any(block.get("type") == "image" for block in content_blocks)
        if has_image:
            return True

        # Check text content - extract all text and filter header/footer
        all_text = ""
        for block in content_blocks:
            if block.get("type") == "text":
                all_text += block.get("text", "")

        context_lines = all_text.strip().split("\n")

        # Filter out header/footer lines
        actual_messages = [
            line
            for line in context_lines
            if line
            and not line.startswith("Here's the recent conversation")
            and not line.startswith("Respond naturally")
        ]

        return bool(actual_messages)

    def _was_interrupted(self, room_id: int, response_start_time: float, agent_name: str) -> bool:
        """
        Check if this response was interrupted by a new user message.

        Args:
            room_id: Room ID
            response_start_time: When this response generation started
            agent_name: Name of the agent (for logging)

        Returns:
            True if interrupted, False otherwise
        """
        if room_id in self.last_user_message_time:
            last_user_msg_time = self.last_user_message_time[room_id]
            if last_user_msg_time > response_start_time:
                logger.info(
                    f"SKIPPING BROADCAST | Room: {room_id} | Agent: {agent_name} | "
                    f"Response started at {response_start_time:.3f}, but interrupted by user message at {last_user_msg_time:.3f}"
                )
                return True
        return False
