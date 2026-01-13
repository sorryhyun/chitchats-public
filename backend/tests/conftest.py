"""
Pytest configuration and shared fixtures for backend tests.

This module provides test fixtures for database sessions, test clients,
authentication, and commonly used test data.
"""

import asyncio
import shutil
import sys
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Add backend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import Base, get_db
from infrastructure.database.models import Agent, Message, Room
from main import app
from orchestration import ChatOrchestrator
from core import AgentManager


# Configure pytest-asyncio
@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_agents_dir(tmp_path_factory) -> Path:
    """
    Session-scoped temporary directory for all test agent configs.

    This prevents tests from polluting the real agents/ directory.
    """
    return tmp_path_factory.mktemp("agents")


@pytest.fixture(autouse=True, scope="session")
def cleanup_test_agents():
    """
    Safety net: cleanup any test directories in real agents/ folder.

    Runs after ALL tests complete and removes directories matching test patterns.
    """
    real_agents_dir = Path(__file__).parent.parent.parent / "agents"
    existing_before: set[str] = set()
    if real_agents_dir.exists():
        existing_before = {d.name for d in real_agents_dir.iterdir() if d.is_dir()}

    yield

    # Cleanup test patterns after all tests
    test_patterns = ["agent_", "group_test", "test_agent", "new_agent"]
    if real_agents_dir.exists():
        for item in real_agents_dir.iterdir():
            if not item.is_dir():
                continue
            # Skip directories that existed before tests
            if item.name in existing_before:
                continue
            # Check if name matches any test pattern
            if any(item.name.startswith(p) for p in test_patterns):
                shutil.rmtree(item, ignore_errors=True)


@pytest.fixture(autouse=True)
def redirect_agents_dir(test_agents_dir, monkeypatch):
    """
    Redirect agent filesystem operations to temp directory.

    This ensures tests don't create files in the real agents/ directory.
    """
    from core.settings import Settings, reset_settings

    def mock_agents_dir(self) -> Path:
        return test_agents_dir

    monkeypatch.setattr(Settings, "agents_dir", property(mock_agents_dir))
    reset_settings()
    yield
    reset_settings()


@pytest.fixture(scope="function")
async def test_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Create a fresh test database for each test function.

    Uses an in-memory SQLite database that is created and destroyed
    for each test to ensure isolation.
    """
    # Use in-memory SQLite for tests
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", echo=False, connect_args={"check_same_thread": False}
    )

    # Create tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    TestingSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async with TestingSessionLocal() as session:
        yield session

    # Drop tables after test
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await test_engine.dispose()


def _setup_app_state():
    """Set up app state with mock instances for testing."""
    if not hasattr(app.state, "agent_manager") or app.state.agent_manager is None:
        from core.client_pool import ClientPool

        app.state.agent_manager = MagicMock(spec=AgentManager)
        app.state.agent_manager.shutdown = AsyncMock()
        # Set up client_pool mock with necessary methods
        app.state.agent_manager.client_pool = MagicMock(spec=ClientPool)
        app.state.agent_manager.client_pool.remove_agent_from_room = MagicMock()
    if not hasattr(app.state, "chat_orchestrator") or app.state.chat_orchestrator is None:
        app.state.chat_orchestrator = MagicMock(spec=ChatOrchestrator)
    if not hasattr(app.state, "background_scheduler") or app.state.background_scheduler is None:
        app.state.background_scheduler = MagicMock()


@pytest.fixture(scope="function")
async def client(test_db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Create a test client with authentication bypassed.

    This fixture overrides the database dependency to use the test database
    and removes authentication middleware for easier testing.
    """
    # Set up app state
    _setup_app_state()

    # Override the get_db dependency to use test database
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db

    # Create test client
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Clean up
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
async def authenticated_client(test_db: AsyncSession) -> AsyncGenerator[tuple[AsyncClient, str], None]:
    """
    Create a test client with a valid JWT token.

    Returns:
        tuple: (AsyncClient, token) - The test client and the JWT token
    """
    from core.auth import generate_jwt_token

    # Set up app state
    _setup_app_state()

    # Override the get_db dependency to use test database
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db

    # Generate a valid JWT token
    token = generate_jwt_token(role="admin", user_id="admin")

    # Create test client with auth header
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers={"X-API-Key": token}) as ac:
        yield ac, token

    # Clean up
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
async def guest_client(test_db: AsyncSession) -> AsyncGenerator[tuple[AsyncClient, str], None]:
    """
    Create a test client with a valid guest JWT token.

    Returns:
        tuple: (AsyncClient, token) - The test client and the JWT token
    """
    from core.auth import generate_jwt_token

    # Set up app state
    _setup_app_state()

    # Override the get_db dependency to use test database
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db

    # Generate a valid JWT token with guest role
    token = generate_jwt_token(role="guest", user_id="guest-test")

    # Create test client with auth header
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers={"X-API-Key": token}) as ac:
        yield ac, token

    # Clean up
    app.dependency_overrides.clear()


