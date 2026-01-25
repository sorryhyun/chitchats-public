"""
Agent configuration data structure.

Groups agent configuration fields for clean parameter passing.
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class AgentConfigData:
    """
    Agent configuration fields grouped together.

    This dataclass groups the agent configuration fields that are
    stored in the database and passed around in business logic.

    Attributes:
        config_file: Path to agent config folder (e.g., "agents/group_장송의프리렌/프리렌")
        in_a_nutshell: Brief identity summary
        characteristics: Personality traits and behaviors
        recent_events: Short-term recent context
        profile_pic: Optional profile picture filename
        long_term_memory_index: Dict mapping memory subtitles to their full content
        long_term_memory_subtitles: List of available memory subtitles (for context injection)
        voice_file: Optional path to voice sample WAV file for TTS cloning
        voice_text: Optional transcript of the voice sample
    """

    config_file: Optional[str] = None
    in_a_nutshell: Optional[str] = None
    characteristics: Optional[str] = None
    recent_events: Optional[str] = None
    profile_pic: Optional[str] = None
    long_term_memory_index: Optional[Dict[str, str]] = None
    long_term_memory_subtitles: Optional[str] = None
    voice_file: Optional[str] = None
    voice_text: Optional[str] = None

    def has_content(self) -> bool:
        """
        Check if any configuration field has content.

        Returns:
            True if at least one field is non-empty, False otherwise
        """
        return any([self.in_a_nutshell, self.characteristics, self.recent_events])

    @classmethod
    def from_dict(cls, data: dict) -> "AgentConfigData":
        """
        Create AgentConfigData from a dictionary.

        Args:
            data: Dictionary with config keys

        Returns:
            AgentConfigData instance
        """
        return cls(
            config_file=data.get("config_file"),
            in_a_nutshell=data.get("in_a_nutshell"),
            characteristics=data.get("characteristics"),
            recent_events=data.get("recent_events"),
            profile_pic=data.get("profile_pic"),
            long_term_memory_index=data.get("long_term_memory_index"),
            long_term_memory_subtitles=data.get("long_term_memory_subtitles"),
            voice_file=data.get("voice_file"),
            voice_text=data.get("voice_text"),
        )
