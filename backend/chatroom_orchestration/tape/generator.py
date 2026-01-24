"""
Tape generator for creating turn schedules.

This module generates turn tapes based on agent configurations,
weaving in interrupt agents appropriately.
"""

import logging
import random
from typing import List, Tuple

from .models import CellType, TurnCell, TurnTape

logger = logging.getLogger("TapeGenerator")


class TapeGenerator:
    """
    Generates turn tapes based on agent configurations.

    Algorithm:
    1. Separate agents into categories (priority, regular, last, interrupt)
    2. Build initial tape: priority first, then shuffled regular, then last agents
    3. Weave interrupt agents after each non-transparent agent cell
    4. Build follow-up tapes: same order as initial
    """

    def __init__(self, agents: List, interrupt_agents: List, mentioned_agent_id: int = None):
        """
        Initialize generator with agent lists.

        Args:
            agents: Non-interrupt agents (may include priority agents)
            interrupt_agents: Agents with interrupt_every_turn=1
            mentioned_agent_id: Agent ID to prioritize first (from @ mention)
        """
        self.agents = agents
        self.interrupt_agents = interrupt_agents
        self.mentioned_agent_id = mentioned_agent_id

        # Pre-sort agents into three categories
        self.priority_agents, self.regular_agents, self.last_agents = self._separate_by_priority(agents)

        # Log configuration
        if self.priority_agents:
            priority_info = ", ".join([f"{a.name}(p={getattr(a, 'priority', 0)})" for a in self.priority_agents])
            logger.debug(f"Priority agents: {priority_info}")
        if self.regular_agents:
            logger.debug(f"Regular agents: {[a.name for a in self.regular_agents]}")
        if self.last_agents:
            last_info = ", ".join([f"{a.name}(p={getattr(a, 'priority', 0)})" for a in self.last_agents])
            logger.debug(f"Last agents: {last_info}")
        if self.interrupt_agents:
            logger.debug(f"Interrupt agents: {[a.name for a in self.interrupt_agents]}")

    def _separate_by_priority(self, agents: List) -> Tuple[List, List, List]:
        """Separate agents into priority (>0), regular (==0), and last (<0) groups."""
        priority = []
        regular = []
        last = []

        for agent in agents:
            p = getattr(agent, "priority", 0)
            if p > 0:
                priority.append(agent)
            elif p < 0:
                last.append(agent)
            else:
                regular.append(agent)

        # Sort priority agents descending (higher priority first)
        priority.sort(key=lambda a: getattr(a, "priority", 0), reverse=True)
        # Sort last agents ascending (more negative = later)
        last.sort(key=lambda a: getattr(a, "priority", 0))

        return priority, regular, last

    def _is_transparent(self, agent) -> bool:
        """Check if agent is transparent (doesn't trigger interrupt agents)."""
        return getattr(agent, "transparent", 0) == 1

    def _make_interrupt_cell(self, triggering_agent_id: int = None, exclude_agent_id: int = None) -> TurnCell:
        """
        Create an interrupt cell with all interrupt agents.

        Args:
            triggering_agent_id: Agent that triggered this interrupt (for logging)
            exclude_agent_id: Agent ID to exclude (for self-interruption prevention)
        """
        agent_ids = [a.id for a in self.interrupt_agents if a.id != exclude_agent_id]
        return TurnCell(
            cell_type=CellType.INTERRUPT,
            agent_ids=agent_ids,
            triggering_agent_id=triggering_agent_id,
        )

    def generate_initial_round(self) -> TurnTape:
        """
        Generate tape for initial response round (after user message).

        Structure:
        1. Interrupt agents respond to user first
        2. Mentioned agent (if specified via @mention) responds first
        3. Priority agents sequential (each may trigger interrupts)
        4. Regular agents sequential in shuffled order (each may trigger interrupts)
        5. Last agents sequential (priority < 0, respond after everyone else)
        """
        tape = TurnTape()

        # Cell 0: Interrupt agents respond to user message first
        if self.interrupt_agents:
            tape.cells.append(
                TurnCell(
                    cell_type=CellType.INTERRUPT,
                    agent_ids=[a.id for a in self.interrupt_agents],
                    triggering_agent_id=None,  # Triggered by user
                )
            )

        # Find mentioned agent (if specified) - they respond first
        mentioned_agent = None
        if self.mentioned_agent_id:
            for agent in self.agents:
                if agent.id == self.mentioned_agent_id:
                    mentioned_agent = agent
                    # Add mentioned agent first
                    tape.cells.append(
                        TurnCell(
                            cell_type=CellType.SEQUENTIAL,
                            agent_ids=[agent.id],
                        )
                    )
                    # Add interrupt cell after if non-transparent
                    if self.interrupt_agents and not self._is_transparent(agent):
                        tape.cells.append(self._make_interrupt_cell(triggering_agent_id=agent.id))
                    logger.info(f"🎯 Mentioned agent {agent.name} placed first in tape")
                    break

        # Priority agents: sequential, each triggers interrupts if non-transparent
        for agent in self.priority_agents:
            # Skip if already added as mentioned agent
            if mentioned_agent and agent.id == self.mentioned_agent_id:
                continue

            # Add priority agent cell
            tape.cells.append(
                TurnCell(
                    cell_type=CellType.SEQUENTIAL,
                    agent_ids=[agent.id],
                )
            )

            # Add interrupt cell after non-transparent agents
            if self.interrupt_agents and not self._is_transparent(agent):
                tape.cells.append(self._make_interrupt_cell(triggering_agent_id=agent.id))

        # Regular agents: sequential (one at a time, shuffled order)
        # Filter out mentioned agent to avoid duplicate
        shuffled_regular = [a for a in self.regular_agents if not (mentioned_agent and a.id == self.mentioned_agent_id)]
        random.shuffle(shuffled_regular)

        for agent in shuffled_regular:
            tape.cells.append(
                TurnCell(
                    cell_type=CellType.SEQUENTIAL,
                    agent_ids=[agent.id],
                )
            )

            # Add interrupt cell after non-transparent agents
            if self.interrupt_agents and not self._is_transparent(agent):
                tape.cells.append(
                    self._make_interrupt_cell(
                        triggering_agent_id=agent.id,
                        exclude_agent_id=agent.id,
                    )
                )

        # Last agents: sequential (priority < 0, respond after everyone else)
        for agent in self.last_agents:
            # Skip if already added as mentioned agent
            if mentioned_agent and agent.id == self.mentioned_agent_id:
                continue

            tape.cells.append(
                TurnCell(
                    cell_type=CellType.SEQUENTIAL,
                    agent_ids=[agent.id],
                )
            )

            # Add interrupt cell after non-transparent agents
            if self.interrupt_agents and not self._is_transparent(agent):
                tape.cells.append(
                    self._make_interrupt_cell(
                        triggering_agent_id=agent.id,
                        exclude_agent_id=agent.id,
                    )
                )

        logger.info(f"Generated initial tape: {tape}")
        return tape

    def generate_follow_up_round(self, round_num: int = 0) -> TurnTape:
        """
        Generate tape for follow-up round.

        Structure:
        - All agents sequential
        - Priority agents first (in priority order)
        - Regular agents shuffled (for natural conversation)
        - Last agents at the end (priority < 0)
        - Interrupt after each non-transparent agent

        Args:
            round_num: Round number (for logging)
        """
        tape = TurnTape()

        # Shuffle regular agents for natural conversation flow
        shuffled_regular = list(self.regular_agents)
        random.shuffle(shuffled_regular)

        # Combine: priority first, then shuffled regular, then last agents
        ordered_agents = self.priority_agents + shuffled_regular + self.last_agents

        for agent in ordered_agents:
            # Add agent cell (sequential)
            tape.cells.append(
                TurnCell(
                    cell_type=CellType.SEQUENTIAL,
                    agent_ids=[agent.id],
                )
            )

            # Add interrupt cell after non-transparent agents
            # Exclude the triggering agent from interrupt list to prevent self-interruption
            if self.interrupt_agents and not self._is_transparent(agent):
                tape.cells.append(
                    self._make_interrupt_cell(
                        triggering_agent_id=agent.id,
                        exclude_agent_id=agent.id,  # Prevent self-interruption
                    )
                )

        logger.debug(f"Generated follow-up tape (round {round_num + 1}): {tape}")
        return tape
