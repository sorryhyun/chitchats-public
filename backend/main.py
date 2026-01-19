"""
ChitChats API - Multi-Claude chat room application.

This is the main entry point for the FastAPI application.
All application configuration and setup is handled by the app factory.
"""

# Initialize settings and logging first
from core import get_settings, setup_logging

settings = get_settings()
setup_logging(debug_mode=settings.debug_agents)

# Create the FastAPI application
from core.app_factory import create_app

app = create_app()
