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
import models
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from orchestration import ChatOrchestrator
from sdk import AgentManager
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = logging.getLogger("BackgroundScheduler")


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
        # Error tracking for backoff
        self._consecutive_errors = 0
        self._max_backoff_errors = 5  # After this many errors, skip processing for a cycle
        self._cleanup_tasks: set[asyncio.Task] = set()  # Track cleanup tasks

    def start(self):
        """Start the background scheduler."""
        if not self.is_running:
            # Run autonomous chat rounds every 2 seconds
            self.scheduler.add_job(
                self._process_active_rooms,
                "interval",
                seconds=2,
                id="process_active_rooms",
                replace_existing=True,
                max_instances=1,  # Only one instance at a time (prevents overwhelming system)
                coalesce=True,  # Skip missed runs if previous job still running
            )

            # Clean up expired cache entries every 5 minutes
            self.scheduler.add_job(
                self._cleanup_cache, "interval", minutes=5, id="cleanup_cache", replace_existing=True
            )

            self.scheduler.start()
            self.is_running = True
            logger.info(
                "🚀 Background scheduler started - processing rooms every 2 seconds, cache cleanup every 5 minutes"
            )

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

        Implements exponential backoff on repeated errors.
        """
        # Check if we should skip due to backoff
        if self._consecutive_errors >= self._max_backoff_errors:
            logger.warning(
                f"⏸️ Skipping processing cycle due to {self._consecutive_errors} consecutive errors. "
                "Will retry next cycle."
            )
            self._consecutive_errors = 0  # Reset to try again next cycle
            return

        try:
            async with self._session_scope() as db:
                active_rooms = await self._get_active_rooms(db)

            if not active_rooms:
                # Don't log when there's no activity (too noisy)
                # Reset error counter on successful (idle) cycle
                self._consecutive_errors = 0
                return

            logger.info(f"🔄 Processing {len(active_rooms)} active room(s)")

            semaphore = asyncio.Semaphore(self.max_concurrent_rooms) if self.max_concurrent_rooms else None
            room_errors = 0

            async def process_with_error_handling(room):
                nonlocal room_errors
                try:
                    if semaphore:
                        async with semaphore:
                            await self._process_room_for_background_job(room)
                    else:
                        await self._process_room_for_background_job(room)
                except Exception as e:
                    room_errors += 1
                    logger.error(f"❌ Error processing room {room.id}: {e}")
                    import traceback

                    traceback.print_exc()

            # Process all active rooms concurrently with a small cap
            await asyncio.gather(*[process_with_error_handling(room) for room in active_rooms])

            # Update error tracking
            if room_errors == 0:
                self._consecutive_errors = 0  # Reset on success
            elif room_errors == len(active_rooms):
                self._consecutive_errors += 1  # All rooms failed
                logger.warning(
                    f"⚠️ All {room_errors} room(s) failed. Consecutive error count: {self._consecutive_errors}"
                )

        except Exception as e:
            self._consecutive_errors += 1
            logger.error(f"💥 Error in _process_active_rooms (consecutive: {self._consecutive_errors}): {e}")
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
        - Has at least 2 agents
        """
        # Calculate cutoff time (5 minutes ago)
        cutoff_time = datetime.utcnow() - timedelta(minutes=5)

        # Use the room's last_activity_at field to avoid repeated full message scans
        stmt = (
            select(models.Room)
            .options(selectinload(models.Room.agents))  # Eager load agents
            .where(models.Room.is_paused == False, models.Room.last_activity_at >= cutoff_time)
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
        """
        Remove completed tasks from active_room_tasks to prevent memory leak.
        Also logs any exceptions that occurred in completed tasks.
        """
        completed_rooms = [room_id for room_id, task in self.chat_orchestrator.active_room_tasks.items() if task.done()]
        for room_id in completed_rooms:
            task = self.chat_orchestrator.active_room_tasks[room_id]
            del self.chat_orchestrator.active_room_tasks[room_id]

            # Check if task had an exception (important for debugging)
            try:
                exc = task.exception()
                if exc:
                    logger.error(f"Task for room {room_id} failed with exception: {exc}")
            except (asyncio.CancelledError, asyncio.InvalidStateError):
                pass  # Task was cancelled or still running (shouldn't happen since we check done())

            logger.debug(f"Cleaned up completed task for room {room_id}")

    async def _process_room_autonomous_round(self, db: AsyncSession, room: models.Room):
        """
        Process one autonomous round for a room.

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
            current_count = await self.chat_orchestrator._count_agent_messages(db, room.id)
            if current_count >= room.max_interactions:
                logger.debug(f"Room {room.id} reached max interactions ({room.max_interactions})")
                return

        # Run one follow-up round
        # Polling architecture doesn't use real-time broadcasting
        from domain.contexts import OrchestrationContext

        orch_context = OrchestrationContext(db=db, room_id=room.id, agent_manager=self.agent_manager)

        # Use the existing _follow_up_rounds logic with max 1 round
        original_max = self.chat_orchestrator.max_follow_up_rounds
        self.chat_orchestrator.max_follow_up_rounds = 1  # Only one round at a time

        try:
            await self.chat_orchestrator._follow_up_rounds(orch_context=orch_context, agents=agents, total_messages=0)
            logger.info(f"✅ Autonomous round complete | Room: {room.id}")
        finally:
            # Restore original setting
            self.chat_orchestrator.max_follow_up_rounds = original_max

    async def _cleanup_cache(self):
        """
        Clean up expired cache entries.
        This runs every 5 minutes to prevent memory bloat.
        """
        try:
            from utils.cache import get_cache

            cache = get_cache()
            cache.cleanup_expired()
            cache.log_stats()
        except Exception as e:
            logger.error(f"Error during cache cleanup: {e}")
