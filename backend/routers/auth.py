"""Authentication routes for login and token verification."""

import json
import secrets

from core import generate_jwt_token, validate_password_with_role
from fastapi import APIRouter, HTTPException, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address

router = APIRouter()

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

# Cookie settings for secure JWT storage
COOKIE_NAME = "auth_token"
COOKIE_MAX_AGE = 7 * 24 * 60 * 60  # 7 days in seconds


def set_auth_cookie(response: Response, token: str) -> None:
    """Set HttpOnly cookie with JWT token for secure storage."""
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,  # Not accessible via JavaScript
        secure=True,  # Only sent over HTTPS (set False for local dev)
        samesite="lax",  # Provides CSRF protection while allowing normal navigation
        path="/",  # Available to all routes
    )


def clear_auth_cookie(response: Response) -> None:
    """Clear the auth cookie on logout."""
    response.delete_cookie(key=COOKIE_NAME, path="/")


@router.post("/login")
@limiter.limit("20/minute")  # Rate limit: 20 attempts per minute per IP
async def login(request: Request, response: Response):
    """
    Validate password and return a JWT token for session storage.
    The token is stored in an HttpOnly cookie for security, and also returned in the response
    for backwards compatibility with clients that use header-based auth.

    Supports both admin and guest passwords:
    - Admin password: Full access to all features
    - Guest password: Limited access to their own rooms and chat; admin-only operations remain restricted

    Security features:
    - Rate limited to 20 attempts per minute per IP address (via slowapi)
    - Returns a JWT token in HttpOnly cookie (cannot be accessed by JavaScript)

    Returns:
        - 400: Invalid request body or missing password
        - 401: Invalid password
        - 429: Too many requests (rate limited)
    """
    try:
        body = await request.json()
        password = body.get("password")

        if not password:
            raise HTTPException(status_code=400, detail="Password is required")

        # Validate password and get role
        role = validate_password_with_role(password)

        if role:
            # Generate a unique user_id for this session (admin is fixed)
            user_id = "admin" if role == "admin" else f"guest-{secrets.token_hex(6)}"

            # Generate a JWT token with the appropriate role (valid for 7 days by default)
            token = generate_jwt_token(role=role, user_id=user_id, expiration_hours=168)

            # Set HttpOnly cookie for secure token storage
            set_auth_cookie(response, token)

            return {
                "success": True,
                "api_key": token,  # Also return in body for backwards compatibility
                "role": role,  # Return the user's role
                "user_id": user_id,
                "message": f"Login successful as {role}",
            }
        else:
            raise HTTPException(status_code=401, detail="Invalid password")

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid request body")


@router.get("/verify")
async def verify_auth(request: Request):
    """
    Verify that the current API key is valid and return the user's role.
    This endpoint is protected by the auth middleware, so if we reach here, auth is valid.
    """
    user_role = getattr(request.state, "user_role", "admin")
    user_id = getattr(request.state, "user_id", "admin")
    return {"success": True, "message": "Authentication valid", "role": user_role, "user_id": user_id}


@router.post("/logout")
async def logout(response: Response):
    """
    Log out by clearing the auth cookie.
    This invalidates the session on the client side.
    """
    clear_auth_cookie(response)
    return {"success": True, "message": "Logged out successfully"}


@router.get("/health")
async def health_check():
    """Health check endpoint (no auth required)."""
    return {"status": "healthy"}


@router.get("/health/pool")
async def pool_stats(request: Request):
    """Get client pool statistics (for debugging)."""
    agent_manager = getattr(request.app.state, "agent_manager", None)
    if not agent_manager:
        return {"error": "agent_manager not available"}

    pool = getattr(agent_manager, "client_pool", None)
    if not pool:
        return {"error": "client_pool not available"}

    # Defensive access to pool internals
    pool_dict = getattr(pool, "pool", {})
    pool_keys = list(pool_dict.keys())
    cleanup_tasks_set = getattr(pool, "_cleanup_tasks", set())
    cleanup_tasks = len(cleanup_tasks_set)

    # Get semaphore availability (how many slots are free for new connections)
    semaphore = getattr(pool, "_connection_semaphore", None)
    # Note: _value is internal but useful for debugging
    available_slots = getattr(semaphore, "_value", "unknown") if semaphore else "unknown"

    active_clients = getattr(agent_manager, "active_clients", {})
    max_connections = getattr(pool, "MAX_CONCURRENT_CONNECTIONS", "unknown")

    return {
        "pool_size": len(pool_keys),
        "pool_keys": [str(k) for k in pool_keys],
        "pending_cleanup_tasks": cleanup_tasks,
        "active_clients": len(active_clients),
        "connection_semaphore_available": available_slots,
        "max_concurrent_connections": max_connections,
    }
