import logging
import os
import platform
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

logger = logging.getLogger(__name__)

Base = declarative_base()

# Lazy initialization - engine created on first use
_engine = None
_async_session_maker = None


def _is_sqlite_url(url: str) -> bool:
    """Check if a database URL is for SQLite."""
    return "sqlite" in url.lower()


def _get_database_url() -> str:
    """
    Determine the appropriate database URL.

    Priority:
    1. DATABASE_URL environment variable (explicit override)
    2. USE_SQLITE=true environment variable
    3. Windows platform auto-detection -> SQLite
    4. Default to PostgreSQL
    """
    # Check for explicit DATABASE_URL first
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return db_url

    # Check for USE_SQLITE flag or Windows platform
    use_sqlite = os.getenv("USE_SQLITE", "").lower() == "true"
    if use_sqlite or platform.system() == "Windows":
        # Get project root (parent of backend directory)
        project_root = Path(__file__).parent.parent
        sqlite_path = project_root / "chitchats.db"
        return f"sqlite+aiosqlite:///{sqlite_path}"

    # Default to PostgreSQL
    return "postgresql+asyncpg://postgres:postgres@localhost:5432/chitchats"


def get_engine():
    """Get or create the database engine (lazy initialization)."""
    global _engine

    if _engine is None:
        database_url = _get_database_url()
        is_sqlite = _is_sqlite_url(database_url)

        if is_sqlite:
            # SQLite configuration - no connection pooling
            _engine = create_async_engine(
                database_url,
                echo=False,
                connect_args={"check_same_thread": False},
            )
            logger.info(f"Database engine created: SQLite ({database_url})")
        else:
            # PostgreSQL configuration - with connection pooling
            _engine = create_async_engine(
                database_url,
                echo=False,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                pool_recycle=3600,
            )
            logger.info("Database engine created: PostgreSQL (pooled)")

    return _engine


def get_session_maker():
    """Get or create the session maker (lazy initialization)."""
    global _async_session_maker

    if _async_session_maker is None:
        _async_session_maker = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    return _async_session_maker


def is_sqlite() -> bool:
    """Check if the current database is SQLite."""
    return _is_sqlite_url(_get_database_url())


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


# =============================================================================
# Concurrency Utilities
# =============================================================================
# These functions handle database concurrency:
# - PostgreSQL: No-ops (handles concurrency natively)
# - SQLite: Could be re-enabled for write serialization if needed


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
