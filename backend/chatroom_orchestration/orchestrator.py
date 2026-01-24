"""
Chat orchestrator for managing multi-agent conversations.

This module handles the logic for multi-round conversations between agents,
including context building, response generation, and message broadcasting.
"""

import asyncio
import logging
import time
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("ChatOrchestrator")

import crud
import schemas
from core.manager import AgentManager
from domain.contexts import OrchestrationContext
from infrastructure.database import models

from core.response_generator import ResponseGenerator

from .agent_ordering import separate_interrupt_agents
from .critic import process_critic_feedback
from .tape import TapeExecutor, TapeGenerator

# Multi-round conversation settings
MAX_FOLLOW_UP_ROUNDS = 5  # Number of follow-up rounds after initial responses
MAX_TOTAL_MESSAGES = 30  # Safety limit to prevent infinite loops


class ChatOrchestrator:
    """
    Orchestrates multi-agent conversations with follow-up rounds.
    Supports priority agent system where specific agents get first chance to respond.
    """

    def __init__(
        self,
        max_follow_up_rounds: int = MAX_FOLLOW_UP_ROUNDS,
        max_total_messages: int = MAX_TOTAL_MESSAGES,
        priority_agent_names: List[str] = None,
    ):
        self.max_follow_up_rounds = max_follow_up_rounds
        self.max_total_messages = max_total_messages
        self.priority_agent_names = priority_agent_names or []
        # Track active processing tasks per room for interruption
        self.active_room_tasks: dict[int, asyncio.Task] = {}
        # Used to skip broadcasting responses that were started before the interruption
        self.last_user_message_time: dict[int, float] = {}
        # Initialize response generator
        self.response_generator = ResponseGenerator(self.last_user_message_time)

    def get_chatting_agents(self, room_id: int, agent_manager: AgentManager) -> list[int]:
        """
        Get list of agent IDs currently chatting (generating responses) in a room.

        Args:
            room_id: Room ID
            agent_manager: AgentManager instance

        Returns:
            List of agent IDs currently processing in this room
        """
        chatting_agent_ids = []

        for task_id in agent_manager.active_clients.keys():
            if task_id.room_id == room_id:
                chatting_agent_ids.append(task_id.agent_id)

        return chatting_agent_ids

    async def interrupt_room_processing(
        self,
        room_id: int,
        agent_manager: AgentManager,
        db: AsyncSession = None,
        save_partial_responses: bool = True,
    ):
        """
        Interrupt all agents currently processing in a room.
        Optionally saves any partial responses that were in-progress.

        Args:
            room_id: Room ID to interrupt
            agent_manager: AgentManager instance
            db: Database session (required if save_partial_responses=True)
            save_partial_responses: If True, save any in-progress responses to DB
        """
        # Capture streaming state BEFORE interrupting (contains partial responses)
        partial_responses = agent_manager.get_and_clear_streaming_state_for_room(room_id)

        # Interrupt all agents in this room via the agent manager FIRST
        # This must happen before task.cancel() because cancellation cleans up active_clients
        await agent_manager.interrupt_room(room_id)

        # Cancel any active processing task for this room
        if room_id in self.active_room_tasks:
            task = self.active_room_tasks[room_id]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass  # Expected

        # Save any partial responses that have content
        if save_partial_responses and db and partial_responses:
            for agent_id, state in partial_responses.items():
                response_text = state.get("response_text", "").strip()
                thinking_text = state.get("thinking_text", "")
                skip_used = state.get("skip_used", False)

                # Only save if there's actual response content and agent wasn't skipping
                if response_text and not skip_used:
                    logger.info(
                        f"💾 Saving partial response | Room: {room_id} | Agent: {agent_id} | "
                        f"Length: {len(response_text)} chars"
                    )
                    message = schemas.MessageCreate(
                        content=response_text,
                        role="assistant",
                        agent_id=agent_id,
                        thinking=thinking_text if thinking_text else None,
                    )
                    await crud.create_message(db, room_id, message, update_room_activity=False)
                elif skip_used:
                    logger.info(
                        f"⏭️  Skipping partial response (agent used skip tool) | Room: {room_id} | Agent: {agent_id}"
                    )

    async def cleanup_room_state(self, room_id: int, agent_manager: AgentManager):
        """
        Clean up all state associated with a room.
        This should be called when a room is deleted to prevent memory leaks.

        Args:
            room_id: Room ID to clean up
            agent_manager: AgentManager instance for interrupting any active processing
        """
        logger.info(f"🧹 Cleaning up room state | Room: {room_id}")

        # First, interrupt any ongoing processing (don't save since room is being deleted)
        await self.interrupt_room_processing(room_id, agent_manager, save_partial_responses=False)

        # Remove from active tasks tracking (may already be removed by interrupt, but ensure it's gone)
        if room_id in self.active_room_tasks:
            del self.active_room_tasks[room_id]
            logger.info(f"✅ Removed room {room_id} from active_room_tasks")

        # Remove from last user message time tracking
        if room_id in self.last_user_message_time:
            del self.last_user_message_time[room_id]
            logger.info(f"✅ Removed room {room_id} from last_user_message_time")

        logger.info(f"✅ Room state cleanup complete | Room: {room_id}")

    async def handle_user_message(
        self,
        db: AsyncSession,
        room_id: int,
        message_data: dict,
        _manager,  # Deprecated, kept for backward compatibility (always None)
        agent_manager: AgentManager,
        saved_user_message_id: int = None,  # Optional: ID of already-saved message to avoid duplication
    ):
        """
        Handle a user message and orchestrate agent responses.
        Interrupts any ongoing agent processing in this room.

        Args:
            db: Database session
            room_id: Room ID
            message_data: Message data from client
            _manager: Deprecated parameter (kept for backward compatibility, always None)
            agent_manager: AgentManager for generating responses
            saved_user_message_id: Optional ID of pre-saved message (used by REST API to avoid duplication)
        """
        logger.info(f"🔵 USER MESSAGE RECEIVED | Room: {room_id} | Content: {message_data.get('content', '')[:50]}")

        # Record the timestamp of this user message for interruption tracking
        self.last_user_message_time[room_id] = time.time()

        # Save user message FIRST (only if not already saved)
        if saved_user_message_id is None:
            user_message = schemas.MessageCreate(
                content=message_data["content"],
                role="user",
                participant_type=message_data.get("participant_type"),
                participant_name=message_data.get("participant_name"),
            )
            # Create message and update room activity atomically
            saved_user_msg = await crud.create_message(db, room_id, user_message, update_room_activity=True)
        else:
            # Fetch the already-saved message in this session
            saved_user_msg = await db.get(models.Message, saved_user_message_id)

        # Note: User message broadcasting removed - not needed with HTTP polling architecture
        # Clients poll /api/rooms/{room_id}/messages to get new messages
        # The user message is already saved to database above, so polling will pick it up
        logger.info(
            f"💾 USER MESSAGE SAVED | Room: {room_id} | ID: {saved_user_msg.id} | Content: {saved_user_msg.content[:50]}"
        )

        # NOW interrupt any ongoing agent processing for this room
        # Save any partial responses that were in-progress
        await self.interrupt_room_processing(room_id, agent_manager, db=db)
        logger.info(f"🛑 INTERRUPTED | Room: {room_id}")

        # Get all agents for the room (use cache for performance)
        all_agents = await crud.get_agents_cached(db, room_id)

        # Extract mentioned agent for priority (@ mention feature)
        # First valid mentioned agent gets to respond first, others follow normal order
        mentioned_agent_id = None
        mentioned_agent_ids = message_data.get("mentioned_agent_ids")
        if mentioned_agent_ids:
            mentioned_set = set(mentioned_agent_ids)
            room_agent_ids = {agent.id for agent in all_agents}
            # Validate: only keep mentions that are actually in the room
            valid_mentions = mentioned_set & room_agent_ids
            if valid_mentions != mentioned_set:
                invalid = mentioned_set - room_agent_ids
                logger.warning(f"⚠️ Invalid @mentions (not in room): {invalid}")
            if valid_mentions:
                # Take first valid mention as priority agent
                for mid in mentioned_agent_ids:
                    if mid in valid_mentions:
                        mentioned_agent_id = mid
                        break
                logger.info(f"🎯 MENTION PRIORITY | Room: {room_id} | Priority agent ID: {mentioned_agent_id}")

        # Separate regular agents, critics, and interrupt agents
        agents = [agent for agent in all_agents if not agent.is_critic]
        critic_agents = [agent for agent in all_agents if agent.is_critic]

        # Separate interrupt agents from regular agents
        interrupt_agents, non_interrupt_agents = separate_interrupt_agents(agents)

        # Separate final_response agents (they get one more turn when limit is reached)
        final_response_agents = [a for a in non_interrupt_agents if getattr(a, "final_response", False)]

        # Create orchestration context
        orch_context = OrchestrationContext(db=db, room_id=room_id, agent_manager=agent_manager)

        # Create a processing task for this room
        logger.info(
            f"🚀 STARTING AGENT PROCESSING | Room: {room_id} | Agents: {len(non_interrupt_agents)} "
            f"| Interrupt Agents: {len(interrupt_agents)} | Final Response: {len(final_response_agents)} | Critics: {len(critic_agents)}"
        )
        processing_task = asyncio.create_task(
            self._process_agent_responses(
                orch_context=orch_context,
                agents=non_interrupt_agents,
                interrupt_agents=interrupt_agents,
                final_response_agents=final_response_agents,
                critic_agents=critic_agents,
                user_message_content=message_data["content"],
                mentioned_agent_id=mentioned_agent_id,
            )
        )

        # Track this task so we can cancel it if a new message arrives
        self.active_room_tasks[room_id] = processing_task

        try:
            await processing_task
            logger.info(f"✅ AGENT PROCESSING COMPLETE | Room: {room_id}")
        except asyncio.CancelledError:
            # Task was cancelled by a new message, this is expected
            logger.info(f"❌ AGENT PROCESSING CANCELLED | Room: {room_id}")
            pass
        except Exception as e:
            logger.error(f"💥 ERROR IN AGENT PROCESSING | Room: {room_id} | Error: {e}")
            import traceback

            traceback.print_exc()
        finally:
            # Clean up task tracking
            if room_id in self.active_room_tasks and self.active_room_tasks[room_id] == processing_task:
                del self.active_room_tasks[room_id]

    async def _process_agent_responses(
        self,
        orch_context: OrchestrationContext,
        agents: List,
        interrupt_agents: List,
        final_response_agents: List,
        critic_agents: List,
        user_message_content: str,
        mentioned_agent_id: int = None,
    ):
        """
        Internal method to process all agent responses using tape-based scheduling.

        This can be cancelled if a new user message arrives.
        Critics are processed separately and their feedback is stored but not broadcast.
        Interrupt agents respond after every single message.
        Final response agents get one more turn when the conversation limit is reached.
        """
        logger.info(f"📝 _process_agent_responses called | Room: {orch_context.room_id}")

        # Build agent lookup dict
        all_agents = agents + interrupt_agents
        agents_by_id = {a.id: a for a in all_agents}

        # Create tape generator and executor
        generator = TapeGenerator(agents, interrupt_agents, mentioned_agent_id=mentioned_agent_id)
        executor = TapeExecutor(
            response_generator=self.response_generator,
            agents_by_id=agents_by_id,
            max_total_messages=self.max_total_messages,
        )

        # Generate and execute initial round tape
        logger.info(f"🎬 Generating initial tape for {len(agents)} agent(s)...")
        initial_tape = generator.generate_initial_round()
        result = await executor.execute(
            tape=initial_tape,
            orch_context=orch_context,
            user_message_content=user_message_content,
        )
        logger.info(f"✅ Initial tape complete | Responses: {result.total_responses} | Skips: {result.total_skips}")

        # Track if we need to run final response agents
        should_run_final_response = False

        # Stop if paused or interrupted (but track limit reached for final response)
        if result.was_paused or result.was_interrupted:
            return
        if result.reached_limit:
            should_run_final_response = True

        # Follow-up rounds: Agents respond to each other (only in multi-agent rooms)
        # Skip if all interrupt agents are transparent
        if not should_run_final_response:
            all_interrupt_transparent = interrupt_agents and all(
                getattr(a, "transparent", 0) == 1 for a in interrupt_agents
            )

            if all_interrupt_transparent:
                logger.info("👻 All interrupt agents are transparent, skipping follow-up rounds")
            elif len(all_agents) > 1:
                total_messages = result.total_responses

                for round_num in range(self.max_follow_up_rounds):
                    logger.info(f"🔄 Follow-up round {round_num + 1}...")
                    follow_up_tape = generator.generate_follow_up_round(round_num)

                    result = await executor.execute(
                        tape=follow_up_tape,
                        orch_context=orch_context,
                        user_message_content=None,
                        current_total=total_messages,
                    )

                    total_messages += result.total_responses

                    # Stop conditions
                    if result.was_paused or result.was_interrupted:
                        break
                    if result.reached_limit:
                        should_run_final_response = True
                        break

                    if result.all_skipped:
                        logger.info(f"🏁 All agents skipped in room {orch_context.room_id}. Marking as finished.")
                        await crud.mark_room_as_finished(orch_context.db, orch_context.room_id)
                        break

        # Process final response agents (they get one more turn when limit is reached)
        if should_run_final_response and final_response_agents:
            logger.info(f"🏁 Running final response for {len(final_response_agents)} agent(s)...")
            for agent in final_response_agents:
                try:
                    responded = await self.response_generator.generate_response(
                        orch_context=orch_context,
                        agent=agent,
                        user_message_content=None,
                    )
                    if responded:
                        logger.info(f"✅ Final response from {agent.name}")
                    else:
                        logger.info(f"⏭️ Final response skipped by {agent.name}")
                except Exception as e:
                    logger.error(f"❌ Final response error from {agent.name}: {e}")

        # Process critic feedback (after conversation rounds complete)
        if critic_agents:
            await process_critic_feedback(
                orch_context=orch_context,
                critic_agents=critic_agents,
                user_message_content=user_message_content,
                response_generator=self.response_generator,
            )
