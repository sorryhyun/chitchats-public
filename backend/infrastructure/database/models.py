from datetime import datetime

from database import Base
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Table, Text
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
    is_paused = Column(Boolean, default=False)  # Whether room is paused
    is_finished = Column(Boolean, default=False)  # Whether all agents have skipped (conversation ended)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_activity_at = Column(
        DateTime, default=datetime.utcnow, index=True
    )  # Track last message time (updated only when messages are created)
    last_read_at = Column(DateTime, nullable=True)  # Track when user last viewed this room
    default_provider = Column(
        String, default="claude"
    )  # Default AI provider: 'claude' or 'codex' (immutable after creation)
    default_model = Column(
        String, nullable=True
    )  # Default model override: 'claude-sonnet-4-6' etc. (None = provider default)

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
    is_critic = Column(Boolean, default=False)  # Whether agent is a critic/observer
    interrupt_every_turn = Column(Boolean, default=False)  # Whether agent always responds after any message
    priority = Column(Integer, default=0)  # Priority level (0 = normal, higher = more priority)
    transparent = Column(Boolean, default=False)  # Whether agent's messages don't trigger other agents
    final_response = Column(Boolean, default=False)  # Whether agent gets a final turn when limit is reached
    created_at = Column(DateTime, default=datetime.utcnow)

    rooms = relationship("Room", secondary=room_agents, back_populates="agents")
    messages = relationship("Message", back_populates="agent")
    room_sessions = relationship("RoomAgentSession", back_populates="agent", cascade="all, delete-orphan")

    def get_config_data(self, use_cache: bool = True):
        """
        Extract agent configuration from filesystem (primary source) or database (fallback).
        This implements the filesystem-primary architecture with in-memory caching.

        Args:
            use_cache: If True, check cache before loading from filesystem (default: True)

        Returns:
            AgentConfigData instance with this agent's configuration
        """
        from domain.agent_config import AgentConfigData

        from infrastructure.cache import agent_config_key, get_cache

        # Check cache first if enabled
        if use_cache:
            cache = get_cache()
            cache_key = agent_config_key(self.id)
            cached_config = cache.get(cache_key)
            if cached_config is not None:
                return cached_config

        # FILESYSTEM-PRIMARY: Load from filesystem first
        config_data = None
        if self.config_file:
            try:
                from core import AgentConfigService

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

        # Cache the result (TTL: 300 seconds = 5 minutes)
        if use_cache:
            cache = get_cache()
            cache_key = agent_config_key(self.id)
            cache.set(cache_key, config_data, ttl_seconds=300)

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
    anthropic_calls = Column(Text, nullable=True)  # JSON array of anthropic tool call situations
    excuse_reasons = Column(Text, nullable=True)  # JSON array of excuse tool reasons
    timestamp = Column(DateTime, default=datetime.utcnow)
    image_data = Column(Text, nullable=True)  # DEPRECATED: Use images column instead
    image_media_type = Column(String, nullable=True)  # DEPRECATED: Use images column instead
    images = Column(Text, nullable=True)  # JSON array: [{"data": "base64...", "media_type": "image/webp"}, ...]
    provider = Column(String, nullable=True)  # AI provider used: 'claude' or 'codex' (NULL = claude for legacy)

    # Indexes for frequently queried foreign keys
    __table_args__ = (
        Index("idx_message_room_id", "room_id"),
        Index("idx_message_agent_id", "agent_id"),
        Index("idx_message_room_timestamp", "room_id", "timestamp"),
    )

    room = relationship("Room", back_populates="messages")
    agent = relationship("Agent", back_populates="messages")


class RoomAgentSession(Base):
    __tablename__ = "room_agent_sessions"

    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), primary_key=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True)
    # Legacy session_id field - always populated for DB constraint compatibility
    session_id = Column(String, nullable=False)
    # Provider-specific session IDs
    claude_session_id = Column(String, nullable=True)  # Claude Agent SDK session ID
    codex_thread_id = Column(String, nullable=True)  # Codex thread ID for conversation resume
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    room = relationship("Room", back_populates="agent_sessions")
    agent = relationship("Agent", back_populates="room_sessions")

    def get_session_id(self, provider: str = "claude") -> str | None:
        """Get the session ID for a specific provider.

        Args:
            provider: Provider name ('claude' or 'codex')

        Returns:
            Session/thread ID for the provider, or None if not set
        """
        if provider == "codex":
            return self.codex_thread_id
        # Default to Claude
        return self.claude_session_id or self.session_id

    def set_session_id(self, session_id: str, provider: str = "claude") -> None:
        """Set the session ID for a specific provider.

        Args:
            session_id: The session/thread ID to store
            provider: Provider name ('claude' or 'codex')
        """
        # Always set legacy session_id field (required by DB constraint)
        self.session_id = session_id

        if provider == "codex":
            self.codex_thread_id = session_id
        else:
            self.claude_session_id = session_id


class VoiceAudio(Base):
    """Cached voice audio for messages."""

    __tablename__ = "voice_audio"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), unique=True, nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    file_path = Column(String, nullable=False)  # Path relative to sounds/ directory
    duration_ms = Column(Integer, nullable=True)  # Duration in milliseconds
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("idx_voice_audio_message_id", "message_id"),)

    message = relationship("Message")
    agent = relationship("Agent")
