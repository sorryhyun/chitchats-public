"""
Chat orchestrator for managing multi-agent conversations.

This module handles the logic for multi-round conversations between agents,
including context building, response generation, and message broadcasting.
"""

import asyncio
import logging
import random
import time
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

logger = logging.getLogger("ChatOrchestrator")

import crud
import models
import schemas
from domain.contexts import OrchestrationContext
from sdk import AgentManager

from .memory_brain import MemoryBrain
from .response_generator import ResponseGenerator

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
        # Initialize memory brain (shared across all agents)
        self.memory_brain = MemoryBrain()
        # Initialize response generator
        self.response_generator = ResponseGenerator(self.last_user_message_time, self.memory_brain)

    async def shutdown(self, timeout: float = 5.0):
        """
        Gracefully shutdown the orchestrator, cancelling all active room tasks.

        Args:
            timeout: Maximum time to wait for tasks to complete before cancelling
        """
        if not self.active_room_tasks:
            return

        logger.info(f"🛑 Shutting down orchestrator with {len(self.active_room_tasks)} active room tasks")

        # Cancel all active tasks
        for room_id, task in list(self.active_room_tasks.items()):
            if not task.done():
                task.cancel()

        # Wait for all tasks to complete (or be cancelled)
        if self.active_room_tasks:
            tasks = list(self.active_room_tasks.values())
            done, pending = await asyncio.wait(tasks, timeout=timeout)

            if pending:
                logger.warning(f"⚠️ {len(pending)} room tasks did not complete within {timeout}s")

        # Clear tracking dicts
        self.active_room_tasks.clear()
        self.last_user_message_time.clear()
        logger.info("✅ Orchestrator shutdown complete")

    def _separate_priority_agents(self, agents: List) -> tuple[List, List]:
        """
        Separate agents into priority and regular groups based on priority_agent_names.

        Args:
            agents: List of agent objects

        Returns:
            Tuple of (priority_agents, regular_agents)
        """
        if not self.priority_agent_names:
            return [], agents

        priority_agents = []
        regular_agents = []

        for agent in agents:
            if agent.name in self.priority_agent_names:
                priority_agents.append(agent)
            else:
                regular_agents.append(agent)

        # Sort priority agents by their order in priority_agent_names
        priority_agents.sort(key=lambda a: self.priority_agent_names.index(a.name))

        return priority_agents, regular_agents

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

    async def interrupt_room_processing(self, room_id: int, agent_manager: AgentManager):
        """
        Interrupt all agents currently processing in a room.
        This is called when a new user message arrives while agents are still responding.
        """
        # Cancel any active processing task for this room
        if room_id in self.active_room_tasks:
            task = self.active_room_tasks[room_id]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass  # Expected

        # Interrupt all agents in this room via the agent manager
        await agent_manager.interrupt_room(room_id)

    async def cleanup_room_state(self, room_id: int, agent_manager: AgentManager):
        """
        Clean up all state associated with a room.
        This should be called when a room is deleted to prevent memory leaks.

        Args:
            room_id: Room ID to clean up
            agent_manager: AgentManager instance for interrupting any active processing
        """
        logger.info(f"🧹 Cleaning up room state | Room: {room_id}")

        # First, interrupt any ongoing processing
        await self.interrupt_room_processing(room_id, agent_manager)

        # Remove from active tasks tracking (may already be removed by interrupt, but ensure it's gone)
        if room_id in self.active_room_tasks:
            del self.active_room_tasks[room_id]
            logger.info(f"✅ Removed room {room_id} from active_room_tasks")

        # Remove from last user message time tracking
        if room_id in self.last_user_message_time:
            del self.last_user_message_time[room_id]
            logger.info(f"✅ Removed room {room_id} from last_user_message_time")

        # Clean up memory state for this room
        self.memory_brain.cleanup(room_id)
        logger.info(f"✅ Cleared memory state for room {room_id}")

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

        # Increment turn counter for memory state tracking
        self.memory_brain.increment_turn(room_id)

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
        await self.interrupt_room_processing(room_id, agent_manager)
        logger.info(f"🛑 INTERRUPTED | Room: {room_id}")

        # Get all agents for the room (use cache for performance)
        all_agents = await crud.get_agents_cached(db, room_id)

        # Separate regular agents from critics
        agents = [agent for agent in all_agents if not agent.is_critic]
        critic_agents = [agent for agent in all_agents if agent.is_critic]

        # Create orchestration context
        orch_context = OrchestrationContext(db=db, room_id=room_id, agent_manager=agent_manager)

        # Create a processing task for this room
        logger.info(
            f"🚀 STARTING AGENT PROCESSING | Room: {room_id} | Agents: {len(agents)} | Critics: {len(critic_agents)}"
        )
        processing_task = asyncio.create_task(
            self._process_agent_responses(
                orch_context=orch_context,
                agents=agents,
                critic_agents=critic_agents,
                user_message_content=message_data["content"],
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
        self, orch_context: OrchestrationContext, agents: List, critic_agents: List, user_message_content: str
    ):
        """
        Internal method to process all agent responses.
        This can be cancelled if a new user message arrives.
        Critics are processed separately and their feedback is stored but not broadcast.
        """
        logger.info(f"📝 _process_agent_responses called | Room: {orch_context.room_id}")

        # Check if room is paused
        room = await crud.get_room_cached(orch_context.db, orch_context.room_id)
        if room and room.is_paused:
            logger.info(f"⏸️  Room {orch_context.room_id} is paused. Skipping agent responses.")
            return

        logger.info(f"▶️  Room {orch_context.room_id} is NOT paused. Proceeding with agents...")
        total_messages = 0

        # Round 1: All agents respond to user message
        logger.info(f"🔄 Starting initial agent responses for {len(agents)} agent(s)...")
        total_messages = await self._initial_agent_responses(
            orch_context=orch_context,
            agents=agents,
            user_message_content=user_message_content,
            total_messages=total_messages,
        )
        logger.info(f"✅ Initial agent responses complete. Total messages: {total_messages}")

        # Refetch room state to check for updates (pause/interaction limit changes)
        room = await crud.get_room_cached(orch_context.db, orch_context.room_id)
        if room and room.is_paused:
            logger.info(f"⏸️  Room {orch_context.room_id} was paused. Stopping agent responses.")
            return

        # Check if we've hit the interaction limit after initial responses
        if room and room.max_interactions is not None:
            current_agent_messages = await self._count_agent_messages(orch_context.db, orch_context.room_id)
            if current_agent_messages >= room.max_interactions:
                logger.info(f"🛑 Room {orch_context.room_id} reached max interactions limit ({room.max_interactions})")
                return

        # Follow-up rounds: Agents respond to each other (only in multi-agent rooms)
        if len(agents) > 1:
            await self._follow_up_rounds(orch_context=orch_context, agents=agents, total_messages=total_messages)

        # Process critic feedback (after conversation rounds complete)
        if critic_agents:
            await self._process_critic_feedback(
                orch_context=orch_context, critic_agents=critic_agents, user_message_content=user_message_content
            )

    async def _process_critic_feedback(
        self, orch_context: OrchestrationContext, critic_agents: List, user_message_content: str
    ):
        """
        Generate feedback from critic agents after conversation rounds.
        Critics observe the conversation but don't participate directly.
        Their feedback is stored but not broadcast to the main chat.
        """
        logger.info(f"🔍 Processing critic feedback | Room: {orch_context.room_id} | Critics: {len(critic_agents)}")

        # Create tasks for all critics to run concurrently
        tasks = [
            self.response_generator.generate_response(
                orch_context=orch_context,
                agent=critic,
                user_message_content=user_message_content,
                is_critic=True,  # Flag to indicate this is a critic
            )
            for critic in critic_agents
        ]

        # Wait for all critics to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Log any errors
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"❌ Critic {critic_agents[i].name} error: {result}")
            else:
                logger.info(f"✅ Critic {critic_agents[i].name} feedback stored")

    async def _initial_agent_responses(
        self, orch_context: OrchestrationContext, agents: List, user_message_content: str, total_messages: int
    ) -> int:
        """
        Generate initial responses from all agents to the user message.
        Priority agents are processed SEQUENTIALLY (one at a time), giving them first chance.
        Regular agents are processed CONCURRENTLY after priority agents.
        Agents can choose to skip by calling the 'skip' tool.

        Returns:
            Updated total_messages count
        """
        # Separate priority and regular agents
        priority_agents, regular_agents = self._separate_priority_agents(agents)

        # Log priority system status
        if priority_agents:
            logger.info(
                f"🎯 Priority agents ({len(priority_agents)}): {[a.name for a in priority_agents]} | "
                f"Regular agents ({len(regular_agents)}): {[a.name for a in regular_agents]}"
            )
        else:
            logger.info(f"👥 All agents ({len(agents)}) will respond concurrently (no priority set)")

        all_results = []

        # Process priority agents SEQUENTIALLY (one at a time)
        if priority_agents:
            logger.info(f"⭐ Processing {len(priority_agents)} priority agent(s) sequentially...")
            for i, agent in enumerate(priority_agents):
                logger.info(f"🎯 Priority agent {i + 1}/{len(priority_agents)}: {agent.name}")
                try:
                    result = await self.response_generator.generate_response(
                        orch_context=orch_context, agent=agent, user_message_content=user_message_content
                    )
                    all_results.append(result)
                    logger.info(f"✓ Priority agent {agent.name} completed: {result}")
                except Exception as e:
                    logger.error(f"❌ Priority agent {agent.name} error: {e}")
                    all_results.append(e)

        # Check if room was paused during priority agent processing
        room = await crud.get_room_cached(orch_context.db, orch_context.room_id)
        if room and room.is_paused:
            logger.info(f"⏸️  Room {orch_context.room_id} was paused during priority agents. Stopping.")
            responses_count = sum(1 for result in all_results if result is True)
            return total_messages + responses_count

        # Process regular agents CONCURRENTLY (all at once)
        if regular_agents:
            logger.info(f"👥 Processing {len(regular_agents)} regular agent(s) concurrently...")
            tasks = [
                self.response_generator.generate_response(
                    orch_context=orch_context, agent=agent, user_message_content=user_message_content
                )
                for agent in regular_agents
            ]

            # Wait for all regular agents to complete
            logger.info(f"⏳ Waiting for {len(tasks)} regular agent task(s) to complete...")
            results = await asyncio.gather(*tasks, return_exceptions=True)
            all_results.extend(results)

            # Log regular agent results
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"❌ Regular agent {i} error: {result}")
                else:
                    logger.info(f"✓ Regular agent {i} result: {result}")

        # Check if room was paused during agent processing
        room = await crud.get_room_cached(orch_context.db, orch_context.room_id)
        if room and room.is_paused:
            logger.info(f"⏸️  Room {orch_context.room_id} was paused during agent responses. Stopping.")
            return total_messages  # Return without counting any responses

        # Count how many agents responded (didn't skip)
        responses_count = sum(1 for result in all_results if result is True)
        total_messages += responses_count
        logger.info(f"📈 Responses count: {responses_count} | Total messages: {total_messages}")

        return total_messages

    async def _follow_up_rounds(self, orch_context: OrchestrationContext, agents: List, total_messages: int):
        """
        Orchestrate follow-up rounds where agents respond to each other SEQUENTIALLY.
        Priority agents are processed first (in priority order), then regular agents (shuffled).
        Each agent sees all previous responses before deciding whether to respond.

        Agents can choose to skip by calling the 'skip' tool.

        Performance optimization: Room state and message counts are cached per round
        instead of being refetched before each agent response, reducing database
        queries by ~80%.
        """
        for round_num in range(self.max_follow_up_rounds):
            if total_messages >= self.max_total_messages:
                break

            # Fetch room state ONCE at the start of each round (not before each agent)
            room = await crud.get_room_cached(orch_context.db, orch_context.room_id)
            if room and room.is_paused:
                logger.info(f"⏸️  Room {orch_context.room_id} was paused. Stopping follow-up rounds.")
                break

            # Check interaction limit ONCE at the start of each round
            # Then maintain a local counter to avoid repeated COUNT queries
            if room and room.max_interactions is not None:
                current_agent_messages = await self._count_agent_messages(orch_context.db, orch_context.room_id)
                if current_agent_messages >= room.max_interactions:
                    logger.info(
                        f"🛑 Room {orch_context.room_id} reached max interactions limit ({room.max_interactions})"
                    )
                    break
                # Track remaining interactions for this round
                remaining_interactions = room.max_interactions - current_agent_messages
            else:
                remaining_interactions = None  # No limit

            # Separate priority and regular agents, then order them
            priority_agents, regular_agents = self._separate_priority_agents(agents)

            # Shuffle only the regular agents for natural conversation flow
            shuffled_regular = list(regular_agents)
            random.shuffle(shuffled_regular)

            # Combine: priority agents first (in priority order), then shuffled regular agents
            ordered_agents = priority_agents + shuffled_regular

            if priority_agents:
                logger.info(
                    f"🔄 Follow-up round {round_num + 1}: Priority agents: {[a.name for a in priority_agents]}, "
                    f"then shuffled: {[a.name for a in shuffled_regular]}"
                )

            responses_count = 0

            # Process agents sequentially (one at a time)
            for agent in ordered_agents:
                if total_messages >= self.max_total_messages:
                    break

                # Check local counter instead of refetching room state for each agent
                # This reduces database queries from N per agent to 1 per round
                if remaining_interactions is not None and remaining_interactions <= 0:
                    logger.info(f"🛑 Room {orch_context.room_id} reached max interactions limit (local count)")
                    break

                try:
                    responded = await self.response_generator.generate_response(
                        orch_context=orch_context,
                        agent=agent,
                        user_message_content=None,  # None means follow-up round
                    )

                    if responded:
                        responses_count += 1
                        total_messages += 1
                        # Decrement remaining interactions counter
                        if remaining_interactions is not None:
                            remaining_interactions -= 1

                except Exception as e:
                    # Log error but continue with other agents
                    logger.error(f"Error in agent {agent.name} response: {e}")
                    continue

            # If no agents responded this round, end the conversation
            if responses_count == 0:
                break

    async def _count_agent_messages(self, db: AsyncSession, room_id: int) -> int:
        """Count the number of agent messages (role='assistant') in a room."""
        from sqlalchemy import func

        result = await db.execute(
            select(func.count(models.Message.id)).where(
                models.Message.room_id == room_id, models.Message.role == "assistant"
            )
        )
        return result.scalar() or 0
