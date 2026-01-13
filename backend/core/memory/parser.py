"""
Utility functions for parsing long-term memory files with subtitles.
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("MemoryParser")


def parse_long_term_memory(file_path: Path) -> Dict[str, str]:
    """
    Parse a long-term memory file with subtitle format.

    Format:
        ## [subtitle]
        Content for this memory...

        ## [another_subtitle]
        More content...

    Args:
        file_path: Path to the long_term_memory.md file

    Returns:
        Dictionary mapping subtitles to their content
    """
    if not file_path.exists():
        logger.debug(f"Long-term memory file not found: {file_path}")
        return {}

    try:
        content = file_path.read_text(encoding="utf-8")

        # Split by subtitle headers: ## [subtitle]
        # Pattern matches: ## [text]
        pattern = r"^##\s*\[([^\]]+)\]"

        memories = {}
        current_subtitle = None
        current_content = []

        for line in content.split("\n"):
            # Check if this line is a subtitle header
            match = re.match(pattern, line)
            if match:
                # Save previous memory if exists
                if current_subtitle:
                    memories[current_subtitle] = "\n".join(current_content).strip()

                # Start new memory
                current_subtitle = match.group(1)
                current_content = []
            else:
                # Accumulate content lines
                if current_subtitle is not None:
                    current_content.append(line)

        # Save last memory
        if current_subtitle:
            memories[current_subtitle] = "\n".join(current_content).strip()

        return memories

    except Exception as e:
        logger.error(f"Error parsing long-term memory file {file_path}: {e}")
        return {}


def get_memory_subtitles(file_path: Path) -> List[str]:
    """
    Extract just the subtitles from a long-term memory file.

    Args:
        file_path: Path to the long_term_memory.md file

    Returns:
        List of subtitle strings
    """
    memories = parse_long_term_memory(file_path)
    return list(memories.keys())


def get_memory_by_subtitle(file_path: Path, subtitle: str) -> Optional[str]:
    """
    Retrieve a specific memory by its subtitle.

    Args:
        file_path: Path to the long_term_memory.md file
        subtitle: The subtitle to look up

    Returns:
        The memory content, or None if not found
    """
    memories = parse_long_term_memory(file_path)
    return memories.get(subtitle)
