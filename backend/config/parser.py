"""
Agent configuration parser for markdown files.

This module handles loading agent configurations from markdown files
following a specific format with standardized sections.
"""

import logging
from pathlib import Path
from typing import Dict, Optional

from core import get_settings
from domain.agent_config import AgentConfigData
from .memory_parser import parse_long_term_memory

logger = logging.getLogger("ConfigParser")

# Get settings singleton
_settings = get_settings()


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
        file_path: Path to the agent folder (can be relative to project root)

    Returns:
        AgentConfigData object or None if folder doesn't exist
    """
    import sys

    # Resolve path relative to project root if not absolute
    path = Path(file_path)
    if not path.is_absolute():
        # First try user agents directory (working directory in bundled mode)
        project_root = _settings.project_root
        path = project_root / file_path

        # In bundled mode, also check bundled agents as fallback
        if not path.exists() and getattr(sys, "frozen", False):
            bundled_path = Path(sys._MEIPASS) / file_path  # type: ignore[attr-defined]
            if bundled_path.exists():
                path = bundled_path

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
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read().strip()
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

    # Parse long-term memory file for recall tool
    memory_filename = f"{_settings.recall_memory_file}.md"
    long_term_memory_file = folder_path / memory_filename
    long_term_memory_index = None
    long_term_memory_subtitles = None

    if long_term_memory_file.exists():
        long_term_memory_index = parse_long_term_memory(long_term_memory_file)
        if long_term_memory_index:
            # Create a comma-separated list of subtitles for context injection
            long_term_memory_subtitles = ", ".join(f"'{s}'" for s in long_term_memory_index.keys())

    return AgentConfigData(
        in_a_nutshell=read_section("in_a_nutshell.md"),
        characteristics=read_section("characteristics.md"),
        recent_events=read_section("recent_events.md"),
        profile_pic=find_profile_pic(),
        long_term_memory_index=long_term_memory_index,
        long_term_memory_subtitles=long_term_memory_subtitles,
    )


def list_available_configs() -> Dict[str, Dict[str, Optional[str]]]:
    """
    List all available agent configurations in folder format.

    Supports both direct agent folders and group-based organization:
    - agents/agent_name/ -> ungrouped agent
    - agents/group_체인소맨/agent_name/ -> agent in "체인소맨" group

    In bundled mode, searches both the working directory (user agents) and
    the bundled directory (default agents) as fallback.

    Returns:
        Dictionary mapping agent names to config info with keys:
        - "path": str (relative path to agent folder)
        - "group": Optional[str] (group name if in a group folder, None otherwise)
    """
    agents_dir = _settings.agents_dir
    bundled_agents_dir = _settings.bundled_agents_dir
    project_root = _settings.project_root

    configs = {}
    required_files = ["in_a_nutshell.md", "characteristics.md"]

    def scan_agents_dir(agents_path: Path, base_path: Path):
        """Scan an agents directory and add found configs."""
        if not agents_path.exists():
            return

        for item in agents_path.iterdir():
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
                            # Skip if already found (user agents take priority)
                            if agent_name in configs:
                                continue
                            relative_path = agent_item.relative_to(base_path)
                            configs[agent_name] = {"path": str(relative_path), "group": group_name}
            else:
                # Regular agent folder (not in a group)
                if any((item / f).exists() for f in required_files):
                    agent_name = item.name
                    # Skip if already found (user agents take priority)
                    if agent_name in configs:
                        continue
                    relative_path = item.relative_to(base_path)
                    configs[agent_name] = {"path": str(relative_path), "group": None}

    # First scan user agents directory (takes priority)
    scan_agents_dir(agents_dir, project_root)

    # In bundled mode, also scan bundled agents as fallback
    if bundled_agents_dir and bundled_agents_dir.exists():
        # For bundled agents, use a special prefix to indicate bundled location
        # But we use the same relative path format for consistency
        import sys
        base_path = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else project_root  # type: ignore[attr-defined]
        scan_agents_dir(bundled_agents_dir, base_path)

    return configs
