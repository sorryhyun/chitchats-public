"""
Agent ordering and separation utilities.

This module handles the logic for separating and ordering agents
based on priority levels and interrupt settings.
"""

import logging
from typing import List, Tuple

logger = logging.getLogger("AgentOrdering")


def separate_priority_agents(agents: List) -> Tuple[List, List]:
    """
    Separate agents into priority and regular groups based on agent.priority field.

    Args:
        agents: List of agent objects

    Returns:
        Tuple of (priority_agents, regular_agents) sorted by priority (higher first)
    """
    priority_agents = []
    regular_agents = []

    for agent in agents:
        # Agents with priority > 0 are considered priority agents
        if getattr(agent, "priority", 0) > 0:
            priority_agents.append(agent)
        else:
            regular_agents.append(agent)

    # Sort priority agents by priority value (descending: higher priority first)
    priority_agents.sort(key=lambda a: getattr(a, "priority", 0), reverse=True)

    return priority_agents, regular_agents


def separate_interrupt_agents(agents: List) -> Tuple[List, List]:
    """
    Separate agents into interrupt and regular groups based on interrupt_every_turn.

    Args:
        agents: List of agent objects

    Returns:
        Tuple of (interrupt_agents, regular_agents)
        Interrupt agents are sorted by priority (higher first)
    """
    interrupt_agents = []
    regular_agents = []

    for agent in agents:
        if getattr(agent, "interrupt_every_turn", 0) == 1:
            interrupt_agents.append(agent)
        else:
            regular_agents.append(agent)

    # Sort interrupt agents by priority (higher first) so priority ones respond first
    interrupt_agents.sort(key=lambda a: getattr(a, "priority", 0), reverse=True)

    return interrupt_agents, regular_agents
