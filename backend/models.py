from datetime import datetime

from database import Base
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Table, Text
from sqlalchemy.orm import relationship

# Association table for many-to-many relationship between rooms and agents
room_agents = Table(
    "room_agents",
    Base.metadata,
    Column("room_id", Integer, ForeignKey("rooms.id", ondelete="CASCADE"), primary_key=True),
    Column("agent_id", Integer, ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
    Column("joined_at", DateTime, nullable=True),  # Timestamp when agent was added to room
)


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (Index("ux_rooms_owner_name", "owner_id", "name", unique=True),)

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(String, nullable=True, index=True)
    name = Column(String, nullable=False, index=True)
    max_interactions = Column(Integer, nullable=True)  # Maximum number of agent interactions (None = unlimited)
    is_paused = Column(Integer, default=0)  # 0 = not paused, 1 = paused (SQLite uses integers for booleans)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_activity_at = Column(
        DateTime, default=datetime.utcnow, index=True
    )  # Track last message time (updated only when messages are created)
    last_read_at = Column(DateTime, nullable=True)  # Track when user last viewed this room

    agents = relationship("Agent", secondary=room_agents, back_populates="rooms")
    messages = relationship("Message", back_populates="room", cascade="all, delete-orphan")
    agent_sessions = relationship("RoomAgentSession", back_populates="room", cascade="all, delete-orphan")


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True, index=True)
    group = Column(String, nullable=True, index=True)  # Group name (e.g., "체인소맨" from "group_체인소맨" folder)
    config_file = Column(String, nullable=True)  # Path to agent config file (e.g., "agents/alice.md")
    profile_pic = Column(Text, nullable=True)  # Profile picture (base64 encoded image data)
    in_a_nutshell = Column(Text, nullable=True)  # Brief identity summary
    characteristics = Column(Text, nullable=True)  # Personality traits and behaviors
    recent_events = Column(Text, nullable=True)  # Short-term recent context
    system_prompt = Column(Text, nullable=False)  # Final combined system prompt
    is_critic = Column(Integer, default=0)  # 0 = participant, 1 = critic/observer (SQLite uses integers for booleans)
    created_at = Column(DateTime, default=datetime.utcnow)

    rooms = relationship("Room", secondary=room_agents, back_populates="agents")
    messages = relationship("Message", back_populates="agent")
    room_sessions = relationship("RoomAgentSession", back_populates="agent", cascade="all, delete-orphan")

    def get_config_data(self, use_cache: bool = True):
        """
        Extract agent configuration from filesystem (primary source) or database (fallback).
        This implements the filesystem-primary architecture with in-memory caching.

        Cache entries are invalidated when underlying config files are modified.

        Args:
            use_cache: If True, check cache before loading from filesystem (default: True)

        Returns:
            AgentConfigData instance with this agent's configuration
        """

        from core.paths import get_work_dir
        from domain.agent_config import AgentConfigData
        from utils.cache import agent_config_key, get_cache

        def _get_config_mtime() -> float:
            """Get the most recent mtime of all config files for this agent."""
            if not self.config_file:
                return 0
            config_path = get_work_dir() / self.config_file
            if not config_path.is_dir():
                return config_path.stat().st_mtime if config_path.exists() else 0
            # For folder-based configs, check all .md files
            max_mtime = 0
            for md_file in config_path.glob("*.md"):
                try:
                    max_mtime = max(max_mtime, md_file.stat().st_mtime)
                except OSError:
                    pass
            return max_mtime

        # Check cache first if enabled
        if use_cache:
            cache = get_cache()
            cache_key = agent_config_key(self.id)
            mtime_key = f"{cache_key}:mtime"
            cached_config = cache.get(cache_key)
            cached_mtime = cache.get(mtime_key)

            if cached_config is not None and cached_mtime is not None:
                # Check if files have been modified since caching
                current_mtime = _get_config_mtime()
                if current_mtime <= cached_mtime:
                    return cached_config
                # Files modified - invalidate and reload
                cache.invalidate(cache_key)
                cache.invalidate(mtime_key)

        # FILESYSTEM-PRIMARY: Load from filesystem first
        config_data = None
        if self.config_file:
            try:
                from services import AgentConfigService

                # load_agent_config now returns AgentConfigData directly
                config_data = AgentConfigService.load_agent_config(self.config_file)
            except Exception as e:
                # Log error but fallback to database
                import logging

                logging.warning(f"Failed to load config from {self.config_file}, using database cache: {e}")

        # FALLBACK: Use database values if filesystem load failed
        if config_data is None:
            config_data = AgentConfigData.from_dict(
                {
                    "config_file": self.config_file,
                    "in_a_nutshell": self.in_a_nutshell or "",
                    "characteristics": self.characteristics or "",
                    "recent_events": self.recent_events or "",
                }
            )
        else:
            # Ensure config_file is set even when loaded from filesystem
            config_data.config_file = self.config_file

        # Cache the result with mtime tracking (TTL: 300 seconds = 5 minutes)
        if use_cache:
            cache = get_cache()
            cache_key = agent_config_key(self.id)
            mtime_key = f"{cache_key}:mtime"
            cache.set(cache_key, config_data, ttl_seconds=300)
            cache.set(mtime_key, _get_config_mtime(), ttl_seconds=300)

        return config_data


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    content = Column(Text, nullable=False)
    role = Column(String, nullable=False)  # 'user' or 'assistant'
    participant_type = Column(
        String, nullable=True
    )  # For user messages: 'user', 'situation_builder', 'character'; NULL for agents
    participant_name = Column(String, nullable=True)  # Custom name for 'character' mode
    thinking = Column(Text, nullable=True)  # Agent's thinking process (for assistant messages)
    image_data = Column(Text, nullable=True)  # JSON string of ImageAttachment (base64 image + media_type)
    timestamp = Column(DateTime, default=datetime.utcnow)

    # Indexes for frequently queried foreign keys
    __table_args__ = (
        Index("idx_message_room_id", "room_id"),
        Index("idx_message_agent_id", "agent_id"),
        Index("idx_message_room_timestamp", "room_id", "timestamp"),
        Index("idx_message_room_agent", "room_id", "agent_id"),  # Composite for efficient agent message queries
    )

    room = relationship("Room", back_populates="messages")
    agent = relationship("Agent", back_populates="messages")


class RoomAgentSession(Base):
    __tablename__ = "room_agent_sessions"

    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), primary_key=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True)
    session_id = Column(String, nullable=False)  # Claude Agent SDK session ID for this room-agent pair
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    room = relationship("Room", back_populates="agent_sessions")
    agent = relationship("Agent", back_populates="room_sessions")
