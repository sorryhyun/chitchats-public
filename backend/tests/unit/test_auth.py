"""
Unit tests for authentication functions.

Tests JWT token generation, validation, password hashing,
and role-based authentication.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import pytest
from core.auth import (
    generate_jwt_token,
    get_jwt_secret,
    get_role_from_token,
    get_user_id_from_token,
    validate_api_key,
    validate_jwt_token,
    validate_password_with_role,
)


class TestPasswordValidation:
    """Tests for password validation functions."""

    @pytest.mark.auth
    def test_validate_api_key_correct(self, mock_env_vars):
        """Test validating correct password."""
        result = validate_api_key(mock_env_vars["test_password"])
        assert result is True

    @pytest.mark.auth
    def test_validate_api_key_incorrect(self, mock_env_vars):
        """Test validating incorrect password."""
        result = validate_api_key("wrong_password")
        assert result is False

    @pytest.mark.auth
    def test_validate_api_key_empty(self, mock_env_vars):
        """Test validating empty password."""
        result = validate_api_key("")
        assert result is False

    @pytest.mark.auth
    def test_validate_password_with_role_admin(self, mock_env_vars):
        """Test validating admin password returns admin role."""
        role = validate_password_with_role(mock_env_vars["test_password"])
        assert role == "admin"

    @pytest.mark.auth
    def test_validate_password_with_role_invalid(self, mock_env_vars):
        """Test validating invalid password returns None."""
        role = validate_password_with_role("wrong_password")
        assert role is None

    @pytest.mark.auth
    def test_validate_password_with_role_guest(self, monkeypatch):
        """Test validating guest password returns guest role."""
        # Set up admin and guest passwords
        # Hash of "test_password" (same as mock_env_vars fixture)
        admin_hash = "$2b$12$H0fCIM9buSuQsCFErTRi0Omz//QVZxCKJW5Dapi2u3ealuUFzvF9O"
        guest_hash = bcrypt.hashpw("guest_password".encode(), bcrypt.gensalt()).decode()

        monkeypatch.setenv("API_KEY_HASH", admin_hash)
        monkeypatch.setenv("GUEST_PASSWORD_HASH", guest_hash)
        monkeypatch.setenv("ENABLE_GUEST_LOGIN", "true")

        # Test guest password
        role = validate_password_with_role("guest_password")
        assert role == "guest"

        # Test admin password still works
        role = validate_password_with_role("test_password")
        assert role == "admin"


class TestJWTTokens:
    """Tests for JWT token generation and validation."""

    @pytest.mark.auth
    def test_generate_jwt_token_default(self, mock_env_vars):
        """Test generating JWT token with default parameters."""
        token = generate_jwt_token()
        assert isinstance(token, str)
        assert len(token) > 0

    @pytest.mark.auth
    def test_generate_jwt_token_admin(self, mock_env_vars):
        """Test generating JWT token for admin role."""
        token = generate_jwt_token(role="admin")
        payload = validate_jwt_token(token)

        assert payload is not None
        assert payload["role"] == "admin"
        assert payload["type"] == "access_token"

    @pytest.mark.auth
    def test_generate_jwt_token_guest(self, mock_env_vars):
        """Test generating JWT token for guest role."""
        token = generate_jwt_token(role="guest", user_id="guest-123")
        payload = validate_jwt_token(token)

        assert payload is not None
        assert payload["role"] == "guest"
        assert payload["type"] == "access_token"
        assert payload["user_id"] == "guest-123"

    @pytest.mark.auth
    def test_get_user_id_from_token(self, mock_env_vars):
        """Ensure user_id is extracted from tokens (with fallback for legacy)."""
        token = generate_jwt_token(role="guest", user_id="guest-abc")
        assert get_user_id_from_token(token) == "guest-abc"

        # Legacy token without user_id should fallback to role
        legacy_payload = {
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iat": datetime.utcnow(),
            "type": "access_token",
            "role": "guest",
        }
        secret = get_jwt_secret()
        legacy_token = jwt.encode(legacy_payload, secret, algorithm="HS256")
        assert get_user_id_from_token(legacy_token) == "guest"

    @pytest.mark.auth
    def test_generate_jwt_token_expiration(self, mock_env_vars):
        """Test JWT token expiration time."""
        token = generate_jwt_token(expiration_hours=1)
        payload = validate_jwt_token(token)

        assert payload is not None

        exp_time = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        iat_time = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)

        # Check expiration is approximately 1 hour from issuance
        time_diff = exp_time - iat_time
        assert 3590 <= time_diff.total_seconds() <= 3610  # Allow small variance

    @pytest.mark.auth
    def test_validate_jwt_token_valid(self, mock_env_vars):
        """Test validating a valid JWT token."""
        token = generate_jwt_token(role="admin")
        payload = validate_jwt_token(token)

        assert payload is not None
        assert "exp" in payload
        assert "iat" in payload
        assert "role" in payload
        assert "type" in payload

    @pytest.mark.auth
    def test_validate_jwt_token_invalid(self, mock_env_vars):
        """Test validating an invalid JWT token."""
        invalid_token = "invalid.token.here"
        payload = validate_jwt_token(invalid_token)

        assert payload is None

    @pytest.mark.auth
    def test_validate_jwt_token_expired(self, mock_env_vars):
        """Test validating an expired JWT token."""
        # Generate token that expires immediately
        secret = get_jwt_secret()
        payload = {
            "exp": datetime.utcnow() - timedelta(hours=1),  # Already expired
            "iat": datetime.utcnow() - timedelta(hours=2),
            "type": "access_token",
            "role": "admin",
        }
        expired_token = jwt.encode(payload, secret, algorithm="HS256")

        result = validate_jwt_token(expired_token)
        assert result is None

    @pytest.mark.auth
    def test_get_role_from_token_admin(self, mock_env_vars):
        """Test extracting admin role from token."""
        token = generate_jwt_token(role="admin")
        role = get_role_from_token(token)

        assert role == "admin"

    @pytest.mark.auth
    def test_get_role_from_token_guest(self, mock_env_vars):
        """Test extracting guest role from token."""
        token = generate_jwt_token(role="guest")
        role = get_role_from_token(token)

        assert role == "guest"

    @pytest.mark.auth
    def test_get_role_from_token_legacy(self, mock_env_vars):
        """Test extracting role from legacy token without role field."""
        # Create token without role field (legacy format)
        secret = get_jwt_secret()
        payload = {
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iat": datetime.utcnow(),
            "type": "access_token",
            # No role field
        }
        legacy_token = jwt.encode(payload, secret, algorithm="HS256")

        role = get_role_from_token(legacy_token)
        # Should default to admin for backward compatibility
        assert role == "admin"
