"""
ChitChats API - Multi-Claude chat room application.

This is the main entry point for the FastAPI application.
All application configuration and setup is handled by the app factory.
"""

# Windows asyncio subprocess fix - must be set before any async code runs
import sys
if sys.platform == "win32":
    import asyncio
    # ProactorEventLoop is required for subprocess support on Windows
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Initialize settings and logging first
from core import get_settings, setup_logging

settings = get_settings()
setup_logging(debug_mode=settings.debug_agents)

# Create the FastAPI application
from core.app_factory import create_app

app = create_app()
