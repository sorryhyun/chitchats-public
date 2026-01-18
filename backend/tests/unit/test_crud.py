"""
Unit tests for CRUD operations.

Tests database operations for Rooms, Agents, Messages,
and their relationships.
"""

import crud
import pytest
import schemas
from infrastructure.database import Agent


class TestRoomCRUD:
    """Tests for Room CRUD operations."""

    @pytest.mark.crud
    async def test_create_room(self, test_db):
        """Test creating a room."""
        room_data = schemas.RoomCreate(name="test_room", max_interactions=10)
        room = await crud.create_room(test_db, room_data, owner_id="admin")

        assert room.id is not None
        assert room.name == "test_room"
        assert room.max_interactions == 10

    @pytest.mark.crud
    async def test_get_rooms(self, test_db):
        """Test getting all rooms."""
        # Create multiple rooms
        await crud.create_room(test_db, schemas.RoomCreate(name="room1"), owner_id="admin")
        await crud.create_room(test_db, schemas.RoomCreate(name="room2"), owner_id="admin")
        await crud.create_room(test_db, schemas.RoomCreate(name="room3"), owner_id="admin")

        rooms = await crud.get_rooms(test_db)
        assert len(rooms) == 3
        assert {r.name for r in rooms} == {"room1", "room2", "room3"}

    @pytest.mark.crud
    async def test_get_room(self, sample_room, test_db):
        """Test getting a specific room."""
        room = await crud.get_room(test_db, sample_room.id)

        assert room is not None
        assert room.id == sample_room.id
        assert room.name == sample_room.name

    @pytest.mark.crud
    async def test_get_room_not_found(self, test_db):
        """Test getting a non-existent room."""
        room = await crud.get_room(test_db, 999)
        assert room is None

    @pytest.mark.crud
    async def test_update_room(self, sample_room, test_db):
        """Test updating a room."""
        update_data = schemas.RoomUpdate(max_interactions=20, is_paused=True)
        updated_room = await crud.update_room(test_db, sample_room.id, update_data)

        assert updated_room.max_interactions == 20
        assert updated_room.is_paused == True

    @pytest.mark.crud
    async def test_delete_room(self, sample_room, test_db):
        """Test deleting a room."""
        result = await crud.delete_room(test_db, sample_room.id)
        assert result is True

        # Verify room is deleted
        room = await crud.get_room(test_db, sample_room.id)
        assert room is None

    @pytest.mark.crud
    async def test_delete_room_not_found(self, test_db):
        """Test deleting a non-existent room."""
        result = await crud.delete_room(test_db, 999)
        assert result is False


class TestAgentCRUD:
    """Tests for Agent CRUD operations."""

    @pytest.mark.crud
    async def test_create_agent(self, test_db):
        """Test creating an agent."""
        agent_data = schemas.AgentCreate(
            name="new_agent",
            group="test_group",
            in_a_nutshell="Test agent",
            characteristics="Helpful",
            recent_events="Just created",
        )
        agent = await crud.create_agent(test_db, agent_data)

        assert agent.id is not None
        assert agent.name == "new_agent"
        assert agent.group == "test_group"
        assert agent.system_prompt is not None  # Should be generated

    @pytest.mark.crud
    async def test_get_all_agents(self, test_db):
        """Test getting all agents."""
        # Create multiple agents
        for i in range(3):
            agent_data = schemas.AgentCreate(name=f"agent_{i}", in_a_nutshell=f"Agent {i}")
            await crud.create_agent(test_db, agent_data)

        agents = await crud.get_all_agents(test_db)
        assert len(agents) == 3

    @pytest.mark.crud
    async def test_get_agent(self, sample_agent, test_db):
        """Test getting a specific agent."""
        agent = await crud.get_agent(test_db, sample_agent.id)

        assert agent is not None
        assert agent.id == sample_agent.id
        assert agent.name == sample_agent.name

    @pytest.mark.crud
    async def test_get_agent_not_found(self, test_db):
        """Test getting a non-existent agent."""
        agent = await crud.get_agent(test_db, 999)
        assert agent is None

    @pytest.mark.crud
    async def test_delete_agent(self, sample_agent, test_db):
        """Test deleting an agent."""
        result = await crud.delete_agent(test_db, sample_agent.id)
        assert result is True

        # Verify agent is deleted
        agent = await crud.get_agent(test_db, sample_agent.id)
        assert agent is None

    @pytest.mark.crud
    async def test_update_agent(self, sample_agent, test_db):
        """Test updating an agent."""
        update_data = schemas.AgentUpdate(in_a_nutshell="Updated nutshell", recent_events="New events")
        updated_agent = await crud.update_agent(test_db, sample_agent.id, update_data)

        assert updated_agent.in_a_nutshell == "Updated nutshell"
        assert updated_agent.recent_events == "New events"
        # Other fields should remain unchanged
        assert updated_agent.name == sample_agent.name


