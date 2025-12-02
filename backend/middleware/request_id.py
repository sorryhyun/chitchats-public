"""
Request ID middleware for log correlation.

This middleware adds a unique request ID to each incoming request,
enabling correlation of logs across the request lifecycle.
"""

import uuid
from contextvars import ContextVar
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Context variable to store request ID across async boundaries
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def get_request_id() -> Optional[str]:
    """Get the current request ID from context."""
    return request_id_var.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds a unique request ID to each request.

    The request ID is:
    - Generated if not provided in X-Request-ID header
    - Stored in context for use throughout the request
    - Added to the response X-Request-ID header
    """

    async def dispatch(self, request: Request, call_next):
        # Get existing request ID or generate new one
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())[:8]  # Short ID for readability

        # Store in context for logging
        token = request_id_var.set(request_id)

        try:
            response = await call_next(request)
            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_var.reset(token)
