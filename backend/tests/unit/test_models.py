"""
Unit tests for database models.

Tests SQLAlchemy models for Rooms, Agents, Messages,
and their relationships.
"""

from datetime import datetime

import pytest
from infrastructure.database import Agent, Message, Room, RoomAgentSession
from sqlalchemy import select


class TestRoomModel:
    """Tests for Room model."""

    @pytest.mark.unit
    async def test_create_room(self, test_db):
        """Test creating a room."""
        room = Room(name="test_room", max_interactions=10, owner_id="admin")
        test_db.add(room)
        await test_db.commit()
        await test_db.refresh(room)

        assert room.id is not None
        assert room.name == "test_room"
        assert room.max_interactions == 10
        assert room.is_paused == 0
        assert isinstance(room.created_at, datetime)

    @pytest.mark.unit
    async def test_room_default_values(self, test_db):
        """Test room default values."""
        room = Room(name="default_room", owner_id="admin")
        test_db.add(room)
        await test_db.commit()
        await test_db.refresh(room)

        assert room.max_interactions is None
        assert room.is_paused == 0
        assert room.created_at is not None

    @pytest.mark.unit
    async def test_room_unique_name_per_owner(self, test_db):
        """Room names are unique per owner, but different owners can reuse names."""
        room1 = Room(name="duplicate", owner_id="owner1")
        test_db.add(room1)
        await test_db.commit()

        room2 = Room(name="duplicate", owner_id="owner1")
        test_db.add(room2)

        with pytest.raises(Exception):  # Should raise IntegrityError for same owner
            await test_db.commit()

        await test_db.rollback()

        # Different owner should be allowed
        room3 = Room(name="duplicate", owner_id="owner2")
        test_db.add(room3)
        await test_db.commit()


class TestAgentModel:
    """Tests for Agent model."""

    @pytest.mark.unit
    async def test_create_agent(self, test_db):
        """Test creating an agent."""
        agent = Agent(
            name="test_agent",
            group="test_group",
            config_file="agents/test_agent.md",
            in_a_nutshell="Test agent",
            characteristics="Helpful",
            recent_events="Just created",
            system_prompt="You are a test agent.",
        )
        test_db.add(agent)
        await test_db.commit()
        await test_db.refresh(agent)

        assert agent.id is not None
        assert agent.name == "test_agent"
        assert agent.group == "test_group"
        assert agent.is_critic == 0
        assert isinstance(agent.created_at, datetime)

    @pytest.mark.unit
    async def test_agent_unique_name(self, test_db):
        """Test that agent names must be unique."""
        agent1 = Agent(name="duplicate", system_prompt="Test")
        test_db.add(agent1)
        await test_db.commit()

        agent2 = Agent(name="duplicate", system_prompt="Test")
        test_db.add(agent2)

        with pytest.raises(Exception):  # Should raise IntegrityError
            await test_db.commit()

    @pytest.mark.unit
    async def test_agent_critic_flag(self, test_db):
        """Test creating a critic agent."""
        agent = Agent(name="critic_agent", system_prompt="You are a critic.", is_critic=True)
        test_db.add(agent)
        await test_db.commit()
        await test_db.refresh(agent)

        assert agent.is_critic == True


class TestMessageModel:
    """Tests for Message model."""

    @pytest.mark.unit
    async def test_create_message(self, sample_room, sample_agent, test_db):
        """Test creating a message."""
        message = Message(
            room_id=sample_room.id,
            agent_id=sample_agent.id,
            content="Hello, world!",
            role="assistant",
            thinking="Test thinking",
        )
        test_db.add(message)
        await test_db.commit()
        await test_db.refresh(message)

        assert message.id is not None
        assert message.room_id == sample_room.id
        assert message.agent_id == sample_agent.id
        assert message.content == "Hello, world!"
        assert message.role == "assistant"
        assert message.thinking == "Test thinking"
        assert isinstance(message.timestamp, datetime)

    @pytest.mark.unit
    async def test_create_user_message(self, sample_room, test_db):
        """Test creating a user message (no agent)."""
        message = Message(
            room_id=sample_room.id, agent_id=None, content="User message", role="user", participant_type="user"
        )
        test_db.add(message)
        await test_db.commit()
        await test_db.refresh(message)

        assert message.agent_id is None
        assert message.role == "user"
        assert message.participant_type == "user"

    @pytest.mark.unit
    async def test_message_relationships(self, sample_room, sample_agent, test_db):
        """Test message relationships with room and agent."""
        message = Message(room_id=sample_room.id, agent_id=sample_agent.id, content="Test", role="assistant")
        test_db.add(message)
        await test_db.commit()
        await test_db.refresh(message)

        # Refresh relationships
        await test_db.refresh(message, ["room", "agent"])

        assert message.room.name == sample_room.name
        assert message.agent.name == sample_agent.name


