"""
Test utilities for dependency injection and testing.

This module provides helpers for creating test app instances with overridden components.
"""

from contextlib import asynccontextmanager
from typing import Optional

from core import AuthMiddleware, get_settings
from core.manager import AgentManager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from infrastructure.database import get_db, init_db
from infrastructure.scheduler import BackgroundScheduler
from orchestration import ChatOrchestrator
from slowapi import Limiter
from slowapi.util import get_remote_address


@asynccontextmanager
async def test_lifespan(
    app: FastAPI,
    agent_manager: Optional[AgentManager] = None,
    chat_orchestrator: Optional[ChatOrchestrator] = None,
    start_scheduler: bool = False,
):
    """
    Test lifespan context manager with optional component overrides.

    Args:
        app: FastAPI application instance
        agent_manager: Optional custom AgentManager instance
        chat_orchestrator: Optional custom ChatOrchestrator instance
        start_scheduler: Whether to start the background scheduler (default: False for tests)

    Yields:
        None
    """
    # Initialize database
    await init_db()

    # Use provided instances or create defaults
    if agent_manager is None:
        agent_manager = AgentManager()
    if chat_orchestrator is None:
        chat_orchestrator = ChatOrchestrator()

    settings = get_settings()
    background_scheduler = BackgroundScheduler(
        chat_orchestrator=chat_orchestrator,
        agent_manager=agent_manager,
        get_db_session=get_db,
        max_concurrent_rooms=settings.max_concurrent_rooms,
    )

    # Store in app state
    app.state.agent_manager = agent_manager
    app.state.chat_orchestrator = chat_orchestrator
    app.state.background_scheduler = background_scheduler

    # Optionally start scheduler (usually disabled in tests)
    if start_scheduler:
        background_scheduler.start()

    yield

    # Shutdown
    if start_scheduler:
        background_scheduler.stop()
    await agent_manager.shutdown()


def create_test_app(
    agent_manager: Optional[AgentManager] = None,
    chat_orchestrator: Optional[ChatOrchestrator] = None,
    start_scheduler: bool = False,
    include_routers: bool = True,
) -> FastAPI:
    """
    Create a FastAPI app instance for testing with optional component overrides.

    Args:
        agent_manager: Optional custom AgentManager instance
        chat_orchestrator: Optional custom ChatOrchestrator instance
        start_scheduler: Whether to start the background scheduler
        include_routers: Whether to include all routers (default: True)

    Returns:
        FastAPI application configured for testing

    Example:
        >>> from unittest.mock import Mock
        >>> mock_agent_manager = Mock(spec=AgentManager)
        >>> app = create_test_app(agent_manager=mock_agent_manager)
        >>> # Use app in tests with dependency injection
    """
    settings = get_settings()
    limiter = Limiter(key_func=get_remote_address)

    # Create lifespan with overrides
    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        async with test_lifespan(
            app=app,
            agent_manager=agent_manager,
            chat_orchestrator=chat_orchestrator,
            start_scheduler=start_scheduler,
        ):
            yield

    app = FastAPI(title="ChitChats API (Test)", lifespan=_lifespan)
    app.state.limiter = limiter

    # Add CORS middleware
    allowed_origins = settings.get_cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add authentication middleware
    app.add_middleware(AuthMiddleware)

    # Optionally include routers
    if include_routers:
        from routers import agent_management, agents, auth, messages, room_agents, rooms

        app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
        app.include_router(rooms.router, prefix="/rooms", tags=["Rooms"])
        app.include_router(agent_management.router, prefix="/agents", tags=["Agent Management"])
        app.include_router(agents.router, prefix="/agents", tags=["Agents"])
        app.include_router(room_agents.router, prefix="/rooms", tags=["Room-Agents"])
        app.include_router(messages.router, prefix="/rooms", tags=["Messages"])
        app.include_router(auth.router, tags=["Health"])

    return app
