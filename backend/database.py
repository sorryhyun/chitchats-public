"""
Database configuration with lazy initialization and SQLite support.

This module provides:
- Lazy engine initialization (only connects when first used)
- Automatic SQLite detection on Windows or when USE_SQLITE=true
- Connection pooling for PostgreSQL
- No pooling for SQLite (uses single connection)

URL Priority:
1. DATABASE_URL environment variable
2. USE_SQLITE=true environment variable
3. Windows auto-detection (defaults to SQLite)
4. PostgreSQL default for Linux/Mac
"""

import logging
import os
import platform
import sys
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

logger = logging.getLogger(__name__)

# Lazy-initialized globals
_engine: Optional[AsyncEngine] = None
_session_maker: Optional[async_sessionmaker] = None

# Declarative base for models
Base = declarative_base()


def _get_work_dir() -> Path:
    """Get the working directory for data files (handles bundled mode)."""
    if getattr(sys, "frozen", False):
        # Running as PyInstaller bundle - use exe directory
        return Path(sys.executable).parent
    else:
        # Running in development - use project root
        return Path(__file__).parent.parent


def _get_database_url() -> str:
    """
    Get the database URL with automatic fallback logic.

    Priority:
    1. DATABASE_URL environment variable
    2. USE_SQLITE=true environment variable → SQLite
    3. Windows platform → SQLite (easier setup)
    4. PostgreSQL default
    """
    # Check for explicit DATABASE_URL
    if db_url := os.getenv("DATABASE_URL"):
        return db_url

    # Check for explicit SQLite request
    if os.getenv("USE_SQLITE", "").lower() == "true":
        work_dir = _get_work_dir()
        return f"sqlite+aiosqlite:///{work_dir}/chitchats.db"

    # Auto-detect Windows → use SQLite for easier development
    if platform.system() == "Windows":
        work_dir = _get_work_dir()
        return f"sqlite+aiosqlite:///{work_dir}/chitchats.db"

    # Default to PostgreSQL
    return "postgresql+asyncpg://postgres:postgres@localhost:5432/chitchats"


def _create_engine() -> AsyncEngine:
    """Create the async engine with appropriate settings."""
    url = _get_database_url()

    if "sqlite" in url:
        logger.info(f"🗄️ Using SQLite database: {url}")
        # SQLite: no pooling, use check_same_thread=False for async
        return create_async_engine(
            url,
            echo=False,
            connect_args={"check_same_thread": False},
        )
    else:
        logger.info("🐘 Using PostgreSQL database")
        # PostgreSQL: connection pooling
        return create_async_engine(
            url,
            echo=False,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
        )


def get_engine() -> AsyncEngine:
    """Get or create the database engine (lazy initialization)."""
    global _engine
    if _engine is None:
        _engine = _create_engine()
    return _engine


def get_session_maker() -> async_sessionmaker:
    """Get or create the session maker (lazy initialization)."""
    global _session_maker
    if _session_maker is None:
        _session_maker = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_maker


async def get_db():
    """Yield a database session for dependency injection."""
    session_maker = get_session_maker()
    async with session_maker() as session:
        yield session


async def init_db():
    """
    Initialize database schema and run migrations.

    This function:
    1. Creates all tables if they don't exist (for fresh installs)
    2. Runs migrations to add missing columns (for upgrades)
    """
    from infrastructure.database.migrations import run_migrations

    engine = get_engine()

    # Create any missing tables first (for fresh installs)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Then run migrations to add any missing columns to existing tables
    await run_migrations(engine)


async def shutdown_db():
    """Dispose database engine and close all connections."""
    global _engine, _session_maker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_maker = None
        logger.info("🗄️ Database engine disposed")


def is_sqlite() -> bool:
    """Check if we're using SQLite."""
    return "sqlite" in _get_database_url()


# Legacy compatibility exports (for infrastructure.database.connection import pattern)
engine = property(lambda self: get_engine())
async_session_maker = property(lambda self: get_session_maker())


# =============================================================================
# SQLite Concurrency Helpers
# =============================================================================
# These are re-implemented here for SQLite support while remaining no-ops
# for PostgreSQL.


def retry_on_db_lock(max_retries=5, initial_delay=0.1, backoff_factor=2):
    """
    Decorator to retry on database lock errors (SQLite only).
    No-op for PostgreSQL which handles concurrency natively.
    """
    import asyncio
    import functools

    def decorator(func):
        if not is_sqlite():
            return func

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            delay = initial_delay
            last_error = None

            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if "database is locked" in str(e).lower():
                        last_error = e
                        await asyncio.sleep(delay)
                        delay *= backoff_factor
                    else:
                        raise

            raise last_error

        return wrapper

    return decorator


class SerializedWrite:
    """
    Async context manager for serialized writes (SQLite only).
    No-op for PostgreSQL which handles concurrency natively.
    """

    _lock = None

    def __init__(self, lock_key=None):
        self.lock_key = lock_key

    async def __aenter__(self):
        if is_sqlite():
            import asyncio

            if SerializedWrite._lock is None:
                SerializedWrite._lock = asyncio.Lock()
            await SerializedWrite._lock.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if is_sqlite() and SerializedWrite._lock is not None:
            SerializedWrite._lock.release()
        return False


def serialized_write(lock_key=None) -> SerializedWrite:
    """Create a serialized write context manager."""
    return SerializedWrite(lock_key)


async def serialized_commit(db: AsyncSession, lock_key=None) -> None:
    """Commit with optional serialization for SQLite."""
    if is_sqlite():
        async with serialized_write(lock_key):
            await db.commit()
    else:
        await db.commit()
