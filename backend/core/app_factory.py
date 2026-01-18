"""
Application factory for creating FastAPI app instances.

This module provides functions for creating and configuring the FastAPI application
with all necessary middleware, routers, and dependencies.
"""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

import crud
from database import get_db, init_db
from infrastructure.scheduler import BackgroundScheduler
from fastapi import FastAPI
from fastapi_mcp import FastApiMCP
from orchestration import ChatOrchestrator
from core import AgentManager

from core import get_logger, get_settings

logger = get_logger("AppFactory")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    from core.auth import AuthMiddleware
    from fastapi.middleware.cors import CORSMiddleware
    from routers import agent_management, agents, auth, debug, exports, mcp_tools, messages, room_agents, rooms
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
        from core.config import log_config_validation

        log_config_validation()

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

        # Seed agents from config files
        async for db in get_db():
            await crud.seed_agents_from_configs(db)
            break

        # Start background scheduler
        background_scheduler.start()

        # Initialize Codex MCP server if enabled
        codex_mcp_manager = None
        if settings.codex_use_mcp:
            try:
                from providers.codex import CodexMCPServerManager
                logger.info("🔌 Starting Codex MCP server (CODEX_USE_MCP=true)...")
                codex_mcp_manager = await CodexMCPServerManager.get_instance()
                await codex_mcp_manager.ensure_started()
                logger.info("✅ Codex MCP server started")
            except Exception as e:
                logger.warning(f"⚠️ Failed to start Codex MCP server: {e}")

        logger.info("✅ Application startup complete")

        yield

        # Shutdown
        logger.info("🛑 Application shutdown...")

        # Shutdown Codex MCP server if it was started
        if codex_mcp_manager is not None:
            logger.info("🔌 Shutting down Codex MCP server...")
            await codex_mcp_manager.shutdown()

        background_scheduler.stop()
        await agent_manager.shutdown()
        logger.info("✅ Application shutdown complete")

    # Initialize rate limiter
    limiter = Limiter(key_func=get_remote_address)

    # Create app with lifespan
    app = FastAPI(title="ChitChats API", lifespan=lifespan)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Add authentication middleware FIRST (will process after CORS)
    app.add_middleware(AuthMiddleware)

    # CORS middleware added LAST (processes requests FIRST in Starlette)
    # This ensures preflight OPTIONS requests are handled before auth
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
    app.include_router(exports.router, prefix="/exports", tags=["Exports"])
    app.include_router(mcp_tools.router, tags=["MCP Tools"])

    # Mount MCP server - exposes simplified tools for easy LLM integration
    # Only expose "MCP Tools" tag with clean, semantic tool names
    mcp = FastApiMCP(
        app,
        name="ChitChats",
        description="Chat with AI agents. Use 'list_agents' to see available agents, then 'chat' to talk with them.",
        include_tags=["MCP Tools"],  # Only expose simplified MCP tools
        headers=["authorization", "x-api-key"],  # Forward auth headers to API calls
    )
    mcp.mount()
    logger.info("🔌 MCP server mounted at /mcp (5 simplified tools)")

    # Serve static frontend files when running as PyInstaller bundle
    if getattr(sys, "frozen", False):
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        # Get the bundled static files directory
        base_path = Path(sys._MEIPASS)
        static_dir = base_path / "static"

        if static_dir.exists():
            # Mount static assets (JS, CSS, images)
            app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")
            logger.info(f"📦 Serving static files from: {static_dir}")

            # Catch-all route for SPA - must be last
            @app.get("/{full_path:path}")
            async def serve_spa(full_path: str):
                """Serve index.html for all non-API routes (SPA routing)."""
                # Check if it's an API route (already handled by routers)
                if full_path.startswith(("api/", "auth/", "rooms/", "agents/", "debug/", "mcp")):
                    return None
                # Serve index.html for SPA routes
                index_file = static_dir / "index.html"
                if index_file.exists():
                    return FileResponse(index_file)
                return FileResponse(static_dir / "index.html")
        else:
            logger.warning(f"⚠️ Static files directory not found: {static_dir}")

    return app
