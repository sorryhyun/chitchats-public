"""
Background scheduler for autonomous agent chat rounds.

This module runs periodic tasks to process agent conversations in active rooms,
enabling background chatroom interactions when users are not actively viewing.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import crud
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from core.manager import AgentManager
from chatroom_orchestration import ChatOrchestrator
from chatroom_orchestration.agent_ordering import separate_interrupt_agents
from chatroom_orchestration.tape import TapeExecutor, TapeGenerator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from infrastructure.database import models

logger = logging.getLogger("BackgroundScheduler")

# Suppress noisy APScheduler "max instances reached" warnings
# These are expected during heavy load and not actionable
logging.getLogger("apscheduler.scheduler").setLevel(logging.ERROR)


class BackgroundScheduler:
    """Manages background tasks for autonomous agent conversations."""

    def __init__(
        self,
        chat_orchestrator: ChatOrchestrator,
        agent_manager: AgentManager,
        get_db_session,
        max_concurrent_rooms: int = 5,
    ):
        self.scheduler = AsyncIOScheduler()
        self.chat_orchestrator = chat_orchestrator
        self.agent_manager = agent_manager
        self.get_db_session = get_db_session
        self.max_concurrent_rooms = max_concurrent_rooms
        self.is_running = False

    def start(self):
        """Start the background scheduler."""
        if not self.is_running:
            # Run autonomous chat rounds every 500ms
            self.scheduler.add_job(
                self._process_active_rooms,
                "interval",
                seconds=0.5,
                id="process_active_rooms",
                replace_existing=True,
                max_instances=1,  # Only one instance at a time (prevents overwhelming system)
                coalesce=True,  # Skip missed runs if previous job still running
                misfire_grace_time=None,  # Never misfire - just skip if busy (suppresses warnings)
            )

            # Clean up expired cache entries every 5 minutes
            self.scheduler.add_job(
                self._cleanup_cache, "interval", minutes=5, id="cleanup_cache", replace_existing=True
            )

            self.scheduler.start()
            self.is_running = True
            logger.info("🚀 Background scheduler started - processing rooms every 500ms, cache cleanup every 5 minutes")

    def stop(self):
        """Stop the background scheduler."""
        if self.is_running:
            self.scheduler.shutdown()
            self.is_running = False
            logger.info("🛑 Background scheduler stopped")

    async def _process_active_rooms(self):
        """
        Process autonomous chat rounds for all active rooms.

        A room is considered active if:
        - It has messages in the last 5 minutes
        - It's not paused
        - It has at least 2 agents
        """
        try:
            async with self._session_scope() as db:
                active_rooms = await self._get_active_rooms(db)

            if not active_rooms:
                # Don't log when there's no activity (too noisy)
                return

            logger.info(f"🔄 Processing {len(active_rooms)} active room(s)")

            semaphore = asyncio.Semaphore(self.max_concurrent_rooms) if self.max_concurrent_rooms else None

            async def process_with_error_handling(room):
                try:
                    if semaphore:
                        async with semaphore:
                            await self._process_room_for_background_job(room)
                    else:
                        await self._process_room_for_background_job(room)
                except Exception as e:
                    logger.error(f"❌ Error processing room {room.id}: {e}")
                    import traceback

                    traceback.print_exc()

            # Process all active rooms concurrently with a small cap
            await asyncio.gather(*[process_with_error_handling(room) for room in active_rooms])

        except Exception as e:
            logger.error(f"💥 Error in _process_active_rooms: {e}")
            import traceback

            traceback.print_exc()

    @asynccontextmanager
    async def _session_scope(self):
        session_gen = self.get_db_session()
        session = await anext(session_gen)
        try:
            yield session
        finally:
            try:
                await session_gen.aclose()
            except Exception as e:
                logger.error(f"Error closing database session: {e}")

    async def _process_room_for_background_job(self, room: models.Room):
        async with self._session_scope() as room_db:
            await self._process_room_autonomous_round(room_db, room)

    async def _get_active_rooms(self, db: AsyncSession) -> list:
        """
        Get rooms that should have autonomous agent interactions.

        Criteria:
        - Has messages in the last 5 minutes
        - Not paused
        - Not finished (all agents haven't skipped)
        - Has at least 2 agents
        """
        # Calculate cutoff time (5 minutes ago)
        cutoff_time = datetime.utcnow() - timedelta(minutes=5)

        # Use the room's last_activity_at field to avoid repeated full message scans
        stmt = (
            select(models.Room)
            .options(selectinload(models.Room.agents))  # Eager load agents
            .where(
                models.Room.is_paused == False,
                models.Room.is_finished == False,
                models.Room.last_activity_at >= cutoff_time,
            )
            .order_by(models.Room.last_activity_at.desc())
        )

        # Optionally cap the number of rooms fetched to reduce load during spikes
        if self.max_concurrent_rooms:
            stmt = stmt.limit(self.max_concurrent_rooms)

        result = await db.execute(stmt)
        rooms = result.scalars().all()

        # Filter rooms with at least 2 agents (agents already loaded via selectinload)
        active_rooms = []
        for room in rooms:
            # Only include rooms with multiple agents (exclude critics)
            regular_agents = [a for a in room.agents if not a.is_critic]
            if len(regular_agents) >= 2:
                active_rooms.append(room)

        return active_rooms

    def _cleanup_completed_tasks(self):
        """Remove completed tasks from active_room_tasks to prevent memory leak."""
        completed_rooms = [room_id for room_id, task in self.chat_orchestrator.active_room_tasks.items() if task.done()]
        for room_id in completed_rooms:
            del self.chat_orchestrator.active_room_tasks[room_id]
            logger.debug(f"Cleaned up completed task for room {room_id}")

    async def _process_room_autonomous_round(self, db: AsyncSession, room: models.Room):
        """
        Process one autonomous round for a room using tape-based scheduling.

        This simulates agent interactions without a user message trigger.
        Agents will decide whether to respond based on the conversation context.
        """
        logger.info(f"🤖 Processing autonomous round | Room: {room.id} ({room.name})")

        # Clean up completed tasks before checking
        self._cleanup_completed_tasks()

        # Check if room is already being processed
        if room.id in self.chat_orchestrator.active_room_tasks:
            task = self.chat_orchestrator.active_room_tasks[room.id]
            if not task.done():
                logger.debug(f"Room {room.id} is already processing, skipping")
                return
            else:
                # Remove completed task
                del self.chat_orchestrator.active_room_tasks[room.id]

        # Get all agents (use cache for performance)
        all_agents = await crud.get_agents_cached(db, room.id)
        agents = [agent for agent in all_agents if not agent.is_critic]

        if len(agents) < 2:
            logger.debug(f"Room {room.id} has less than 2 agents, skipping")
            return

        # Check if room has hit max interactions
        if room.max_interactions is not None:
            current_count = await self._count_agent_messages(db, room.id)
            if current_count >= room.max_interactions:
                logger.debug(f"Room {room.id} reached max interactions ({room.max_interactions})")
                return

        # Run one follow-up round using tape-based scheduling
        from domain.contexts import OrchestrationContext

        orch_context = OrchestrationContext(db=db, room_id=room.id, agent_manager=self.agent_manager)

        # Separate interrupt agents from regular agents
        interrupt_agents, non_interrupt_agents = separate_interrupt_agents(agents)

        # Build agent lookup dict
        all_non_critic_agents = non_interrupt_agents + interrupt_agents
        agents_by_id = {a.id: a for a in all_non_critic_agents}

        # Create tape generator and executor
        generator = TapeGenerator(non_interrupt_agents, interrupt_agents)
        executor = TapeExecutor(
            response_generator=self.chat_orchestrator.response_generator,
            agents_by_id=agents_by_id,
            max_total_messages=self.chat_orchestrator.max_total_messages,
        )

        # Generate and execute one follow-up round tape
        tape = generator.generate_follow_up_round(round_num=0)
        result = await executor.execute(tape=tape, orch_context=orch_context, user_message_content=None)

        if result.all_skipped:
            logger.info(f"🏁 All agents skipped in room {room.id}. Marking as finished.")
            await crud.mark_room_as_finished(db, room.id)
        else:
            logger.info(f"✅ Autonomous round complete | Room: {room.id} | Responses: {result.total_responses}")

    async def _count_agent_messages(self, db: AsyncSession, room_id: int) -> int:
        """Count the number of agent messages (role='assistant') in a room."""
        result = await db.execute(
            select(func.count(models.Message.id)).where(
                models.Message.room_id == room_id,
                models.Message.role == "assistant",
            )
        )
        return result.scalar() or 0

    async def _cleanup_cache(self):
        """
        Clean up expired cache entries.
        This runs every 5 minutes to prevent memory bloat.
        """
        try:
            from infrastructure.cache import get_cache

            cache = get_cache()
            cache.cleanup_expired()
            cache.log_stats()
        except Exception as e:
            logger.error(f"Error during cache cleanup: {e}")
