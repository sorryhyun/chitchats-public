"""
Agent configuration parser for markdown files.

This module handles loading agent configurations from markdown files
following a specific format with standardized sections.

Also includes memory parsing utilities for long-term memory files.
"""

import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from domain.agent_config import AgentConfigData

logger = logging.getLogger("ConfigParser")

# Regex pattern for "지금 드는 생각" (current thoughts) section
THOUGHTS_PATTERN = r'\*\*지금 드는 생각:\*\*\s*"([^"]*)"'


@dataclass
class MemoryEntry:
    """A parsed memory entry with content and optional thoughts."""

    content: str
    thoughts: Optional[str] = None


def _get_agents_dir() -> Path:
    """Get the agents directory, handling both dev and bundled modes."""
    if getattr(sys, "frozen", False):
        # Running as PyInstaller bundle - agents are next to exe
        return Path(sys.executable).parent / "agents"
    else:
        # Running in development - relative to this file
        backend_dir = Path(__file__).parent.parent
        project_root = backend_dir.parent
        return project_root / "agents"


# =============================================================================
# Utility Functions
# =============================================================================


def _read_file_with_fallback(file_path: Path) -> str:
    """Read file with encoding fallback (UTF-8 -> cp949 -> latin-1)."""
    encodings = ["utf-8", "cp949", "latin-1"]
    for encoding in encodings:
        try:
            return file_path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    # If all fail, read as binary and decode with errors='replace'
    return file_path.read_bytes().decode("utf-8", errors="replace")


# =============================================================================
# Memory Parsing Functions
# =============================================================================


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
        content = _read_file_with_fallback(file_path)

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


def parse_long_term_memory_with_thoughts(file_path: Path) -> Dict[str, MemoryEntry]:
    """
    Parse a long-term memory file, separating content from thoughts.

    This extracts "지금 드는 생각" (current thoughts) from each memory entry.
    The thoughts can be shown as previews in tool descriptions while the
    actual recalled content excludes them.

    Format:
        ## [subtitle]
        Content for this memory...

        **지금 드는 생각:** "Some thought about this memory"

    Args:
        file_path: Path to the memory file

    Returns:
        Dictionary mapping subtitles to MemoryEntry objects with content and thoughts
    """
    raw_memories = parse_long_term_memory(file_path)
    result: Dict[str, MemoryEntry] = {}

    for subtitle, full_content in raw_memories.items():
        # Extract thoughts using the pattern
        match = re.search(THOUGHTS_PATTERN, full_content)
        thoughts = match.group(1) if match else None

        # Strip thoughts from content
        content = re.sub(r'\n?\*\*지금 드는 생각:\*\*\s*"[^"]*"', "", full_content).strip()

        result[subtitle] = MemoryEntry(content=content, thoughts=thoughts)

    return result


# =============================================================================
# Agent Configuration Parsing
# =============================================================================


def parse_agent_config(file_path: str) -> Optional[AgentConfigData]:
    """
    Parse an agent configuration from a folder with separate markdown files.

    Expected folder structure:
       agents/agent_name/
         ├── in_a_nutshell.md
         ├── characteristics.md
         ├── recent_events.md
         └── consolidated_memory.md (or long_term_memory.md)

    Args:
        file_path: Path to the agent folder (can be relative to project root/work_dir)

    Returns:
        AgentConfigData object or None if folder doesn't exist
    """
    # Resolve path relative to agents directory if not absolute
    path = Path(file_path)
    if not path.is_absolute():
        # If path starts with "agents/", resolve relative to work_dir
        if file_path.startswith("agents/") or file_path.startswith("agents\\"):
            agents_dir = _get_agents_dir()
            # Remove "agents/" prefix and resolve from agents_dir
            relative_path = file_path.replace("agents/", "").replace("agents\\", "")
            path = agents_dir / relative_path
        else:
            # Assume it's relative to work_dir
            if getattr(sys, "frozen", False):
                work_dir = Path(sys.executable).parent
            else:
                backend_dir = Path(__file__).parent.parent
                work_dir = backend_dir.parent
            path = work_dir / file_path

    if not path.exists() or not path.is_dir():
        return None

    try:
        return _parse_folder_config(path)
    except Exception as e:
        logger.error(f"Error parsing agent config {path}: {e}")
        return None


