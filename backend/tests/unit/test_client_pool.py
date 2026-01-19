"""
Tests for ClientPool - Claude SDK client lifecycle management.

This module tests the ClientPool class which manages pooling and lifecycle
of ClaudeSDKClient instances.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from core.client_pool import ClientPool
from domain.task_identifier import TaskIdentifier


@pytest.fixture
def client_pool():
    """Create a fresh ClientPool instance for each test."""
    return ClientPool()


@pytest.fixture
def mock_options():
    """Create a mock ClaudeAgentOptions."""
    options = Mock()
    options.resume = None
    return options


@pytest.fixture
def mock_client():
    """Create a mock ClaudeSDKClient."""
    client = AsyncMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.options = Mock()
    client.options.resume = None
    return client


@pytest.mark.asyncio
async def test_get_or_create_new_client(client_pool, mock_options):
    """Test creating a new client."""
    task_id = TaskIdentifier(room_id=1, agent_id=2)

    with patch("core.client_pool.ClaudeSDKClient") as mock_sdk_client_class:
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.options = mock_options
        mock_sdk_client_class.return_value = mock_client

        client, is_new = await client_pool.get_or_create(task_id, mock_options)

        assert is_new is True
        assert task_id in client_pool.pool
        assert client_pool.pool[task_id] == mock_client
        mock_client.connect.assert_called_once()


@pytest.mark.asyncio
async def test_get_or_create_reuse_existing(client_pool, mock_options):
    """Test reusing existing client."""
    task_id = TaskIdentifier(room_id=1, agent_id=2)

    with patch("core.client_pool.ClaudeSDKClient") as mock_sdk_client_class:
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.options = mock_options
        mock_sdk_client_class.return_value = mock_client

        # First call - creates new client
        client1, is_new1 = await client_pool.get_or_create(task_id, mock_options)

        # Second call - should reuse
        client2, is_new2 = await client_pool.get_or_create(task_id, mock_options)

        assert is_new1 is True
        assert is_new2 is False
        assert client1 is client2
        # Connect should only be called once (for the new client)
        assert mock_client.connect.call_count == 1


@pytest.mark.asyncio
async def test_session_change_triggers_new_client(client_pool):
    """Test that session change triggers new client creation."""
    task_id = TaskIdentifier(room_id=1, agent_id=2)

    # First options with no session
    options1 = Mock()
    options1.resume = None

    # Second options with session ID
    options2 = Mock()
    options2.resume = "sess_123"

    with patch("core.client_pool.ClaudeSDKClient") as mock_sdk_client_class:
        mock_client1 = AsyncMock()
        mock_client1.connect = AsyncMock()
        mock_client1.disconnect = AsyncMock()
        mock_client1.options = options1

        mock_client2 = AsyncMock()
        mock_client2.connect = AsyncMock()
        mock_client2.options = options2

        mock_sdk_client_class.side_effect = [mock_client1, mock_client2]

        # First call - creates client with no session
        client1, is_new1 = await client_pool.get_or_create(task_id, options1)
        assert is_new1 is True

        # Second call - session changed, should create new client
        client2, is_new2 = await client_pool.get_or_create(task_id, options2)
        assert is_new2 is True
        assert client1 is not client2

        # First client should have been cleaned up
        # Note: disconnect is called in background task, so we can't easily assert it here


@pytest.mark.asyncio
async def test_cleanup_client(client_pool, mock_options):
    """Test cleanup removes client and schedules disconnect."""
    task_id = TaskIdentifier(room_id=1, agent_id=2)

    with patch("core.client_pool.ClaudeSDKClient") as mock_sdk_client_class:
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()
        mock_client.options = mock_options
        mock_sdk_client_class.return_value = mock_client

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
async def test_cleanup_room(client_pool, mock_options):
    """Test cleanup all clients in a room."""
    task1 = TaskIdentifier(room_id=1, agent_id=1)
    task2 = TaskIdentifier(room_id=1, agent_id=2)
    task3 = TaskIdentifier(room_id=2, agent_id=1)

    with patch("core.client_pool.ClaudeSDKClient") as mock_sdk_client_class:
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()
        mock_client.options = mock_options
        mock_sdk_client_class.return_value = mock_client

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
async def test_get_keys_for_agent(client_pool, mock_options):
    """Test filtering pool keys by agent_id."""
    task1 = TaskIdentifier(room_id=1, agent_id=5)
    task2 = TaskIdentifier(room_id=2, agent_id=5)
    task3 = TaskIdentifier(room_id=1, agent_id=6)

    with patch("core.client_pool.ClaudeSDKClient") as mock_sdk_client_class:
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.options = mock_options
        mock_sdk_client_class.return_value = mock_client

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

    with patch("core.client_pool.ClaudeSDKClient") as mock_sdk_client_class:
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()
        mock_client.options = mock_options
        mock_sdk_client_class.return_value = mock_client

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

    async def mock_connect_delay():
        """Mock connect with delay to simulate race condition."""
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)  # Small delay to allow concurrent calls

    with patch("core.client_pool.ClaudeSDKClient") as mock_sdk_client_class:
        mock_client = AsyncMock()
        mock_client.connect = mock_connect_delay
        mock_client.options = mock_options
        mock_sdk_client_class.return_value = mock_client

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
async def test_retry_on_process_transport_error(client_pool, mock_options):
    """Test retry logic for ProcessTransport errors."""
    task_id = TaskIdentifier(room_id=1, agent_id=2)

    with patch("core.client_pool.ClaudeSDKClient") as mock_sdk_client_class:
        # First two attempts fail with ProcessTransport error
        mock_client1 = AsyncMock()
        mock_client1.connect = AsyncMock(side_effect=Exception("ProcessTransport is not ready for writing"))

        mock_client2 = AsyncMock()
        mock_client2.connect = AsyncMock(side_effect=Exception("ProcessTransport is not ready for writing"))

        # Third attempt succeeds
        mock_client3 = AsyncMock()
        mock_client3.connect = AsyncMock()
        mock_client3.options = mock_options

        mock_sdk_client_class.side_effect = [mock_client1, mock_client2, mock_client3]

        # Should succeed on third attempt
        client, is_new = await client_pool.get_or_create(task_id, mock_options)

        assert is_new is True
        assert task_id in client_pool.pool
        # Should have tried 3 times
        assert mock_sdk_client_class.call_count == 3


@pytest.mark.asyncio
async def test_retry_exhausted_raises_error(client_pool, mock_options):
    """Test that retries exhausted raises the error."""
    task_id = TaskIdentifier(room_id=1, agent_id=2)

    with patch("core.client_pool.ClaudeSDKClient") as mock_sdk_client_class:
        # All attempts fail
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock(side_effect=Exception("ProcessTransport is not ready for writing"))
        mock_sdk_client_class.return_value = mock_client

        # Should raise after max retries
        with pytest.raises(Exception, match="ProcessTransport is not ready"):
            await client_pool.get_or_create(task_id, mock_options)


@pytest.mark.asyncio
async def test_non_transport_error_raises_immediately(client_pool, mock_options):
    """Test that non-transport errors raise immediately without retry."""
    task_id = TaskIdentifier(room_id=1, agent_id=2)

    with patch("core.client_pool.ClaudeSDKClient") as mock_sdk_client_class:
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock(side_effect=ValueError("Invalid options"))
        mock_sdk_client_class.return_value = mock_client

        # Should raise immediately, not retry
        with pytest.raises(ValueError, match="Invalid options"):
            await client_pool.get_or_create(task_id, mock_options)

        # Should only be called once (no retries)
        assert mock_sdk_client_class.call_count == 1


@pytest.mark.asyncio
async def test_keys_method_returns_pool_keys(client_pool, mock_options):
    """Test that keys() method returns pool keys."""
    task1 = TaskIdentifier(room_id=1, agent_id=1)
    task2 = TaskIdentifier(room_id=2, agent_id=2)

    with patch("core.client_pool.ClaudeSDKClient") as mock_sdk_client_class:
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.options = mock_options
        mock_sdk_client_class.return_value = mock_client

        await client_pool.get_or_create(task1, mock_options)
        await client_pool.get_or_create(task2, mock_options)

        keys = client_pool.keys()

        assert task1 in keys
        assert task2 in keys
        assert len(list(keys)) == 2
