"""
Tape-based turn scheduling data structures.

This module defines the core data structures for the tape scheduling system:
- TurnCell: A single cell in the tape (one or more agents)
- TurnTape: The complete schedule with position tracking
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class CellType(Enum):
    """Type of cell in the tape."""

    SEQUENTIAL = "sequential"  # Single agent executes
    CONCURRENT = "concurrent"  # Multiple agents execute via asyncio.gather
    INTERRUPT = "interrupt"  # Interrupt agents after a non-transparent agent


@dataclass
class TurnCell:
    """
    A single cell in the turn tape.

    Attributes:
        cell_type: Type of this cell (sequential, concurrent, interrupt)
        agent_ids: List of agent IDs to execute in this cell
        triggering_agent_id: For interrupt cells, the agent that triggered this
    """

    cell_type: CellType
    agent_ids: List[int] = field(default_factory=list)
    triggering_agent_id: Optional[int] = None

    @property
    def is_concurrent(self) -> bool:
        """Check if this cell should execute agents concurrently."""
        return len(self.agent_ids) > 1 and self.cell_type == CellType.CONCURRENT

    def __repr__(self) -> str:
        if not self.agent_ids:
            return f"[{self.cell_type.value}:empty]"
        agents = ",".join(str(id) for id in self.agent_ids)
        suffix = "(INT)" if self.cell_type == CellType.INTERRUPT else ""
        return f"[{agents}{suffix}]"


@dataclass
class ExecutionResult:
    """Result of tape execution."""

    total_responses: int = 0
    total_skips: int = 0
    was_interrupted: bool = False
    was_paused: bool = False
    reached_limit: bool = False
    all_skipped: bool = False


@dataclass
class TurnTape:
    """
    The complete turn schedule for a conversation round.

    Attributes:
        cells: Ordered list of cells to execute
        position: Current execution position (0-indexed)
        total_responses: Count of successful agent responses
        total_skips: Count of agent skips
    """

    cells: List[TurnCell] = field(default_factory=list)
    position: int = 0
    total_responses: int = 0
    total_skips: int = 0

    def current_cell(self) -> Optional[TurnCell]:
        """Get the current cell to execute."""
        if self.position < len(self.cells):
            return self.cells[self.position]
        return None

    def advance(self) -> bool:
        """Advance to next cell. Returns True if more cells remain."""
        self.position += 1
        return self.position < len(self.cells)

    def remaining_cells(self) -> List[TurnCell]:
        """Get cells remaining to be executed."""
        return self.cells[self.position :]

    def is_exhausted(self) -> bool:
        """Check if all cells have been processed."""
        return self.position >= len(self.cells)

    def cut_at_current(self) -> None:
        """Cut the tape at current position (for user interruption)."""
        self.cells = self.cells[: self.position]

    def __repr__(self) -> str:
        cells_repr = " -> ".join(repr(cell) for cell in self.cells)
        return f"Tape[pos={self.position}]: {cells_repr}"