def _parse_folder_config(folder_path: Path) -> AgentConfigData:
    """Parse agent configuration from folder with separate .md files."""

    def read_section(filename: str) -> str:
        file_path = folder_path / filename
        if file_path.exists():
            return _read_file_with_fallback(file_path).strip()
        return ""

    def find_profile_pic() -> Optional[str]:
        """Find profile picture file in the agent folder."""
        # Common image extensions to look for
        image_extensions = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"]
        # Common profile pic filenames
        common_names = ["profile", "avatar", "picture", "photo"]

        # First, try common profile pic filenames
        for name in common_names:
            for ext in image_extensions:
                pic_path = folder_path / f"{name}{ext}"
                if pic_path.exists():
                    return pic_path.name

        # If no common name found, look for any image file
        for ext in image_extensions:
            for file in folder_path.glob(f"*{ext}"):
                return file.name

        return None

    def find_voice_file() -> tuple[Optional[str], Optional[str]]:
        """Find voice sample file and its transcript in the agent folder.

        Returns:
            Tuple of (voice_file_path, voice_text) or (None, None) if not found
        """
        voice_extensions = [".wav", ".mp3", ".flac", ".ogg"]
        voice_names = ["voice", "sample", "tts"]

        voice_path = None
        # First, try common voice file names
        for name in voice_names:
            for ext in voice_extensions:
                candidate = folder_path / f"{name}{ext}"
                if candidate.exists():
                    voice_path = str(candidate)
                    break
            if voice_path:
                break

        # If no common name found, look for any audio file
        if not voice_path:
            for ext in voice_extensions:
                for file in folder_path.glob(f"*{ext}"):
                    voice_path = str(file)
                    break
                if voice_path:
                    break

        if not voice_path:
            return None, None

        # Look for transcript file
        voice_text = None
        text_file = folder_path / "voice_text.txt"
        if text_file.exists():
            try:
                voice_text = _read_file_with_fallback(text_file).strip()
            except Exception as e:
                logger.warning(f"Failed to read voice_text.txt: {e}")

        return voice_path, voice_text

    # Parse long-term memory file for recall tool
    long_term_memory_file = folder_path / "consolidated_memory.md"
    long_term_memory_index = None
    long_term_memory_subtitles = None
    long_term_memory_entries = None

    if long_term_memory_file.exists():
        # Import settings to check if memory preview with thoughts is enabled
        from core.settings import get_settings

        settings = get_settings()

        if settings.memory_preview_with_thoughts:
            # Parse with thoughts extraction
            long_term_memory_entries = parse_long_term_memory_with_thoughts(long_term_memory_file)
            if long_term_memory_entries:
                # Create index from entries (for backward compatibility)
                long_term_memory_index = {k: v.content for k, v in long_term_memory_entries.items()}
                long_term_memory_subtitles = ", ".join(f"'{s}'" for s in long_term_memory_entries.keys())
        else:
            # Legacy parsing without thoughts
            long_term_memory_index = parse_long_term_memory(long_term_memory_file)
            if long_term_memory_index:
                long_term_memory_subtitles = ", ".join(f"'{s}'" for s in long_term_memory_index.keys())

    # Find voice files
    voice_file, voice_text = find_voice_file()

    return AgentConfigData(
        in_a_nutshell=read_section("in_a_nutshell.md"),
        characteristics=read_section("characteristics.md"),
        recent_events=read_section("recent_events.md"),
        profile_pic=find_profile_pic(),
        long_term_memory_index=long_term_memory_index,
        long_term_memory_subtitles=long_term_memory_subtitles,
        long_term_memory_entries=long_term_memory_entries,
        voice_file=voice_file,
        voice_text=voice_text,
    )


def list_available_configs() -> Dict[str, Dict[str, Optional[str]]]:
    """
    List all available agent configurations in folder format.

    Supports both direct agent folders and group-based organization:
    - agents/agent_name/ -> ungrouped agent
    - agents/group_체인소맨/agent_name/ -> agent in "체인소맨" group

    Returns:
        Dictionary mapping agent names to config info with keys:
        - "path": str (relative path to agent folder)
        - "group": Optional[str] (group name if in a group folder, None otherwise)
    """
    agents_dir = _get_agents_dir()

    if not agents_dir.exists():
        return {}

    configs = {}
    required_files = ["in_a_nutshell.md", "characteristics.md"]
    # Parent of agents_dir is the work_dir/project_root
    work_dir = agents_dir.parent

    # Check for folder-based configs
    for item in agents_dir.iterdir():
        if not item.is_dir() or item.name.startswith("."):
            continue

        # Check if this is a group folder (starts with "group_")
        if item.name.startswith("group_"):
            # Extract group name (remove "group_" prefix)
            group_name = item.name[6:]  # Remove "group_" prefix

            # Scan for agent folders inside the group folder
            for agent_item in item.iterdir():
                if agent_item.is_dir() and not agent_item.name.startswith("."):
                    # Verify it has at least one required config file
                    if any((agent_item / f).exists() for f in required_files):
                        agent_name = agent_item.name
                        relative_path = agent_item.relative_to(work_dir)
                        configs[agent_name] = {"path": str(relative_path), "group": group_name}
        else:
            # Regular agent folder (not in a group)
            if any((item / f).exists() for f in required_files):
                agent_name = item.name
                relative_path = item.relative_to(work_dir)
                configs[agent_name] = {"path": str(relative_path), "group": None}

    return configs
