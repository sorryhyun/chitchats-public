"""
Tests for ClientPool - AI client lifecycle management.

This module tests the BaseClientPool class and provider-specific pools
which manage pooling and lifecycle of AIClient instances.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from domain.task_identifier import TaskIdentifier
from core.client_pool import BaseClientPool
from providers.base import AIClient


class TestClientPool(BaseClientPool):
    """Concrete test implementation of BaseClientPool."""

    def __init__(self):
        super().__init__()
        self.create_client_mock = AsyncMock()
        self.created_clients = []

    async def _create_client(self, options) -> AIClient:
        """Create a mock client for testing."""
        client = await self.create_client_mock(options)
        self.created_clients.append(client)
        return client


@pytest.fixture
def client_pool():
    """Create a fresh TestClientPool instance for each test."""
    return TestClientPool()


@pytest.fixture
def mock_options():
    """Create a mock options object."""
    options = Mock()
    options.resume = None
    options.thread_id = None
    return options


@pytest.fixture
def mock_client():
    """Create a mock AIClient."""
    client = AsyncMock(spec=AIClient)
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.options = Mock()
    client.options.resume = None
    return client


@pytest.mark.asyncio
async def test_get_or_create_new_client(client_pool, mock_options, mock_client):
    """Test creating a new client."""
    task_id = TaskIdentifier(room_id=1, agent_id=2)

    # Configure mock to return the mock client
    mock_client.options = mock_options
    client_pool.create_client_mock.return_value = mock_client

    client, is_new = await client_pool.get_or_create(task_id, mock_options)

    assert is_new is True
    assert task_id in client_pool.pool
    assert client_pool.pool[task_id] == mock_client
    client_pool.create_client_mock.assert_called_once_with(mock_options)


@pytest.mark.asyncio
async def test_get_or_create_reuse_existing(client_pool, mock_options, mock_client):
    """Test reusing existing client."""
    task_id = TaskIdentifier(room_id=1, agent_id=2)

    mock_client.options = mock_options
    client_pool.create_client_mock.return_value = mock_client

    # First call - creates new client
    client1, is_new1 = await client_pool.get_or_create(task_id, mock_options)

    # Second call - should reuse
    client2, is_new2 = await client_pool.get_or_create(task_id, mock_options)

    assert is_new1 is True
    assert is_new2 is False
    assert client1 is client2
    # _create_client should only be called once
    assert client_pool.create_client_mock.call_count == 1


@pytest.mark.asyncio
async def test_session_change_triggers_new_client(client_pool):
    """Test that session change triggers new client creation."""
    task_id = TaskIdentifier(room_id=1, agent_id=2)

    # First options with no session
    options1 = Mock()
    options1.resume = None
    options1.thread_id = None

    # Second options with session ID
    options2 = Mock()
    options2.resume = "sess_123"
    options2.thread_id = None

    # Create two different mock clients
    mock_client1 = AsyncMock(spec=AIClient)
    mock_client1.options = options1

    mock_client2 = AsyncMock(spec=AIClient)
    mock_client2.options = options2

    client_pool.create_client_mock.side_effect = [mock_client1, mock_client2]

    # First call - creates client with no session
    client1, is_new1 = await client_pool.get_or_create(task_id, options1)
    assert is_new1 is True

    # Second call - session changed, should create new client
    client2, is_new2 = await client_pool.get_or_create(task_id, options2)
    assert is_new2 is True
    assert client1 is not client2


@pytest.mark.asyncio
async def test_cleanup_client(client_pool, mock_options, mock_client):
    """Test cleanup removes client and schedules disconnect."""
    task_id = TaskIdentifier(room_id=1, agent_id=2)

    mock_client.options = mock_options
    client_pool.create_client_mock.return_value = mock_client

    # Create a client
    client, _ = await client_pool.get_or_create(task_id, mock_options)

    # Cleanup the client
    await client_pool.cleanup(task_id)

    # Client should be removed from pool immediately
    assert task_id not in client_pool.pool

    # Wait a bit for background task to run
    await asyncio.sleep(0.1)

    # Disconnect should be called (in background task)
    mock_client.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_nonexistent_client(client_pool):
    """Test cleanup of nonexistent client doesn't raise error."""
    task_id = TaskIdentifier(room_id=1, agent_id=2)

    # Should not raise exception
    await client_pool.cleanup(task_id)


