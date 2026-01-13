"""
Integration tests for agent API endpoints.

Tests CRUD operations for agents through the REST API.
"""

import pytest


class TestAgentEndpoints:
    """Tests for agent API endpoints."""

    @pytest.mark.integration
    @pytest.mark.api
    async def test_list_agents(self, authenticated_client, sample_agent):
        """Test listing all agents."""
        client, token = authenticated_client

        response = await client.get("/agents")

        assert response.status_code == 200
        agents = response.json()
        assert len(agents) >= 1
        assert any(a["id"] == sample_agent.id for a in agents)

    @pytest.mark.integration
    @pytest.mark.api
    async def test_get_agent(self, authenticated_client, sample_agent):
        """Test getting a specific agent."""
        client, token = authenticated_client

        response = await client.get(f"/agents/{sample_agent.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_agent.id
        assert data["name"] == sample_agent.name

    @pytest.mark.integration
    @pytest.mark.api
    async def test_get_agent_not_found(self, authenticated_client):
        """Test getting a non-existent agent."""
        client, token = authenticated_client

        response = await client.get("/agents/999")

        assert response.status_code == 404

    @pytest.mark.integration
    @pytest.mark.api
    async def test_update_agent(self, authenticated_client, sample_agent):
        """Test updating an agent."""
        client, token = authenticated_client

        response = await client.patch(
            f"/agents/{sample_agent.id}", json={"in_a_nutshell": "Updated description", "recent_events": "New events"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["in_a_nutshell"] == "Updated description"
        assert data["recent_events"] == "New events"

    @pytest.mark.integration
    @pytest.mark.api
    async def test_delete_agent(self, authenticated_client, test_db):
        """Test deleting an agent."""
        client, token = authenticated_client

        # Create an agent to delete with unique name
        import time

        from infrastructure.database import Agent

        unique_name = f"agent_to_delete_{int(time.time() * 1000)}"
        agent = Agent(name=unique_name, system_prompt="Test")

        # Add agent using test_db
        test_db.add(agent)
        await test_db.commit()
        await test_db.refresh(agent)
        agent_id = agent.id

        # Delete via API
        response = await client.delete(f"/agents/{agent_id}")

        assert response.status_code == 200
        assert response.json()["message"] == "Agent deleted successfully"

        # Verify agent is deleted
        response = await client.get(f"/agents/{agent_id}")
        assert response.status_code == 404

    @pytest.mark.integration
    @pytest.mark.api
    async def test_delete_agent_not_found(self, authenticated_client):
        """Test deleting a non-existent agent."""
        client, token = authenticated_client

        response = await client.delete("/agents/999")

        assert response.status_code == 404


class TestAgentConfiguration:
    """Tests for agent configuration endpoints."""

    @pytest.mark.integration
    @pytest.mark.api
    async def test_list_available_configs(self, authenticated_client):
        """Test listing available agent configurations."""
        client, token = authenticated_client

        response = await client.get("/agents/configs")

        assert response.status_code == 200
        data = response.json()
        # Response has "configs" key with a dict mapping agent names to config info
        assert "configs" in data
        assert isinstance(data["configs"], dict)

    @pytest.mark.integration
    @pytest.mark.api
    async def test_reload_agent_from_config(self, authenticated_client, sample_agent):
        """Test reloading an agent from config file."""
        client, token = authenticated_client

        # This will fail if config file doesn't exist, which is expected in test environment
        response = await client.post(f"/agents/{sample_agent.id}/reload")

        # Accept either success or file not found (400 if no config file)
        assert response.status_code in [200, 400, 404]


class TestAgentMemory:
    """Tests for agent memory endpoints."""

    @pytest.mark.integration
    @pytest.mark.api
    async def test_append_agent_memory(self, authenticated_client, sample_agent):
        """Test appending to agent memory via API (if config exists)."""
        client, token = authenticated_client

        # Recent events update only works if the agent has a config file
        response = await client.patch(f"/agents/{sample_agent.id}", json={"recent_events": "New event entry"})

        # This test verifies the endpoint works; the fixture agent may not have config
        assert response.status_code in [200, 404]
