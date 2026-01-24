"""
Whiteboard Diff Parser and Applier

Parses diff output from 화이트보드 agent and applies it to maintain full state.

Diff Format:
- `+ line` : Add line
- `- line` : Remove line
- `~ old → new` : Modify line
- `CLEAR` : Clear entire board
"""

import re
from dataclasses import dataclass
from typing import List, Tuple

WHITEBOARD_AGENT_NAME = "화이트보드"


@dataclass
class WhiteboardState:
    lines: List[str]

    @property
    def is_empty(self) -> bool:
        return len(self.lines) == 0


def is_whiteboard_diff(content: str) -> bool:
    """Check if a message contains whiteboard diff."""
    return "[화이트보드 diff]" in content


def is_whiteboard_content(content: str) -> bool:
    """Check if content is rendered whiteboard (starts with [화이트보드])."""
    return content.startswith("[화이트보드]")


def parse_whiteboard_diff(content: str) -> List[Tuple[str, str, str]]:
    """
    Parse whiteboard diff from message content.

    Returns list of operations: (type, content1, content2)
    - ('add', content, '')
    - ('remove', content, '')
    - ('modify', old_content, new_content)
    - ('clear', '', '')
    """
    operations = []

    # Extract content after [화이트보드 diff]
    match = re.search(r"\[화이트보드 diff\]\s*([\s\S]*?)(?:```|$)", content)
    if not match:
        return operations

    diff_content = match.group(1).strip()
    lines = diff_content.split("\n")

    for line in lines:
        trimmed = line.strip()

        if trimmed == "CLEAR":
            operations.append(("clear", "", ""))
            continue

        if trimmed.startswith("+ "):
            operations.append(("add", trimmed[2:], ""))
            continue

        if trimmed.startswith("- "):
            operations.append(("remove", trimmed[2:], ""))
            continue

        if trimmed.startswith("~ "):
            # Format: ~ old content → new content
            modify_content = trimmed[2:]
            arrow_index = modify_content.find(" → ")
            if arrow_index != -1:
                old_content = modify_content[:arrow_index]
                new_content = modify_content[arrow_index + 3 :]
                operations.append(("modify", old_content, new_content))
            continue

    return operations


def normalize_for_match(line: str) -> str:
    """Normalize line for fuzzy matching (handles whitespace differences)."""
    return re.sub(r"\s+", " ", line).strip()


def apply_diff(state: WhiteboardState, operations: List[Tuple[str, str, str]]) -> WhiteboardState:
    """Apply diff operations to whiteboard state."""
    lines = list(state.lines)

    for op_type, content1, content2 in operations:
        if op_type == "clear":
            lines = []
        elif op_type == "add":
            lines.append(content1)
        elif op_type == "remove":
            # Find and remove the line (fuzzy match to handle whitespace differences)
            normalized_target = normalize_for_match(content1)
            for i, line in enumerate(lines):
                if normalize_for_match(line) == normalized_target:
                    lines.pop(i)
                    break
        elif op_type == "modify":
            # Find and replace the line
            normalized_old = normalize_for_match(content1)
            for i, line in enumerate(lines):
                if normalize_for_match(line) == normalized_old:
                    lines[i] = content2
                    break

    return WhiteboardState(lines=lines)


def render_whiteboard(state: WhiteboardState) -> str:
    """Render whiteboard state as displayable content."""
    if state.is_empty:
        return ""
    return "[화이트보드]\n" + "\n".join(state.lines)


def create_empty_whiteboard() -> WhiteboardState:
    """Create initial empty whiteboard state."""
    return WhiteboardState(lines=[])


def process_messages_for_whiteboard(messages: List) -> dict:
    """
    Process messages and return a map of message_id -> rendered_content
    for whiteboard messages.

    This accumulates diff operations to show the full state at each point.

    Args:
        messages: List of message objects with content and agent attributes

    Returns:
        Dict mapping message_id to rendered whiteboard content
    """
    rendered_map = {}
    state = create_empty_whiteboard()

    for msg in messages:
        # Check if this is a message from the whiteboard agent
        agent_name = getattr(msg, "agent", None)
        if agent_name:
            agent_name = getattr(agent_name, "name", None)

        if agent_name != WHITEBOARD_AGENT_NAME:
            continue

        content = getattr(msg, "content", "")
        if not content:
            continue

        if is_whiteboard_diff(content):
            # Parse and apply the diff
            operations = parse_whiteboard_diff(content)
            if operations:
                state = apply_diff(state, operations)

            # Store the rendered content for this message
            rendered_map[msg.id] = render_whiteboard(state)
        else:
            # Not a diff format - might be old full-content format
            rendered_map[msg.id] = content

    return rendered_map