@pytest.mark.asyncio
async def test_cleanup_room(client_pool, mock_options, mock_client):
    """Test cleanup all clients in a room."""
    task1 = TaskIdentifier(room_id=1, agent_id=1)
    task2 = TaskIdentifier(room_id=1, agent_id=2)
    task3 = TaskIdentifier(room_id=2, agent_id=1)

    mock_client.options = mock_options
    # Return new mock for each call
    client_pool.create_client_mock.side_effect = [
        AsyncMock(spec=AIClient, options=mock_options, disconnect=AsyncMock()),
        AsyncMock(spec=AIClient, options=mock_options, disconnect=AsyncMock()),
        AsyncMock(spec=AIClient, options=mock_options, disconnect=AsyncMock()),
    ]

    # Create clients in different rooms
    await client_pool.get_or_create(task1, mock_options)
    await client_pool.get_or_create(task2, mock_options)
    await client_pool.get_or_create(task3, mock_options)

    # Cleanup room 1
    await client_pool.cleanup_room(room_id=1)

    # Room 1 clients should be removed
    assert task1 not in client_pool.pool
    assert task2 not in client_pool.pool
    # Room 2 client should still exist
    assert task3 in client_pool.pool


@pytest.mark.asyncio
async def test_get_keys_for_agent(client_pool, mock_options, mock_client):
    """Test filtering pool keys by agent_id."""
    task1 = TaskIdentifier(room_id=1, agent_id=5)
    task2 = TaskIdentifier(room_id=2, agent_id=5)
    task3 = TaskIdentifier(room_id=1, agent_id=6)

    mock_client.options = mock_options
    client_pool.create_client_mock.return_value = mock_client

    # Create clients for different agents
    await client_pool.get_or_create(task1, mock_options)
    await client_pool.get_or_create(task2, mock_options)
    await client_pool.get_or_create(task3, mock_options)

    # Get keys for agent 5
    keys = client_pool.get_keys_for_agent(agent_id=5)

    assert len(keys) == 2
    assert task1 in keys
    assert task2 in keys
    assert task3 not in keys


@pytest.mark.asyncio
async def test_shutdown_all(client_pool, mock_options):
    """Test shutdown waits for all cleanup tasks."""
    task1 = TaskIdentifier(room_id=1, agent_id=1)
    task2 = TaskIdentifier(room_id=1, agent_id=2)

    # Return new mock for each call
    client_pool.create_client_mock.side_effect = [
        AsyncMock(spec=AIClient, options=mock_options, disconnect=AsyncMock()),
        AsyncMock(spec=AIClient, options=mock_options, disconnect=AsyncMock()),
    ]

    # Create clients
    await client_pool.get_or_create(task1, mock_options)
    await client_pool.get_or_create(task2, mock_options)

    # Shutdown all
    await client_pool.shutdown_all()

    # Pool should be empty
    assert len(client_pool.pool) == 0
    # Cleanup tasks should be done
    assert len(client_pool._cleanup_tasks) == 0


@pytest.mark.asyncio
async def test_concurrent_client_creation(client_pool, mock_options):
    """Test connection lock prevents race conditions."""
    task_id = TaskIdentifier(room_id=1, agent_id=2)

    call_count = 0

    async def mock_create_client(options):
        """Mock create with delay to simulate race condition."""
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)
        client = AsyncMock(spec=AIClient)
        client.options = options
        return client

    client_pool.create_client_mock = mock_create_client

    # Simulate concurrent calls
    results = await asyncio.gather(
        client_pool.get_or_create(task_id, mock_options),
        client_pool.get_or_create(task_id, mock_options),
        client_pool.get_or_create(task_id, mock_options),
    )

    # Only one should be new, others reused
    new_count = sum(1 for _, is_new in results if is_new)
    assert new_count == 1

    # All should return same client
    clients = [client for client, _ in results]
    assert clients[0] is clients[1] is clients[2]

    # Only one client should be created (due to lock)
    assert call_count == 1