class TestRoomAgentRelationshipCRUD:
    """Tests for Room-Agent relationship CRUD operations."""

    @pytest.mark.crud
    async def test_add_agent_to_room(self, sample_room, sample_agent, test_db):
        """Test adding an agent to a room."""
        await crud.add_agent_to_room(test_db, sample_room.id, sample_agent.id)

        # Verify relationship
        agents = await crud.get_agents(test_db, sample_room.id)
        assert len(agents) == 1
        assert agents[0].id == sample_agent.id

    @pytest.mark.crud
    async def test_remove_agent_from_room(self, sample_room_with_agents, sample_agent, test_db):
        """Test removing an agent from a room."""
        # Verify agent is in room
        agents = await crud.get_agents(test_db, sample_room_with_agents.id)
        assert len(agents) == 1

        # Remove agent
        result = await crud.remove_agent_from_room(test_db, sample_room_with_agents.id, sample_agent.id)
        assert result is True

        # Verify agent is removed
        agents = await crud.get_agents(test_db, sample_room_with_agents.id)
        assert len(agents) == 0

    @pytest.mark.crud
    async def test_get_agents_in_room(self, sample_room, test_db):
        """Test getting agents in a room."""
        # Create multiple agents
        agents = []
        for i in range(3):
            agent_data = schemas.AgentCreate(name=f"agent_{i}", in_a_nutshell=f"Agent {i}")
            agent = await crud.create_agent(test_db, agent_data)
            agents.append(agent)

        # Add agents to room
        for agent in agents:
            await crud.add_agent_to_room(test_db, sample_room.id, agent.id)

        # Get agents
        room_agents = await crud.get_agents(test_db, sample_room.id)
        assert len(room_agents) == 3
        assert {a.id for a in room_agents} == {a.id for a in agents}


class TestMessageCRUD:
    """Tests for Message CRUD operations."""

    @pytest.mark.crud
    async def test_create_message(self, sample_room, sample_agent, test_db):
        """Test creating a message."""
        message_data = schemas.MessageCreate(
            content="Test message", role="assistant", agent_id=sample_agent.id, thinking="Test thinking"
        )
        message = await crud.create_message(test_db, sample_room.id, message_data)

        assert message.id is not None
        assert message.room_id == sample_room.id
        assert message.agent_id == sample_agent.id
        assert message.content == "Test message"
        assert message.thinking == "Test thinking"

    @pytest.mark.crud
    async def test_create_user_message(self, sample_room, test_db):
        """Test creating a user message."""
        message_data = schemas.MessageCreate(content="User message", role="user", participant_type="user")
        message = await crud.create_message(test_db, sample_room.id, message_data)

        assert message.agent_id is None
        assert message.role == "user"
        assert message.participant_type == "user"

    @pytest.mark.crud
    async def test_get_messages(self, sample_room, sample_agent, test_db):
        """Test getting all messages in a room."""
        # Create multiple messages
        for i in range(3):
            message_data = schemas.MessageCreate(content=f"Message {i}", role="assistant", agent_id=sample_agent.id)
            await crud.create_message(test_db, sample_room.id, message_data)

        messages = await crud.get_messages(test_db, sample_room.id)
        assert len(messages) == 3

    @pytest.mark.crud
    async def test_get_messages_since(self, sample_room, sample_agent, test_db):
        """Test getting messages since a specific message ID."""
        # Create messages
        messages = []
        for i in range(5):
            message_data = schemas.MessageCreate(content=f"Message {i}", role="assistant", agent_id=sample_agent.id)
            msg = await crud.create_message(test_db, sample_room.id, message_data)
            messages.append(msg)

        # Get messages since message 2
        new_messages = await crud.get_messages_since(test_db, sample_room.id, messages[2].id)

        # Should get messages 3 and 4 (after message 2)
        assert len(new_messages) == 2
        assert new_messages[0].id == messages[3].id
        assert new_messages[1].id == messages[4].id

    @pytest.mark.crud
    async def test_delete_room_messages(self, sample_room, sample_agent, test_db):
        """Test deleting all messages in a room."""
        # Create messages
        for i in range(3):
            message_data = schemas.MessageCreate(content=f"Message {i}", role="assistant", agent_id=sample_agent.id)
            await crud.create_message(test_db, sample_room.id, message_data)

        # Delete messages
        result = await crud.delete_room_messages(test_db, sample_room.id)
        assert result is True

        # Verify messages are deleted
        messages = await crud.get_messages(test_db, sample_room.id)
        assert len(messages) == 0