class TestRoomAgentSession:
    """Tests for RoomAgentSession model."""

    @pytest.mark.unit
    async def test_create_session(self, sample_room, sample_agent, test_db):
        """Test creating a room-agent session."""
        session = RoomAgentSession(room_id=sample_room.id, agent_id=sample_agent.id, session_id="test_session_123")
        test_db.add(session)
        await test_db.commit()

        # Retrieve session
        result = await test_db.execute(
            select(RoomAgentSession).where(
                RoomAgentSession.room_id == sample_room.id, RoomAgentSession.agent_id == sample_agent.id
            )
        )
        retrieved_session = result.scalar_one()

        assert retrieved_session.session_id == "test_session_123"
        assert isinstance(retrieved_session.updated_at, datetime)

    @pytest.mark.unit
    async def test_session_composite_key(self, sample_room, test_db):
        """Test that room_id and agent_id form composite primary key."""
        # Create two agents
        agent1 = Agent(name="agent1", system_prompt="Test")
        agent2 = Agent(name="agent2", system_prompt="Test")
        test_db.add_all([agent1, agent2])
        await test_db.commit()
        await test_db.refresh(agent1)
        await test_db.refresh(agent2)

        # Same room, different agents - should be allowed
        session1 = RoomAgentSession(room_id=sample_room.id, agent_id=agent1.id, session_id="session1")
        session2 = RoomAgentSession(room_id=sample_room.id, agent_id=agent2.id, session_id="session2")
        test_db.add_all([session1, session2])
        await test_db.commit()

        # Should succeed
        assert session1.session_id == "session1"
        assert session2.session_id == "session2"


class TestRoomAgentRelationship:
    """Tests for many-to-many relationship between rooms and agents."""

    @pytest.mark.unit
    async def test_add_agent_to_room(self, sample_room, sample_agent, test_db):
        """Test adding an agent to a room."""
        # Refresh to load agents relationship first (async SQLAlchemy requires this)
        await test_db.refresh(sample_room, ["agents"])

        sample_room.agents.append(sample_agent)
        await test_db.commit()

        # Refresh and check
        await test_db.refresh(sample_room, ["agents"])

        assert len(sample_room.agents) == 1
        assert sample_room.agents[0].name == sample_agent.name
        assert sample_room.agents[0].id == sample_agent.id

    @pytest.mark.unit
    async def test_multiple_agents_in_room(self, sample_room, test_db):
        """Test adding multiple agents to a room."""
        agent1 = Agent(name="agent1", system_prompt="Test1")
        agent2 = Agent(name="agent2", system_prompt="Test2")
        agent3 = Agent(name="agent3", system_prompt="Test3")

        test_db.add_all([agent1, agent2, agent3])
        await test_db.commit()

        # Refresh to load the agents relationship
        await test_db.refresh(sample_room, ["agents"])
        sample_room.agents.extend([agent1, agent2, agent3])
        await test_db.commit()

        await test_db.refresh(sample_room, ["agents"])
        assert len(sample_room.agents) == 3

    @pytest.mark.unit
    async def test_agent_in_multiple_rooms(self, sample_agent, test_db):
        """Test adding an agent to multiple rooms."""
        room1 = Room(name="room1")
        room2 = Room(name="room2")
        room3 = Room(name="room3")

        test_db.add_all([room1, room2, room3])
        await test_db.commit()

        # Refresh to load the rooms relationship
        await test_db.refresh(sample_agent, ["rooms"])
        sample_agent.rooms.extend([room1, room2, room3])
        await test_db.commit()

        await test_db.refresh(sample_agent, ["rooms"])
        assert len(sample_agent.rooms) == 3

    @pytest.mark.unit
    async def test_cascade_delete_room(self, sample_room_with_agents, sample_agent, test_db):
        """Test that deleting a room removes room-agent associations."""
        room_id = sample_room_with_agents.id
        agent_id = sample_agent.id

        # Delete room
        await test_db.delete(sample_room_with_agents)
        await test_db.commit()

        # Agent should still exist
        result = await test_db.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()
        assert agent is not None

        # But room should be gone
        result = await test_db.execute(select(Room).where(Room.id == room_id))
        room = result.scalar_one_or_none()
        assert room is None
