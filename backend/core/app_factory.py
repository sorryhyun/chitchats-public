"""
Application factory for creating FastAPI app instances.

This module provides functions for creating and configuring the FastAPI application
with all necessary middleware, routers, and dependencies.
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import crud
from chatroom_orchestration import ChatOrchestrator
from fastapi import FastAPI, Request
from fastapi_mcp import FastApiMCP
from infrastructure.database import get_db, init_db, shutdown_db
from infrastructure.scheduler import BackgroundScheduler

from core import get_logger, get_settings
from core.manager import AgentManager
from core.sse import EventBroadcaster

logger = get_logger("AppFactory")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    from fastapi.middleware.cors import CORSMiddleware
    from routers import (
        agent_management,
        agents,
        auth,
        debug,
        exports,
        messages,
        providers,
        room_agents,
        rooms,
        serve_mcp,
        settings,
        sse,
        tools_api,
        user,
        voice,
    )
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    from core.auth import AuthMiddleware
    from core.logging import set_correlation_id

    class CorrelationIdMiddleware:
        """Middleware to set correlation ID for request tracking."""

        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                # Check for existing correlation ID in headers
                headers = dict(scope.get("headers", []))
                correlation_id = headers.get(b"x-correlation-id", b"").decode("utf-8") or None
                # Set correlation ID for this request context
                set_correlation_id(correlation_id)

            await self.app(scope, receive, send)

    def get_client_ip(request: Request) -> str:
        """
        Get the real client IP address, respecting trusted proxies.

        Uses X-Forwarded-For header when behind a trusted proxy, otherwise
        falls back to the direct connection IP.

        Args:
            request: FastAPI request object

        Returns:
            Client IP address as a string
        """
        trusted_proxy_count = settings.trusted_proxy_count

        if trusted_proxy_count > 0:
            # Check X-Forwarded-For header
            forwarded_for = request.headers.get("x-forwarded-for")
            if forwarded_for:
                # X-Forwarded-For can contain multiple IPs: client, proxy1, proxy2, ...
                # We want the IP at position -(trusted_proxy_count + 1) from the end
                ips = [ip.strip() for ip in forwarded_for.split(",")]
                # Calculate index: if trusted_proxy_count=1, we want the second-to-last
                # which is ips[-2] or len(ips) - 2
                target_index = len(ips) - trusted_proxy_count - 1
                if target_index >= 0:
                    return ips[target_index]
                # If not enough IPs, use the first one (likely the real client)
                return ips[0]

        # No proxy configured or no X-Forwarded-For, use direct connection IP
        if request.client:
            return request.client.host
        return "127.0.0.1"

    # Body size limit middleware (10MB max)
    MAX_BODY_SIZE = 10 * 1024 * 1024  # 10MB

    class BodySizeLimitMiddleware:
        """Middleware to limit request body size to prevent memory exhaustion."""

        def __init__(self, app, max_size: int = MAX_BODY_SIZE):
            self.app = app
            self.max_size = max_size

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return

            content_length = None
            for header_name, header_value in scope.get("headers", []):
                if header_name == b"content-length":
                    try:
                        content_length = int(header_value.decode())
                    except (ValueError, UnicodeDecodeError):
                        pass
                    break

            # Reject if Content-Length exceeds limit
            if content_length is not None and content_length > self.max_size:
                response_body = b'{"detail":"Request body too large"}'
                await send(
                    {
                        "type": "http.response.start",
                        "status": 413,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(response_body)).encode()),
                        ],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": response_body,
                    }
                )
                return

            await self.app(scope, receive, send)

    settings = get_settings()

    # Create lifespan context manager
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Lifespan context manager for application startup and shutdown."""
        # Startup
        logger.info("🚀 Application startup...")

        # Validate configuration files
        from core import log_config_validation

        log_config_validation()

        # Initialize database
        await init_db()

        # Create singleton instances
        agent_manager = AgentManager()
        event_broadcaster = EventBroadcaster()
        agent_manager.set_event_broadcaster(event_broadcaster)

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
        app.state.event_broadcaster = event_broadcaster

        # Seed agents from config files
        async for db in get_db():
            await crud.seed_agents_from_configs(db)
            break

        # Start background scheduler
        background_scheduler.start()

        # Initialize Codex App Server pool (lazy - instances created on demand)
        codex_server_pool = None
        try:
            from providers.codex import CodexAppServerPool

            logger.info("🔧 Initializing Codex App Server pool...")
            codex_server_pool = await CodexAppServerPool.get_instance()
            pool_stats = codex_server_pool.get_stats()
            logger.info(
                f"✅ Codex App Server pool ready "
                f"(max_instances: {pool_stats['max_instances']}, "
                f"idle_timeout: {pool_stats['idle_timeout']}s)"
            )
        except Exception as e:
            logger.warning(f"⚠️ Failed to initialize Codex App Server pool: {e}")
            logger.warning("   Codex provider will not be available")

        logger.info("✅ Application startup complete")

        yield

        # Shutdown
        logger.info("🛑 Application shutdown...")

        try:
            # Shutdown SSE connections first (allows clients to disconnect gracefully)
            await event_broadcaster.shutdown()

            # Shutdown Codex server pool if it was started
            if codex_server_pool is not None:
                try:
                    logger.info("🔧 Shutting down Codex server pool...")
                    await codex_server_pool.shutdown()
                    logger.info("✅ Codex server pool shutdown complete")
                except asyncio.CancelledError:
                    logger.info("⚠️ Codex server pool shutdown interrupted")
                except Exception as e:
                    logger.warning(f"⚠️ Error shutting down Codex server pool: {e}")

            background_scheduler.stop()
            await agent_manager.shutdown()
            await shutdown_db()
            # Use print() for final message - logging system may be shutting down
            print("✅ Application shutdown complete", flush=True)

        except asyncio.CancelledError:
            # Shutdown was interrupted by Ctrl+C - this is expected
            logger.info("⚠️ Shutdown interrupted, cleaning up...")
            background_scheduler.stop()
            # Force kill any remaining Codex processes
            if codex_server_pool is not None:
                for instance in list(codex_server_pool._instances.values()):
                    if instance.is_healthy:
                        try:
                            instance.kill()
                        except Exception:
                            pass
            # Use print() for final message - logging system may be shutting down
            print("✅ Emergency cleanup complete", flush=True)

    # Initialize rate limiter
    limiter = Limiter(key_func=get_client_ip)

    # Create app with lifespan
    app = FastAPI(title="ChitChats API", lifespan=lifespan)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Add body size limit middleware FIRST (processes last, rejects huge requests early)
    app.add_middleware(BodySizeLimitMiddleware, max_size=MAX_BODY_SIZE)

    # Add correlation ID middleware for request tracking
    app.add_middleware(CorrelationIdMiddleware)

    # Add authentication middleware (will process after CORS)
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
    app.include_router(sse.router, prefix="/rooms", tags=["SSE"])
    app.include_router(debug.router, prefix="/debug", tags=["Debug"])
    app.include_router(providers.router, tags=["Providers"])
    app.include_router(exports.router, prefix="/exports", tags=["Exports"])
    app.include_router(voice.router, prefix="/voice", tags=["Voice"])
    app.include_router(user.router, prefix="/user", tags=["User"])
    app.include_router(settings.router, prefix="/settings", tags=["Settings"])
    app.include_router(tools_api.router, tags=["Tools"])
    app.include_router(serve_mcp.router, tags=["MCP Tools"])

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
            logger.info(f"📦 Serving static files from: {static_dir}")

            # Catch-all route for SPA - must be last
            @app.get("/{full_path:path}")
            async def serve_spa(full_path: str):
                """Serve static files if they exist, otherwise index.html for SPA routing."""
                # Check if it's an API route (already handled by routers)
                if full_path.startswith(("api/", "auth/", "rooms/", "agents/", "debug/", "mcp")):
                    return None

                # Serve actual static files (fonts, images, assets, manifest, etc.)
                static_file = static_dir / full_path
                if full_path and static_file.exists() and static_file.is_file():
                    return FileResponse(static_file)

                # Fall back to index.html for SPA routes
                return FileResponse(static_dir / "index.html")
        else:
            logger.warning(f"⚠️ Static files directory not found: {static_dir}")

    return app