class TestRoomAgentSessionCRUD:
    """Tests for RoomAgentSession CRUD operations."""

    @pytest.mark.crud
    async def test_get_or_create_session_new(self, sample_room, sample_agent, test_db):
        """Test creating a new room-agent session."""
        session = await crud.get_room_agent_session(test_db, sample_room.id, sample_agent.id)

        # First time should create a new session
        assert session is None

    @pytest.mark.crud
    async def test_update_room_agent_session(self, sample_room, sample_agent, test_db):
        """Test updating a room-agent session."""
        session_id = "test_session_123"

        await crud.update_room_agent_session(test_db, sample_room.id, sample_agent.id, session_id)

        # Verify session was created
        returned_session_id = await crud.get_room_agent_session(test_db, sample_room.id, sample_agent.id)

        assert returned_session_id is not None
        assert returned_session_id == session_id

    @pytest.mark.crud
    async def test_update_existing_session(self, sample_room, sample_agent, test_db):
        """Test updating an existing session."""
        # Create initial session
        await crud.update_room_agent_session(test_db, sample_room.id, sample_agent.id, "session_1")

        # Update with new session ID
        await crud.update_room_agent_session(test_db, sample_room.id, sample_agent.id, "session_2")

        # Verify session was updated
        returned_session_id = await crud.get_room_agent_session(test_db, sample_room.id, sample_agent.id)

        assert returned_session_id == "session_2"


class TestMemoryOperations:
    """Tests for agent memory operations."""

    @pytest.mark.crud
    async def test_append_agent_memory(self, temp_agent_config, test_db, monkeypatch):
        """Test appending to agent memory."""
        # Mock get_project_root to return temp_agent_config parent
        from config import AgentConfigIO

        monkeypatch.setattr(AgentConfigIO, "get_project_root", lambda: temp_agent_config.parent.parent)

        # Create agent with config file (relative path from mocked project root)
        # Use actual directory name from fixture (may be "agents0", "agents1", etc. in pytest)
        relative_config_path = f"{temp_agent_config.parent.name}/test_agent"
        agent = Agent(
            name="test_agent",
            group="test_group",
            config_file=relative_config_path,
            in_a_nutshell="Test agent",
            characteristics="Test characteristics",
            recent_events="Initial events",
            system_prompt="Test prompt",
            is_critic=0,
        )
        test_db.add(agent)
        await test_db.commit()
        await test_db.refresh(agent)

        # Append new memory
        new_memory = "New memory entry"
        result = await crud.append_agent_memory(test_db, agent.id, new_memory)

        # Verify function returns agent
        assert result is not None
        assert result.id == agent.id

        # Verify recent_events file was updated
        recent_events_file = temp_agent_config / "recent_events.md"
        content = recent_events_file.read_text()
        assert "New memory entry" in content

    @pytest.mark.crud
    async def test_append_agent_memory_empty(self, temp_agent_config, test_db, monkeypatch):
        """Test appending to empty memory."""
        # Mock get_project_root to return temp_agent_config parent
        from config import AgentConfigIO

        monkeypatch.setattr(AgentConfigIO, "get_project_root", lambda: temp_agent_config.parent.parent)

        # Create agent with config file (relative path from mocked project root)
        # Use actual directory name from fixture (may be "agents0", "agents1", etc. in pytest)
        relative_config_path = f"{temp_agent_config.parent.name}/test_agent"
        agent = Agent(
            name="test_agent",
            group="test_group",
            config_file=relative_config_path,
            in_a_nutshell="Test agent",
            characteristics="Test characteristics",
            recent_events="",
            system_prompt="Test prompt",
            is_critic=0,
        )
        test_db.add(agent)
        await test_db.commit()
        await test_db.refresh(agent)

        # Clear the recent events file
        recent_events_file = temp_agent_config / "recent_events.md"
        recent_events_file.write_text("")

        # Append new memory
        new_memory = "First memory entry"
        result = await crud.append_agent_memory(test_db, agent.id, new_memory)

        # Verify function returns agent
        assert result is not None

        # Verify recent_events file was updated
        content = recent_events_file.read_text()
        assert "First memory entry" in content


