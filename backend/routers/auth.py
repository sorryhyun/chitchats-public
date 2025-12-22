"""Authentication routes for login and token verification."""

import json
import secrets

from auth import generate_jwt_token, validate_password_with_role
from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

router = APIRouter()

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)


@router.post("/login")
@limiter.limit("20/minute")  # Rate limit: 20 attempts per minute per IP
async def login(request: Request):
    """
    Validate password and return a JWT token for session storage.
    The client should store the returned api_key (JWT token) and include it in all subsequent requests.

    Supports both admin and guest passwords:
    - Admin password: Full access to all features
    - Guest password: Read-only access, can chat but cannot modify rooms/agents/messages

    Security features:
    - Rate limited to 20 attempts per minute per IP address (via slowapi)
    - Returns a JWT token instead of plaintext password

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
            return {
                "success": True,
                "api_key": token,  # Return JWT token (not the password!)
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


@router.get("/health")
async def health_check():
    """Health check endpoint (no auth required)."""
    return {"status": "healthy"}


@router.get("/health/pool")
async def pool_stats(request: Request):
    """Get client pool statistics (for debugging)."""
    agent_manager = request.app.state.agent_manager
    pool = agent_manager.client_pool
    pool_keys = list(pool.pool.keys())
    cleanup_tasks = len(pool._cleanup_tasks)

    # Get semaphore availability (how many slots are free for new connections)
    semaphore = pool._connection_semaphore
    # Note: _value is internal but useful for debugging
    available_slots = getattr(semaphore, "_value", "unknown")

    return {
        "pool_size": len(pool_keys),
        "pool_keys": [str(k) for k in pool_keys],
        "pending_cleanup_tasks": cleanup_tasks,
        "active_clients": len(agent_manager.active_clients),
        "connection_semaphore_available": available_slots,
        "max_concurrent_connections": pool.MAX_CONCURRENT_CONNECTIONS,
    }
