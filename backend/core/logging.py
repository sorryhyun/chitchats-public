"""
Centralized logging configuration.

This module provides a single place to configure logging for the entire application.
Call setup_logging() once at application startup.
"""

import logging
import uuid
from contextvars import ContextVar
from typing import Optional

# Context variable for correlation ID (thread-safe for async)
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Get the current correlation ID for request tracking."""
    return correlation_id_var.get()


def set_correlation_id(correlation_id: str | None = None) -> str:
    """Set a correlation ID for the current context. Returns the ID set."""
    cid = correlation_id or uuid.uuid4().hex[:12]
    correlation_id_var.set(cid)
    return cid


class CorrelationIdFilter(logging.Filter):
    """Add correlation ID to log records."""

    def filter(self, record):
        """Add correlation_id attribute to record."""
        try:
            record.correlation_id = correlation_id_var.get() or "-"
        except Exception:
            # During interpreter shutdown, context vars may be unavailable
            record.correlation_id = "-"
        return True


class SuppressPollingLogsFilter(logging.Filter):
    """Filter to suppress noisy polling endpoint logs."""

    def filter(self, record):
        """Filter out polling endpoint access logs."""
        if hasattr(record, "getMessage"):
            message = record.getMessage()
            if "/messages/poll" in message or "/chatting-agents" in message:
                return False
        return True


def setup_logging(debug_mode: bool = True, log_level: Optional[int] = None, json_output: bool = False) -> None:
    """
    Configure application-wide logging.

    This function should be called once at application startup, before any other
    logging occurs. It configures the root logger and applies filters.

    Args:
        debug_mode: If True, set log level to DEBUG (unless log_level is explicitly provided)
        log_level: Explicit log level to use (overrides debug_mode)
        json_output: If True, output logs in JSON format (for production)
    """
    # Determine log level
    if log_level is None:
        log_level = logging.DEBUG if debug_mode else logging.INFO

    # Configure root logger with correlation ID in format
    if json_output:
        # JSON format for production (easier to parse in log aggregation systems)
        log_format = '{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","correlation_id":"%(correlation_id)s","message":"%(message)s"}'
    else:
        # Human-readable format for development
        log_format = "%(asctime)s | %(levelname)-8s | %(name)s | [%(correlation_id)s] %(message)s"

    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,  # Override any existing configuration
    )

    # Add correlation ID filter to all handlers (not the logger)
    # Filters on loggers only apply to records handled directly by that logger,
    # not to records from child loggers. Adding to handlers ensures all records get the filter.
    root_logger = logging.getLogger()
    correlation_filter = CorrelationIdFilter()
    for handler in root_logger.handlers:
        handler.addFilter(correlation_filter)

    # Apply filter to uvicorn access logger to suppress polling endpoints
    uvicorn_logger = logging.getLogger("uvicorn.access")
    uvicorn_logger.addFilter(SuppressPollingLogsFilter())

    # Suppress verbose SSE-related loggers
    logging.getLogger("sse_starlette").setLevel(logging.WARNING)
    logging.getLogger("sse_starlette.sse").setLevel(logging.WARNING)
    logging.getLogger("EventBroadcaster").setLevel(logging.INFO)

    # Suppress verbose aiosqlite debug logs
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)

    # Suppress MCP client JSONRPC parsing errors (noisy during normal operation)
    logging.getLogger("mcp.client.stdio").setLevel(logging.CRITICAL)

    # Log the configuration
    logger = logging.getLogger("Logging")
    level_name = logging.getLevelName(log_level)
    logger.info(f"Logging configured with level: {level_name}")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the specified name.

    This is a convenience wrapper around logging.getLogger that ensures
    consistent logger naming across the application.

    Args:
        name: Name for the logger (typically __name__ or a descriptive string)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)