@pytest.fixture
async def sample_agent(test_db: AsyncSession) -> Agent:
    """Create a sample agent for testing."""
    agent = Agent(
        name="test_agent",
        group="test_group",
        config_file="agents/test_agent.md",
        in_a_nutshell="A test agent for testing purposes",
        characteristics="Friendly and helpful",
        recent_events="Just created",
        system_prompt="You are a test agent.",
        is_critic=False,
    )
    test_db.add(agent)
    await test_db.commit()
    await test_db.refresh(agent)
    return agent


@pytest.fixture
async def sample_room(test_db: AsyncSession) -> Room:
    """Create a sample room for testing."""
    room = Room(name="test_room", max_interactions=None, is_paused=False, owner_id="admin")
    test_db.add(room)
    await test_db.commit()
    await test_db.refresh(room)
    return room


@pytest.fixture
async def sample_room_with_agents(
    test_db: AsyncSession, sample_room: Room, sample_agent: Agent
) -> Room:
    """Create a sample room with agents."""
    # Refresh to ensure we have the agents relationship loaded
    await test_db.refresh(sample_room, ["agents"])
    sample_room.agents.append(sample_agent)
    await test_db.commit()
    await test_db.refresh(sample_room, ["agents"])
    return sample_room


@pytest.fixture
async def sample_message(test_db: AsyncSession, sample_room: Room, sample_agent: Agent) -> Message:
    """Create a sample message for testing."""
    message = Message(
        room_id=sample_room.id,
        agent_id=sample_agent.id,
        content="This is a test message",
        role="assistant",
        thinking="Test thinking process",
    )
    test_db.add(message)
    await test_db.commit()
    await test_db.refresh(message)
    return message


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set up mock environment variables for testing."""
    from core import reset_settings

    # Mock API key hash (bcrypt hash of "test_password")
    test_hash = "$2b$12$H0fCIM9buSuQsCFErTRi0Omz//QVZxCKJW5Dapi2u3ealuUFzvF9O"
    monkeypatch.setenv("API_KEY_HASH", test_hash)

    # Mock JWT secret
    monkeypatch.setenv("JWT_SECRET", "test_secret_key_for_testing_only")

    # Disable guest login for most tests
    monkeypatch.setenv("ENABLE_GUEST_LOGIN", "false")

    # Reset settings cache so new env vars are picked up
    reset_settings()

    return {
        "api_key_hash": test_hash,
        "jwt_secret": "test_secret_key_for_testing_only",
        "test_password": "test_password",
    }


@pytest.fixture
def temp_agent_config(test_agents_dir):
    """Create a temporary agent configuration directory using the test agents dir."""
    agent_dir = test_agents_dir / "test_agent"
    agent_dir.mkdir(parents=True, exist_ok=True)

    # Create config files
    (agent_dir / "in_a_nutshell.md").write_text("Test agent nutshell")
    (agent_dir / "characteristics.md").write_text("Test characteristics")
    (agent_dir / "recent_events.md").write_text("Test recent events")

    return agent_dir