class TestDirectRoomOperations:
    """Tests for direct room operations."""

    @pytest.mark.crud
    async def test_get_or_create_direct_room_new(self, test_db):
        """Test creating a new direct room."""
        from infrastructure.database import Agent

        # Create an agent
        agent = Agent(name="test_agent", system_prompt="Test prompt")
        test_db.add(agent)
        await test_db.commit()
        await test_db.refresh(agent)

        # Get or create direct room
        room = await crud.get_or_create_direct_room(test_db, agent.id, owner_id="admin")

        assert room is not None
        assert room.name == f"Direct: {agent.name}"
        # Refresh and check agents
        await test_db.refresh(room, ["agents"])
        assert len(room.agents) == 1
        assert room.agents[0].id == agent.id

    @pytest.mark.crud
    async def test_get_or_create_direct_room_existing(self, test_db):
        """Test getting an existing direct room."""
        from infrastructure.database import Agent

        # Create an agent
        agent = Agent(name="test_agent", system_prompt="Test prompt")
        test_db.add(agent)
        await test_db.commit()
        await test_db.refresh(agent)

        # Create first time
        room1 = await crud.get_or_create_direct_room(test_db, agent.id, owner_id="admin")

        # Get second time with same agent
        room2 = await crud.get_or_create_direct_room(test_db, agent.id, owner_id="admin")

        # Should get the same room
        assert room1.id == room2.id


class TestCriticMessageOperations:
    """Tests for critic message operations."""

    @pytest.mark.crud
    async def test_get_critic_messages(self, sample_room, test_db):
        """Test getting critic messages."""
        from infrastructure.database import Agent, Message

        # Create critic agent
        critic = Agent(name="critic", system_prompt="Test", is_critic=1)
        test_db.add(critic)
        await test_db.commit()
        await test_db.refresh(critic)

        # Create critic message
        msg = Message(room_id=sample_room.id, agent_id=critic.id, content="Critic message", role="assistant")
        test_db.add(msg)
        await test_db.commit()

        # Get critic messages
        critic_messages = await crud.get_critic_messages(test_db, sample_room.id)

        assert len(critic_messages) >= 1
        assert any(m.content == "Critic message" for m in critic_messages)

    @pytest.mark.crud
    async def test_get_critic_messages_empty(self, sample_room, test_db):
        """Test getting critic messages when there are none."""
        critic_messages = await crud.get_critic_messages(test_db, sample_room.id)

        assert len(critic_messages) == 0


class TestReloadAgentFromConfig:
    """Tests for reloading agent from config file."""

    @pytest.mark.crud
    async def test_reload_agent_from_config(self, sample_agent, test_db, temp_agent_config):
        """Test reloading agent configuration from file."""
        # Set agent config file
        sample_agent.config_file = str(temp_agent_config)
        await test_db.commit()

        # Reload from config
        reloaded = await crud.reload_agent_from_config(test_db, sample_agent.id)

        assert reloaded is not None
        assert reloaded.in_a_nutshell == "Test agent nutshell"
        assert reloaded.characteristics == "Test characteristics"

    @pytest.mark.crud
    async def test_reload_agent_nonexistent_config(self, sample_agent, test_db):
        """Test reloading agent with non-existent config."""
        sample_agent.config_file = "nonexistent/path"
        await test_db.commit()

        # Should raise ValueError for non-existent config
        with pytest.raises(ValueError, match="Failed to load config"):
            await crud.reload_agent_from_config(test_db, sample_agent.id)
