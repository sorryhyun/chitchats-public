"""
Integration tests for authentication API endpoints.

Tests login, JWT token handling, and role-based access control.
"""

import pytest
from httpx import AsyncClient


class TestAuthEndpoints:
    """Tests for authentication endpoints."""

    @pytest.mark.integration
    @pytest.mark.api
    @pytest.mark.auth
    async def test_login_success(self, client: AsyncClient, mock_env_vars):
        """Test successful login."""
        response = await client.post("/auth/login", json={"password": mock_env_vars["test_password"]})

        assert response.status_code == 200
        data = response.json()
        assert "api_key" in data
        assert data["success"] is True
        assert data["role"] == "admin"

    @pytest.mark.integration
    @pytest.mark.api
    @pytest.mark.auth
    async def test_login_failure(self, client: AsyncClient, mock_env_vars):
        """Test login with wrong password."""
        response = await client.post("/auth/login", json={"password": "wrong_password"})

        assert response.status_code == 401
        assert "Invalid password" in response.json()["detail"]

    @pytest.mark.integration
    @pytest.mark.api
    @pytest.mark.auth
    async def test_health_check_public(self, client: AsyncClient):
        """Test health check endpoint is publicly accessible."""
        response = await client.get("/auth/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    @pytest.mark.integration
    @pytest.mark.api
    @pytest.mark.auth
    async def test_protected_endpoint_without_token(self, client: AsyncClient):
        """Test accessing protected endpoint without authentication."""
        # Remove auth middleware for this test
        # The client fixture doesn't have auth, so we need to use a different approach

        # Create a new client without auth bypass
        from httpx import ASGITransport
        from main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/rooms")

            assert response.status_code == 401
            assert "Invalid or missing authentication token" in response.json()["detail"]

    @pytest.mark.integration
    @pytest.mark.api
    @pytest.mark.auth
    async def test_protected_endpoint_with_token(self, authenticated_client):
        """Test accessing protected endpoint with valid token."""
        client, token = authenticated_client

        response = await client.get("/rooms")

        # Should be successful (even if empty)
        assert response.status_code == 200


class TestRoleBasedAccess:
    """Tests for role-based access control."""

    @pytest.mark.integration
    @pytest.mark.api
    @pytest.mark.auth
    async def test_admin_can_create_room(self, authenticated_client):
        """Test that admin can create rooms."""
        client, token = authenticated_client

        response = await client.post("/rooms", json={"name": "admin_room"})

        assert response.status_code == 200
        assert response.json()["name"] == "admin_room"

    @pytest.mark.integration
    @pytest.mark.api
    @pytest.mark.auth
    async def test_guest_can_create_room(self, guest_client):
        """Test that guest can create rooms."""
        client, token = guest_client

        response = await client.post("/rooms", json={"name": "guest_room"})

        # Guests can create rooms - they just can't delete them
        assert response.status_code == 200
        assert response.json()["name"] == "guest: guest_room"

    @pytest.mark.integration
    @pytest.mark.api
    @pytest.mark.auth
    async def test_guest_can_view_rooms(self, guest_client):
        """Test that guest can view rooms."""
        client, token = guest_client

        response = await client.get("/rooms")

        assert response.status_code == 200

    @pytest.mark.integration
    @pytest.mark.api
    @pytest.mark.auth
    async def test_guest_cannot_access_admin_rooms(self, authenticated_client, guest_client):
        """Guests should only see their own rooms and be blocked from admin-owned rooms."""
        admin_client, _ = authenticated_client
        guest_client_obj, _ = guest_client

        # Admin creates a room
        admin_room_resp = await admin_client.post("/rooms", json={"name": "admin_only_room"})
        admin_room_id = admin_room_resp.json()["id"]

        # Guest creates their own room
        guest_room_resp = await guest_client_obj.post("/rooms", json={"name": "guest_private_room"})
        guest_room_id = guest_room_resp.json()["id"]

        # Guest listing should only include their own room
        guest_rooms = await guest_client_obj.get("/rooms")
        assert guest_rooms.status_code == 200
        room_ids = {room["id"] for room in guest_rooms.json()}
        assert guest_room_id in room_ids
        assert admin_room_id not in room_ids

        # Guest cannot fetch admin room details
        forbidden_resp = await guest_client_obj.get(f"/rooms/{admin_room_id}")
        assert forbidden_resp.status_code == 403

    @pytest.mark.integration
    @pytest.mark.api
    @pytest.mark.auth
    async def test_guest_cannot_delete_room(self, guest_client, sample_room, test_db):
        """Test that guest cannot delete rooms."""
        client, token = guest_client

        response = await client.delete(f"/rooms/{sample_room.id}")

        assert response.status_code == 403
        assert "admin privileges" in response.json()["detail"]
