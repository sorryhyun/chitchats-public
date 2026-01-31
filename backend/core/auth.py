"""
Authentication middleware and utilities for JWT token-based authentication.

SECURITY NOTES:
- Passwords are hashed using bcrypt before comparison
- JWT tokens are issued upon successful login
- Tokens are sent via X-API-Key header for all endpoints
- Always use HTTPS in production to protect credentials in transit
- Rate limiting via slowapi to prevent brute force attacks
"""

import logging
import os
import secrets
import sys
from datetime import datetime, timedelta

import bcrypt
import jwt
from fastapi import HTTPException, Request, status

from core.settings import get_settings

logger = logging.getLogger("Auth")


def get_api_key_hash_from_env() -> str:
    """
    Get the hashed API key from environment variable.

    The API_KEY_HASH should be a bcrypt hash generated from your password.
    Use the generate_hash.py script to create one.

    Raises:
        SystemExit: If API_KEY_HASH is not set in production
    """
    # Prefer direct environment variable (supports runtime overrides in tests)
    api_key_hash = os.getenv("API_KEY_HASH") or get_settings().api_key_hash
    if api_key_hash:
        return api_key_hash

    # API_KEY_HASH is required
    logger.error("❌ ERROR: API_KEY_HASH is not set in environment variables!")
    logger.error("❌ Authentication cannot work without a password configured.")
    logger.error("💡 To fix: Run 'python generate_hash.py' to create a hash, then add it to .env")
    sys.exit(1)


def get_guest_password_hash_from_env() -> str | None:
    """
    Get the hashed guest password from environment variable.

    The GUEST_PASSWORD_HASH should be a bcrypt hash generated from your guest password.
    Use the generate_hash.py script to create one.

    Returns:
        str | None: The guest password hash if set, None otherwise
    """
    return os.getenv("GUEST_PASSWORD_HASH") or get_settings().guest_password_hash


def is_guest_login_enabled() -> bool:
    """
    Check if guest login is enabled via environment variable.

    Returns:
        bool: True if guest login is enabled, False otherwise
    """
    env_value = os.getenv("ENABLE_GUEST_LOGIN")
    if env_value is not None:
        return str(env_value).lower() in {"1", "true", "yes", "on"}
    return get_settings().enable_guest_login


def validate_api_key(provided_key: str) -> bool:
    """
    Validate the provided API key against the configured hashed password.

    Uses constant-time comparison via bcrypt to prevent timing attacks.

    Args:
        provided_key: The plaintext password/API key provided by the user

    Returns:
        bool: True if the password matches, False otherwise
    """
    try:
        expected_hash = get_api_key_hash_from_env()
        # bcrypt.checkpw handles constant-time comparison internally
        return bcrypt.checkpw(provided_key.encode("utf-8"), expected_hash.encode("utf-8"))
    except Exception as e:
        logger.error(f"❌ Error validating API key: {e}")
        return False


def validate_password_with_role(provided_key: str) -> str | None:
    """
    Validate the provided password and return the user's role.

    Checks against both admin and guest password hashes (if guest login is enabled).

    Args:
        provided_key: The plaintext password provided by the user

    Returns:
        str | None: 'admin' if admin password matches, 'guest' if guest password matches,
                    None if no password matches
    """
    try:
        # Check admin password
        admin_hash = get_api_key_hash_from_env()
        if bcrypt.checkpw(provided_key.encode("utf-8"), admin_hash.encode("utf-8")):
            return "admin"

        # Check guest password if configured and enabled
        if is_guest_login_enabled():
            guest_hash = get_guest_password_hash_from_env()
            if guest_hash:
                if bcrypt.checkpw(provided_key.encode("utf-8"), guest_hash.encode("utf-8")):
                    return "guest"

        return None
    except Exception as e:
        logger.error(f"❌ Error validating password: {e}")
        return None


def get_jwt_secret() -> str:
    """
    Get the JWT secret key from environment variable.

    Raises:
        SystemExit: If JWT_SECRET is not set in production

    Returns:
        str: The JWT secret key
    """
    jwt_secret = os.getenv("JWT_SECRET") or get_settings().jwt_secret
    if not jwt_secret:
        logger.error("❌ ERROR: JWT_SECRET is not set in environment variables!")
        logger.error("❌ Without a stable secret, tokens will be invalidated on every server restart.")
        logger.error("💡 To fix: Generate a secret with 'python -c \"import secrets; print(secrets.token_hex(32))\"'")
        logger.error("💡 Then add JWT_SECRET=<your_secret> to your .env file")
        sys.exit(1)
    return jwt_secret


