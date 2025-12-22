import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

logger = logging.getLogger(__name__)

# PostgreSQL connection URL from environment variable
# Format: postgresql+asyncpg://user:password@host:port/database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/chitchats")

# Configure engine with connection pooling for PostgreSQL
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verify connections before use
    pool_recycle=3600,  # Recycle connections after 1 hour
)

# Session factory with sensible defaults
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

Base = declarative_base()


async def get_db():
    """Yield a database session for dependency injection."""
    async with async_session_maker() as session:
        yield session


async def init_db():
    """
    Initialize database schema and run migrations.

    This function:
    1. Creates all tables if they don't exist (for fresh installs)
    2. Runs migrations to add missing columns (for upgrades)
    """
    from infrastructure.database.migrations import run_migrations

    # Create any missing tables first (for fresh installs)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Then run migrations to add any missing columns to existing tables
    await run_migrations(engine)


# =============================================================================
# PostgreSQL Compatibility Layer
# =============================================================================
# These functions were originally needed for SQLite's limited concurrency.
# PostgreSQL handles concurrent writes natively, so these are now no-ops.
# Kept to avoid breaking existing code that imports them.


def retry_on_db_lock(max_retries=5, initial_delay=0.1, backoff_factor=2):
    """No-op decorator. PostgreSQL handles concurrency natively."""

    def decorator(func):
        return func

    return decorator


class SerializedWrite:
    """No-op async context manager. PostgreSQL handles concurrency natively."""

    def __init__(self, lock_key=None):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


def serialized_write(lock_key=None) -> SerializedWrite:
    """No-op context manager. PostgreSQL handles concurrency natively."""
    return SerializedWrite(lock_key)


async def serialized_commit(db: AsyncSession, lock_key=None) -> None:
    """Direct commit. PostgreSQL handles concurrency natively."""
    await db.commit()