@pytest.mark.asyncio
async def test_disconnect_client_background_with_disconnect_method(client_pool):
    """Test _disconnect_client_background uses disconnect method if available."""
    task_id = TaskIdentifier(room_id=1, agent_id=2)
    mock_client = AsyncMock()
    mock_client.disconnect = AsyncMock()

    await client_pool._disconnect_client_background(mock_client, task_id)

    mock_client.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_disconnect_client_background_with_close_method(client_pool):
    """Test _disconnect_client_background uses close method if disconnect not available."""
    task_id = TaskIdentifier(room_id=1, agent_id=2)
    mock_client = AsyncMock()
    mock_client.close = AsyncMock()
    # Remove disconnect method
    del mock_client.disconnect

    await client_pool._disconnect_client_background(mock_client, task_id)

    mock_client.close.assert_called_once()


@pytest.mark.asyncio
async def test_disconnect_client_background_suppresses_cancel_errors(client_pool):
    """Test _disconnect_client_background suppresses cancel scope errors."""
    task_id = TaskIdentifier(room_id=1, agent_id=2)
    mock_client = AsyncMock()
    mock_client.disconnect = AsyncMock(side_effect=Exception("cancel scope violation"))

    # Should not raise
    await client_pool._disconnect_client_background(mock_client, task_id)


@pytest.mark.asyncio
async def test_disconnect_client_background_logs_other_errors(client_pool):
    """Test _disconnect_client_background logs non-cancel errors."""
    task_id = TaskIdentifier(room_id=1, agent_id=2)
    mock_client = AsyncMock()
    mock_client.disconnect = AsyncMock(side_effect=Exception("Connection failed"))

    # Should not raise, but should log
    with patch("core.client_pool.logger") as mock_logger:
        await client_pool._disconnect_client_background(mock_client, task_id)
        # Warning should be logged for non-cancel errors
        mock_logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_retry_on_process_transport_error(client_pool, mock_options, mock_client):
    """Test retry logic for ProcessTransport errors."""
    task_id = TaskIdentifier(room_id=1, agent_id=2)

    # First two attempts fail with ProcessTransport error
    call_count = 0

    async def mock_create_with_retry(options):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("ProcessTransport is not ready for writing")
        client = AsyncMock(spec=AIClient)
        client.options = options
        return client

    client_pool.create_client_mock = mock_create_with_retry

    # Should succeed on third attempt
    client, is_new = await client_pool.get_or_create(task_id, mock_options)

    assert is_new is True
    assert task_id in client_pool.pool
    # Should have tried 3 times
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_exhausted_raises_error(client_pool, mock_options):
    """Test that retries exhausted raises the error."""
    task_id = TaskIdentifier(room_id=1, agent_id=2)

    async def mock_always_fail(options):
        raise Exception("ProcessTransport is not ready for writing")

    client_pool.create_client_mock = mock_always_fail

    # Should raise after max retries
    with pytest.raises(Exception, match="ProcessTransport is not ready"):
        await client_pool.get_or_create(task_id, mock_options)


@pytest.mark.asyncio
async def test_non_transport_error_raises_immediately(client_pool, mock_options):
    """Test that non-transport errors raise immediately without retry."""
    task_id = TaskIdentifier(room_id=1, agent_id=2)

    call_count = 0

    async def mock_fail_immediately(options):
        nonlocal call_count
        call_count += 1
        raise ValueError("Invalid options")

    client_pool.create_client_mock = mock_fail_immediately

    # Should raise immediately, not retry
    with pytest.raises(ValueError, match="Invalid options"):
        await client_pool.get_or_create(task_id, mock_options)

    # Should only be called once (no retries)
    assert call_count == 1


@pytest.mark.asyncio
async def test_keys_method_returns_pool_keys(client_pool, mock_options, mock_client):
    """Test that keys() method returns pool keys."""
    task1 = TaskIdentifier(room_id=1, agent_id=1)
    task2 = TaskIdentifier(room_id=2, agent_id=2)

    mock_client.options = mock_options
    client_pool.create_client_mock.return_value = mock_client

    await client_pool.get_or_create(task1, mock_options)
    await client_pool.get_or_create(task2, mock_options)

    keys = client_pool.keys()

    assert task1 in keys
    assert task2 in keys
    assert len(list(keys)) == 2
