"""
Centralized logging configuration.

This module provides a single place to configure logging for the entire application.
Call setup_logging() once at application startup.
"""

import logging
from typing import Optional


class SuppressPollingLogsFilter(logging.Filter):
    """Filter to suppress noisy polling endpoint logs."""

    def filter(self, record):
        """Filter out polling endpoint access logs."""
        if hasattr(record, "getMessage"):
            message = record.getMessage()
            if "/messages/poll" in message or "/chatting-agents" in message:
                return False
        return True


def setup_logging(debug_mode: bool = True, log_level: Optional[int] = None) -> None:
    """
    Configure application-wide logging.

    This function should be called once at application startup, before any other
    logging occurs. It configures the root logger and applies filters.

    Args:
        debug_mode: If True, set log level to DEBUG (unless log_level is explicitly provided)
        log_level: Explicit log level to use (overrides debug_mode)
    """
    # Determine log level
    if log_level is None:
        log_level = logging.DEBUG if debug_mode else logging.INFO

    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,  # Override any existing configuration
    )

    # Apply filter to uvicorn access logger to suppress polling endpoints
    uvicorn_logger = logging.getLogger("uvicorn.access")
    uvicorn_logger.addFilter(SuppressPollingLogsFilter())

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
