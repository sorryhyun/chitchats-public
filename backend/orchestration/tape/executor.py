"""
Tape executor for processing turn schedules.

This module executes turn tapes cell by cell with a single
pause/limit check location, simplifying the orchestration logic.
"""

import asyncio
import logging
from typing import Dict, Optional

import crud
from domain.contexts import OrchestrationContext

from .models import CellType, ExecutionResult, TurnCell, TurnTape

logger = logging.getLogger("TapeExecutor")


class TapeExecutor:
    """
    Executes turn tapes cell by cell.

    Features:
    - Single pause check location (before each cell)
    - Single limit check location (before each cell)
    - User interrupt handling (stops execution, tape cut externally)
    - Skip counting for all-skipped detection
    """

    def __init__(
        self,
        response_generator,
        agents_by_id: Dict[int, any],
        max_total_messages: int = 30,
    ):
        """
        Initialize executor.

        Args:
            response_generator: ResponseGenerator instance
            agents_by_id: Dict mapping agent IDs to agent objects
            max_total_messages: Safety limit to prevent infinite loops
        """
        self.response_generator = response_generator
        self.agents_by_id = agents_by_id
        self.max_total_messages = max_total_messages

    async def execute(
        self,
        tape: TurnTape,
        orch_context: OrchestrationContext,
        user_message_content: Optional[str] = None,
        current_total: int = 0,
    ) -> ExecutionResult:
        """
        Execute the tape cell by cell.

        Args:
            tape: The TurnTape to execute
            orch_context: Orchestration context with db, room_id, agent_manager
            user_message_content: For initial round (None for follow-ups)
            current_total: Current total messages count (for limit checking across tapes)

        Returns:
            ExecutionResult with counts and status flags
        """
        result = ExecutionResult()
        running_total = current_total

        while not tape.is_exhausted():
            # ===== SINGLE PAUSE CHECK =====
            room = await crud.get_room_cached(orch_context.db, orch_context.room_id)
            if room and room.is_paused:
                logger.info(f"⏸️  Tape paused | Room: {orch_context.room_id}")
                result.was_paused = True
                break

            # ===== SINGLE LIMIT CHECK (max_total_messages) =====
            if running_total >= self.max_total_messages:
                logger.info(
                    f"🛑 Tape limit reached (max_total_messages) | Room: {orch_context.room_id} | Total: {running_total}"
                )
                result.reached_limit = True
                break

            # ===== SINGLE LIMIT CHECK (room.max_interactions) =====
            if room and room.max_interactions is not None:
                current_count = await self._count_agent_messages(orch_context.db, orch_context.room_id)
                if current_count >= room.max_interactions:
                    logger.info(
                        f"🛑 Room interaction limit reached | Room: {orch_context.room_id} | "
                        f"Count: {current_count}/{room.max_interactions}"
                    )
                    result.reached_limit = True
                    break

            # Get current cell
            cell = tape.current_cell()
            if cell is None:
                break

            # Execute current cell
            try:
                cell_result = await self._execute_cell(cell, orch_context, user_message_content)
                result.total_responses += cell_result["responses"]
                result.total_skips += cell_result["skips"]
                running_total += cell_result["responses"]

            except asyncio.CancelledError:
                logger.info(f"⏹️  Tape interrupted | Room: {orch_context.room_id}")
                result.was_interrupted = True
                tape.cut_at_current()
                raise

            # Advance to next cell
            tape.advance()

            # Clear user_message_content after first cell (follow-up context)
            user_message_content = None

        # Check if all agents skipped (no responses, some skips)
        if result.total_responses == 0 and result.total_skips > 0:
            result.all_skipped = True

        return result

    async def _execute_cell(
        self,
        cell: TurnCell,
        orch_context: OrchestrationContext,
        user_message_content: Optional[str],
    ) -> Dict[str, int]:
        """
        Execute a single cell.

        Returns:
            Dict with "responses" and "skips" counts
        """
        # Get agents for this cell (filter out any that no longer exist)
        agents = [self.agents_by_id[id] for id in cell.agent_ids if id in self.agents_by_id]

        if not agents:
            logger.debug(f"Cell has no valid agents, skipping: {cell}")
            return {"responses": 0, "skips": 0}

        logger.debug(f"Executing cell: {cell} with {len(agents)} agent(s)")

        if cell.is_concurrent:
            # Concurrent execution (multiple agents at once)
            return await self._execute_concurrent(agents, orch_context, user_message_content, cell)
        else:
            # Sequential execution (one agent, or interrupt agents one by one)
            return await self._execute_sequential(agents, orch_context, user_message_content, cell)

    async def _execute_sequential(
        self,
        agents: list,
        orch_context: OrchestrationContext,
        user_message_content: Optional[str],
        cell: TurnCell,
    ) -> Dict[str, int]:
        """
        Execute agents sequentially (one at a time).

        For INTERRUPT cells, process all agents sequentially.
        For SEQUENTIAL cells, there's only one agent.
        """
        responses = 0
        skips = 0

        for agent in agents:
            # Skip if this agent triggered the interrupt (self-interruption prevention)
            # This is handled in generator now, but double-check here
            if cell.cell_type == CellType.INTERRUPT and cell.triggering_agent_id == agent.id:
                logger.debug(f"⏭️  Skipping self-interrupt for {agent.name}")
                continue

            try:
                responded = await self.response_generator.generate_response(
                    orch_context=orch_context,
                    agent=agent,
                    user_message_content=user_message_content,
                )

                if responded:
                    responses += 1
                    logger.debug(f"✅ Agent {agent.name} responded")
                else:
                    skips += 1
                    logger.debug(f"⏭️  Agent {agent.name} skipped")

            except asyncio.CancelledError:
                # Re-raise cancellation to stop processing
                raise
            except Exception as e:
                logger.error(f"❌ Agent {agent.name} error: {e}")
                # Errors don't count as skips - try to continue
                try:
                    await orch_context.db.rollback()
                except Exception:
                    pass

        return {"responses": responses, "skips": skips}

    async def _execute_concurrent(
        self,
        agents: list,
        orch_context: OrchestrationContext,
        user_message_content: Optional[str],
        cell: TurnCell,
    ) -> Dict[str, int]:
        """Execute multiple agents concurrently via asyncio.gather."""
        tasks = [
            self.response_generator.generate_response(
                orch_context=orch_context,
                agent=agent,
                user_message_content=user_message_content,
            )
            for agent in agents
        ]

        logger.debug(f"⏳ Executing {len(tasks)} agents concurrently...")
        results = await asyncio.gather(*tasks, return_exceptions=True)

        responses = 0
        skips = 0

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"❌ Agent {agents[i].name} error: {result}")
                # Errors don't count as skips
            elif result is True:
                responses += 1
                logger.debug(f"✅ Agent {agents[i].name} responded")
            else:
                skips += 1
                logger.debug(f"⏭️  Agent {agents[i].name} skipped")

        return {"responses": responses, "skips": skips}

    async def _count_agent_messages(self, db, room_id: int) -> int:
        """Count agent messages in room."""
        from infrastructure.database import Message
        from sqlalchemy import func
        from sqlalchemy.future import select

        result = await db.execute(
            select(func.count(Message.id)).where(
                Message.room_id == room_id,
                Message.role == "assistant",
            )
        )
        return result.scalar() or 0