def generate_jwt_token(role: str = "admin", expiration_hours: int = 168, user_id: str | None = None) -> str:
    """
    Generate a JWT token for authentication.

    Args:
        role: User role ('admin', 'guest', or 'user')
        expiration_hours: Hours until token expires (default: 168 = 7 days)
        user_id: Unique identifier for the authenticated user
                 - admin: defaults to 'admin'
                 - guest: auto-generated as 'guest-{random}'
                 - user: required, should be 'user-{db_id}' for Google Sign-In users

    Returns:
        str: Encoded JWT token
    """
    # Default user_id handling
    if user_id is None:
        if role == "guest":
            user_id = f"guest-{secrets.token_hex(6)}"
        elif role == "user":
            # user role requires explicit user_id (from database)
            raise ValueError("user_id is required for 'user' role")
        else:
            user_id = "admin"

    secret = get_jwt_secret()
    payload = {
        "exp": datetime.utcnow() + timedelta(hours=expiration_hours),
        "iat": datetime.utcnow(),
        "type": "access_token",
        "role": role,
        "user_id": user_id,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def validate_jwt_token(token: str) -> dict | None:
    """
    Validate a JWT token and return its payload.

    Args:
        token: The JWT token to validate

    Returns:
        dict | None: Token payload if valid, None otherwise
    """
    try:
        secret = get_jwt_secret()
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("⚠️  JWT token has expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"⚠️  Invalid JWT token: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Error validating JWT token: {e}")
        return None


def generate_sse_ticket(room_id: int, user_id: str, expiration_seconds: int = 60) -> str:
    """
    Generate a short-lived SSE ticket for a specific room.

    This ticket is used for SSE connections where the browser's EventSource API
    doesn't support custom headers. The ticket is short-lived to minimize exposure
    if it appears in logs or browser history.

    Args:
        room_id: The room ID this ticket is valid for
        user_id: User ID that owns this ticket (for access control)
        expiration_seconds: Seconds until ticket expires (default: 60)

    Returns:
        str: Encoded JWT ticket
    """
    secret = get_jwt_secret()
    payload = {
        "exp": datetime.utcnow() + timedelta(seconds=expiration_seconds),
        "iat": datetime.utcnow(),
        "type": "sse_ticket",
        "room_id": room_id,
        "user_id": user_id,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def validate_sse_ticket(ticket: str, room_id: int) -> dict | None:
    """
    Validate an SSE ticket for a specific room.

    Args:
        ticket: The SSE ticket to validate
        room_id: The room ID to validate against

    Returns:
        dict | None: Ticket payload with user_id if valid, None otherwise
    """
    try:
        secret = get_jwt_secret()
        payload = jwt.decode(ticket, secret, algorithms=["HS256"])

        # Verify this is an SSE ticket
        if payload.get("type") != "sse_ticket":
            logger.warning("⚠️  Token is not an SSE ticket")
            return None

        # Verify room_id matches
        if payload.get("room_id") != room_id:
            logger.warning(f"⚠️  SSE ticket room_id mismatch: expected {room_id}, got {payload.get('room_id')}")
            return None

        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("⚠️  SSE ticket has expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"⚠️  Invalid SSE ticket: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Error validating SSE ticket: {e}")
        return None


def get_role_from_token(token: str) -> str | None:
    """
    Extract the role from a JWT token.

    Args:
        token: The JWT token

    Returns:
        str | None: The role ('admin', 'guest', or 'user') if valid, None otherwise
    """
    payload = validate_jwt_token(token)
    if payload:
        return payload.get("role", "admin")  # Default to admin for old tokens
    return None


def get_user_id_from_token(token: str) -> str | None:
    """
    Extract the user_id from a JWT token.

    Falls back to role when missing for backward compatibility with legacy tokens.
    """
    payload = validate_jwt_token(token)
    if not payload:
        return None

    # Legacy tokens didn't include user_id; fallback to role-based defaults
    if "user_id" not in payload:
        role = payload.get("role", "admin")
        return "admin" if role == "admin" else "guest"

    return payload.get("user_id")


class AuthMiddleware:
    """
    Pure ASGI middleware for JWT token authentication.

    Using pure ASGI instead of BaseHTTPMiddleware to support SSE/streaming responses
    (required for MCP endpoint compatibility).

    Authentication methods:
    - REST API: X-API-Key header (contains JWT token)

    Excluded paths (no auth required):
    - /auth/login - Login endpoint
    - /auth/health - Health check
    - /docs, /openapi.json, /redoc - API documentation
    - /mcp - MCP endpoint (SSE streaming)
    """

    # Paths that don't require authentication
    EXCLUDED_PATHS = {
        "/",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/auth/login",
        "/auth/google",  # Google Sign-In endpoint
        "/auth/health",
        "/register",  # OAuth dynamic client registration (for MCP clients)
    }

    # Path prefixes that don't require authentication
    EXCLUDED_PREFIXES = (
        "/mcp",  # MCP endpoint (handles its own auth via MCP protocol)
        "/assets",  # Static assets (JS, CSS, images) for bundled mode
        "/.well-known",  # OAuth/OpenID discovery (for MCP clients)
    )

    # API path prefixes (routes that require authentication)
    API_PREFIXES = (
        "/auth/",
        "/rooms/",
        "/agents/",
        "/debug/",
    )

    def __init__(self, app):
        self.app = app

    def _is_api_route(self, path: str) -> bool:
        """Check if path is an API route that requires authentication."""
        # Exact API paths
        if path in {"/auth/login", "/auth/health"}:
            return False  # These are excluded from auth
        # API prefixes
        return path.startswith(self.API_PREFIXES)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        method = scope["method"]
        headers = dict(scope.get("headers", []))

        # Skip auth for excluded paths
        if path in self.EXCLUDED_PATHS:
            await self.app(scope, receive, send)
            return

        # Skip auth for excluded prefixes (like /mcp, /assets)
        if path.startswith(self.EXCLUDED_PREFIXES):
            await self.app(scope, receive, send)
            return

        # Skip auth for profile picture requests (needed for <img> tags)
        if path.startswith("/agents/") and path.endswith("/profile-pic"):
            await self.app(scope, receive, send)
            return

        # Skip auth for voice status check and audio file serving
        if path == "/voice/status" or path.startswith("/voice/audio/"):
            await self.app(scope, receive, send)
            return

        # Skip auth for SSE stream endpoints (they handle auth via query param)
        # EventSource API doesn't support custom headers, so auth is passed as query param
        if path.startswith("/rooms/") and path.endswith("/stream"):
            await self.app(scope, receive, send)
            return

        # In bundled mode, skip auth for non-API routes (frontend SPA routes)
        if getattr(sys, "frozen", False) and not self._is_api_route(path):
            await self.app(scope, receive, send)
            return

        # Skip auth for OPTIONS requests (CORS preflight)
        if method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        # Extract token from header (primary) or cookie (fallback)
        token = headers.get(b"x-api-key", b"").decode("utf-8") or None

        # If no header token, try cookie
        if not token:
            cookie_header = headers.get(b"cookie", b"").decode("utf-8")
            if cookie_header:
                # Parse cookies to find auth_token
                for cookie in cookie_header.split(";"):
                    cookie = cookie.strip()
                    if cookie.startswith("auth_token="):
                        token = cookie[len("auth_token=") :]
                        break

        # Validate JWT token
        token_payload = validate_jwt_token(token) if token else None
        if not token_payload:
            # Build 401 response
            origin = headers.get(b"origin", b"").decode("utf-8")
            response_headers = [
                (b"content-type", b"application/json"),
            ]
            if origin:
                response_headers.extend(
                    [
                        (b"access-control-allow-origin", origin.encode()),
                        (b"access-control-allow-credentials", b"true"),
                        (b"access-control-allow-methods", b"*"),
                        (b"access-control-allow-headers", b"*"),
                    ]
                )

            body = b'{"detail":"Invalid or missing authentication token"}'
            response_headers.append((b"content-length", str(len(body)).encode()))

            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": response_headers,
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": body,
                }
            )
            return

        # Store auth info in scope state for later use
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["user_role"] = token_payload.get("role", "admin")
        scope["state"]["user_id"] = token_payload.get("user_id") or (
            "admin" if scope["state"]["user_role"] == "admin" else "guest"
        )

        # Continue processing the request
        await self.app(scope, receive, send)


def require_admin(request: Request):
    """
    Dependency function to require admin role for an endpoint.

    Args:
        request: The FastAPI request object

    Raises:
        HTTPException: 403 Forbidden if user is not an admin

    Usage:
        @app.delete("/rooms/{room_id}", dependencies=[Depends(require_admin)])
        async def delete_room(room_id: int):
            ...
    """
    user_role = getattr(request.state, "user_role", None)
    if user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires admin privileges.",
        )


async def ensure_room_access(room, user_id: str, user_role: str) -> None:
    """
    Verify that a user can access a specific room.

    Room access rules:
    - Admins can access all rooms
    - Non-admins can only access rooms they own (owner_id matches user_id)

    Args:
        room: Room object (must have owner_id attribute)
        user_id: The user's ID
        user_role: The user's role ('admin', 'guest', or 'user')

    Raises:
        HTTPException: 403 Forbidden if user cannot access the room
    """
    # Admins can access all rooms
    if user_role == "admin":
        return

    # Non-admins can only access their own rooms
    if room.owner_id != user_id:
        logger.warning(f"⚠️  User {user_id} attempted to access room owned by {room.owner_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this room.",
        )
