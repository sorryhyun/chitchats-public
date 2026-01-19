"""
Integration tests for message-specific endpoints.

Tests message creation, polling, and advanced message operations.
"""

import pytest


class TestMessageCreation:
    """Tests for message creation endpoints."""

    @pytest.mark.integration
    @pytest.mark.api
    async def test_send_user_message(self, authenticated_client, sample_room):
        """Test sending a user message."""
        client, token = authenticated_client

        response = await client.post(
            f"/rooms/{sample_room.id}/messages/send",
            json={"content": "Hello from user", "role": "user", "participant_type": "user"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Hello from user"
        assert data["role"] == "user"
        assert data["participant_type"] == "user"

    @pytest.mark.integration
    @pytest.mark.api
    async def test_send_situation_builder_message(self, authenticated_client, sample_room):
        """Test sending a situation builder message."""
        client, token = authenticated_client

        response = await client.post(
            f"/rooms/{sample_room.id}/messages/send",
            json={"content": "The scene is set...", "role": "user", "participant_type": "situation_builder"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["participant_type"] == "situation_builder"

    @pytest.mark.integration
    @pytest.mark.api
    async def test_send_character_message(self, authenticated_client, sample_room):
        """Test sending a character message with custom name."""
        client, token = authenticated_client

        response = await client.post(
            f"/rooms/{sample_room.id}/messages/send",
            json={
                "content": "Hello!",
                "role": "user",
                "participant_type": "character",
                "participant_name": "Custom Character",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["participant_type"] == "character"
        assert data["participant_name"] == "Custom Character"

    @pytest.mark.integration
    @pytest.mark.api
    async def test_guest_cannot_send_to_admin_room(self, authenticated_client, guest_client):
        """Guest should not be able to post messages in admin-owned rooms."""
        admin_client, _ = authenticated_client
        guest_client_obj, _ = guest_client

        # Admin creates a room
        admin_room = await admin_client.post("/rooms", json={"name": "admin_room_forbidden"})
        room_id = admin_room.json()["id"]

        # Guest attempts to send a message
        response = await guest_client_obj.post(
            f"/rooms/{room_id}/messages/send",
            json={"content": "I should not post here", "role": "user"},
        )

        assert response.status_code == 403

    @pytest.mark.integration
    @pytest.mark.api
    async def test_send_message_to_nonexistent_room(self, authenticated_client):
        """Test sending a message to non-existent room."""
        client, token = authenticated_client

        response = await client.post("/rooms/999/messages/send", json={"content": "Hello", "role": "user"})

        assert response.status_code == 404


class TestMessagePolling:
    """Tests for message polling endpoint."""

    @pytest.mark.integration
    @pytest.mark.api
    async def test_poll_no_new_messages(self, authenticated_client, sample_room):
        """Test polling when there are no new messages."""
        client, token = authenticated_client

        response = await client.get(f"/rooms/{sample_room.id}/messages/poll", params={"since_id": 0})

        assert response.status_code == 200
        data = response.json()
        # Response is a list of messages, not a dict with keys
        assert isinstance(data, list)

    @pytest.mark.integration
    @pytest.mark.api
    async def test_poll_with_new_messages(self, authenticated_client, sample_room):
        """Test polling with new messages."""
        client, token = authenticated_client

        # Create initial message
        await client.post(f"/rooms/{sample_room.id}/messages/send", json={"content": "First", "role": "user"})

        # Get all messages to find last ID
        response = await client.get(f"/rooms/{sample_room.id}/messages")
        messages = response.json()
        last_id = messages[-1]["id"] if messages else 0

        # Create new message
        await client.post(f"/rooms/{sample_room.id}/messages/send", json={"content": "Second", "role": "user"})

        # Poll for new messages
        response = await client.get(f"/rooms/{sample_room.id}/messages/poll", params={"since_id": last_id})

        assert response.status_code == 200
        data = response.json()
        # Response is a list of messages
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["content"] == "Second"

    @pytest.mark.integration
    @pytest.mark.api
    async def test_poll_nonexistent_room(self, authenticated_client):
        """Test polling a non-existent room."""
        client, token = authenticated_client

        response = await client.get("/rooms/999/messages/poll", params={"since_id": 0})

        assert response.status_code == 404


class TestCriticMessages:
    """Tests for critic message endpoints."""

    @pytest.mark.integration
    @pytest.mark.api
    async def test_get_critic_messages(self, authenticated_client, sample_room, test_db):
        """Test getting critic messages from a room."""
        from infrastructure.database.models import Agent, Message

        # Create a critic agent
        critic = Agent(name="critic_agent", system_prompt="You are a critic.", is_critic=1)
        test_db.add(critic)
        await test_db.commit()
        await test_db.refresh(critic)

        # Create a critic message
        critic_msg = Message(
            room_id=sample_room.id, agent_id=critic.id, content="Critical analysis...", role="assistant"
        )
        test_db.add(critic_msg)
        await test_db.commit()

        # Get critic messages via API
        client, token = authenticated_client
        response = await client.get(f"/rooms/{sample_room.id}/critic-messages")

        assert response.status_code == 200
        messages = response.json()
        assert len(messages) >= 1
        assert any(m["content"] == "Critical analysis..." for m in messages)

    @pytest.mark.integration
    @pytest.mark.api
    async def test_get_critic_messages_empty(self, authenticated_client, sample_room):
        """Test getting critic messages when there are none."""
        client, token = authenticated_client

        response = await client.get(f"/rooms/{sample_room.id}/critic-messages")

        assert response.status_code == 200
        messages = response.json()
        assert isinstance(messages, list)


class TestMessageDeletion:
    """Tests for message deletion endpoints."""

    @pytest.mark.integration
    @pytest.mark.api
    async def test_delete_all_messages(self, authenticated_client, sample_room):
        """Test deleting all messages in a room."""
        client, token = authenticated_client

        # Create some messages
        for i in range(3):
            await client.post(
                f"/rooms/{sample_room.id}/messages/send", json={"content": f"Message {i}", "role": "user"}
            )

        # Delete all messages
        response = await client.delete(f"/rooms/{sample_room.id}/messages")

        assert response.status_code == 200

        # Verify messages are deleted
        response = await client.get(f"/rooms/{sample_room.id}/messages")
        messages = response.json()
        assert len(messages) == 0

    @pytest.mark.integration
    @pytest.mark.api
    async def test_delete_messages_nonexistent_room(self, authenticated_client):
        """Test deleting messages from non-existent room."""
        client, token = authenticated_client

        response = await client.delete("/rooms/999/messages")

        assert response.status_code == 404


class TestGuestMessageRestrictions:
    """Tests for guest user message restrictions."""

    @pytest.mark.integration
    @pytest.mark.api
    async def test_guest_can_send_messages(self, guest_client, test_db):
        """Test that guest can send messages to their own room."""
        from infrastructure.database.models import Room

        client, token = guest_client

        # Create a room owned by the guest
        guest_room = Room(name="guest_test_room", owner_id="guest-test")
        test_db.add(guest_room)
        await test_db.commit()
        await test_db.refresh(guest_room)

        response = await client.post(
            f"/rooms/{guest_room.id}/messages/send", json={"content": "Guest message", "role": "user"}
        )

        assert response.status_code == 200

    @pytest.mark.integration
    @pytest.mark.api
    async def test_guest_can_poll_messages(self, guest_client, test_db):
        """Test that guest can poll for messages in their own room."""
        from infrastructure.database.models import Room

        client, token = guest_client

        # Create a room owned by the guest
        guest_room = Room(name="guest_poll_room", owner_id="guest-test")
        test_db.add(guest_room)
        await test_db.commit()
        await test_db.refresh(guest_room)

        response = await client.get(f"/rooms/{guest_room.id}/messages/poll", params={"since_id": 0})

        assert response.status_code == 200

    @pytest.mark.integration
    @pytest.mark.api
    async def test_guest_cannot_delete_messages(self, guest_client, sample_room):
        """Test that guest cannot delete messages."""
        client, token = guest_client

        response = await client.delete(f"/rooms/{sample_room.id}/messages")

        assert response.status_code == 403
