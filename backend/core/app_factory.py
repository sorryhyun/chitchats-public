"""
Application factory for creating FastAPI app instances.

This module provides functions for creating and configuring the FastAPI application
with all necessary middleware, routers, and dependencies.
"""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

import crud
from background_scheduler import BackgroundScheduler
from database import get_db, init_db
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from orchestration import ChatOrchestrator
from sdk import AgentManager
from starlette.responses import FileResponse
from utils.write_queue import start_writer, stop_writer

from core import get_logger, get_settings


def get_static_dir() -> Path | None:
    """Get the path to the built frontend static files."""
    # When running as PyInstaller bundle, static files are in _MEIPASS
    if getattr(sys, "frozen", False):
        base_path = Path(sys._MEIPASS)
        static_dir = base_path / "static"
        if static_dir.exists():
            return static_dir

    # Development: check for frontend/dist
    dev_static = Path(__file__).parent.parent.parent / "frontend" / "dist"
    if dev_static.exists():
        return dev_static

    return None


logger = get_logger("AppFactory")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    from auth import AuthMiddleware
    from fastapi.middleware.cors import CORSMiddleware
    from routers import agent_management, agents, auth, debug, messages, room_agents, rooms
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address

    settings = get_settings()

    # Create lifespan context manager
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Lifespan context manager for application startup and shutdown."""
        # Startup
        logger.info("🚀 Application startup...")

        # Validate configuration files
        from config.config_loader import log_config_validation

        log_config_validation()

        # Start write queue for serialized DB writes
        await start_writer()

        # Initialize database
        await init_db()

        # Create singleton instances
        agent_manager = AgentManager()
        priority_agent_names = settings.get_priority_agent_names()
        chat_orchestrator = ChatOrchestrator(priority_agent_names=priority_agent_names)
        background_scheduler = BackgroundScheduler(
            chat_orchestrator=chat_orchestrator,
            agent_manager=agent_manager,
            get_db_session=get_db,
            max_concurrent_rooms=settings.max_concurrent_rooms,
        )

        # Log priority agent configuration
        if priority_agent_names:
            logger.info(f"🎯 Priority agents enabled: {priority_agent_names}")
            logger.info("   💡 Priority agents will respond first in both initial and follow-up rounds")
        else:
            logger.info("👥 All agents have equal priority (PRIORITY_AGENTS not set)")

        # Store in app state for dependency injection
        app.state.agent_manager = agent_manager
        app.state.chat_orchestrator = chat_orchestrator
        app.state.background_scheduler = background_scheduler
        app.state.background_tasks = set()  # Track fire-and-forget tasks

        # Seed agents from config files
        async for db in get_db():
            await crud.seed_agents_from_configs(db)
            break

        # Start background scheduler
        background_scheduler.start()

        logger.info("✅ Application startup complete")

        yield

        # Shutdown
        logger.info("🛑 Application shutdown...")
        background_scheduler.stop()

        # Wait for background tasks to complete (with timeout)
        if app.state.background_tasks:
            import asyncio

            logger.info(f"⏳ Waiting for {len(app.state.background_tasks)} background tasks...")
            done, pending = await asyncio.wait(app.state.background_tasks, timeout=5.0)
            if pending:
                logger.warning(f"⚠️ Cancelling {len(pending)} pending background tasks")
                for task in pending:
                    task.cancel()

        # Shutdown orchestrator (cancels active room tasks)
        await chat_orchestrator.shutdown()
        await agent_manager.shutdown()
        await stop_writer()
        logger.info("✅ Application shutdown complete")

    # Initialize rate limiter
    limiter = Limiter(key_func=get_remote_address)

    # Create app with lifespan
    app = FastAPI(title="Claude Code Role Play API", lifespan=lifespan)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # CORS middleware
    allowed_origins = settings.get_cors_origins()
    logger.info("🔒 CORS Configuration:")
    logger.info(f"   Allowed origins: {allowed_origins}")
    logger.info("   💡 To add more origins, set FRONTEND_URL or VERCEL_URL in .env")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add authentication middleware
    app.add_middleware(AuthMiddleware)

    # Add request ID middleware for log correlation
    from middleware import RequestIDMiddleware

    app.add_middleware(RequestIDMiddleware)

    # Register routers
    # IMPORTANT: agent_management must come before agents to ensure /agents/configs
    # matches before /agents/{agent_id} (more specific routes before generic ones)
    app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
    app.include_router(rooms.router, prefix="/rooms", tags=["Rooms"])
    app.include_router(agent_management.router, prefix="/agents", tags=["Agent Management"])
    app.include_router(agents.router, prefix="/agents", tags=["Agents"])
    app.include_router(room_agents.router, prefix="/rooms", tags=["Room-Agents"])
    app.include_router(messages.router, prefix="/rooms", tags=["Messages"])
    app.include_router(debug.router, prefix="/debug", tags=["Debug"])

    # Add health check to root
    app.include_router(auth.router, tags=["Health"])

    # Mount static files for bundled frontend (production/packaged mode)
    static_dir = get_static_dir()
    if static_dir:
        logger.info(f"📦 Serving static frontend from: {static_dir}")

        # Serve static assets (js, css, images)
        assets_dir = static_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        # Catch-all route for SPA - serve index.html for non-API routes
        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            """Serve the SPA for all non-API routes."""
            # Don't serve SPA for API routes (they're already handled by routers)
            if full_path.startswith(("auth", "rooms", "agents", "debug")):
                return None
            index_file = static_dir / "index.html"
            if index_file.exists():
                return FileResponse(str(index_file))
            return {"error": "Frontend not found"}

    return app
