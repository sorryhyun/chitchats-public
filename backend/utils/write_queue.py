"""
Single Writer Pattern for SQLite.

This module provides a centralized write queue that serializes all database
writes through a single background task. This eliminates SQLite write contention
when multiple concurrent operations try to write simultaneously.

Usage:
    from utils.write_queue import enqueue_write, start_writer, stop_writer

    # At app startup
    await start_writer()

    # For writes
    result = await enqueue_write(my_write_coroutine())

    # At app shutdown
    await stop_writer()
"""

import asyncio
import logging
from typing import Awaitable, TypeVar

logger = logging.getLogger("WriteQueue")

T = TypeVar("T")

# Global write queue and control
_write_queue: asyncio.Queue | None = None
_writer_task: asyncio.Task | None = None
_shutdown_event: asyncio.Event | None = None


class WriteOperation:
    """Wrapper for a write operation with its result future."""

    def __init__(self, coro: Awaitable[T]):
        self.coro = coro
        self.future: asyncio.Future[T] = asyncio.get_event_loop().create_future()


async def _writer_loop():
    """
    Background task that processes write operations sequentially.

    This ensures only one write happens at a time, eliminating SQLite lock contention.
    """
    global _write_queue, _shutdown_event

    logger.info("Write queue started - all DB writes will be serialized")

    while True:
        try:
            # Wait for a write operation with timeout to check shutdown
            try:
                op: WriteOperation = await asyncio.wait_for(
                    _write_queue.get(),
                    timeout=1.0,
                )
            except asyncio.TimeoutError:
                # Check if we should shut down
                if _shutdown_event and _shutdown_event.is_set():
                    # Drain remaining operations before exiting
                    while not _write_queue.empty():
                        try:
                            op = _write_queue.get_nowait()
                            try:
                                result = await op.coro
                                op.future.set_result(result)
                            except Exception as e:
                                op.future.set_exception(e)
                        except asyncio.QueueEmpty:
                            break
                    logger.info("Write queue shut down gracefully")
                    return
                continue

            # Execute the write operation
            try:
                result = await op.coro
                op.future.set_result(result)
            except Exception as e:
                logger.error(f"Write operation failed: {e}")
                op.future.set_exception(e)

            _write_queue.task_done()

        except asyncio.CancelledError:
            logger.info("Write queue cancelled")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in writer loop: {e}")
            # Continue processing - don't let one error stop the queue


async def start_writer():
    """Start the background writer task."""
    global _write_queue, _writer_task, _shutdown_event

    if _writer_task is not None and not _writer_task.done():
        logger.warning("Writer task already running")
        return

    _write_queue = asyncio.Queue()
    _shutdown_event = asyncio.Event()
    _writer_task = asyncio.create_task(_writer_loop())
    logger.info("Write queue initialized")


async def stop_writer(timeout: float = 10.0):
    """
    Stop the background writer task gracefully.

    Args:
        timeout: Maximum time to wait for pending writes to complete
    """
    global _writer_task, _shutdown_event, _write_queue

    if _writer_task is None:
        return

    logger.info("Stopping write queue...")
    _shutdown_event.set()

    try:
        await asyncio.wait_for(_writer_task, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(f"Write queue didn't stop within {timeout}s, cancelling...")
        _writer_task.cancel()
        try:
            await _writer_task
        except asyncio.CancelledError:
            pass

    _writer_task = None
    _write_queue = None
    _shutdown_event = None
    logger.info("Write queue stopped")


async def enqueue_write(coro: Awaitable[T]) -> T:
    """
    Enqueue a write operation and wait for its result.

    This function queues the coroutine to be executed by the single writer task,
    ensuring serialized writes to SQLite.

    Args:
        coro: The coroutine to execute (should be a DB write operation)

    Returns:
        The result of the coroutine

    Raises:
        RuntimeError: If the writer task is not running
        Any exception raised by the coroutine
    """
    global _write_queue

    if _write_queue is None:
        # Fallback: execute directly if queue not initialized
        # This should only happen during tests or startup issues
        logger.error(
            "Write queue not initialized - executing write directly. "
            "This may cause SQLite contention issues in production. "
            "Ensure start_writer() is called during app startup."
        )
        return await coro

    op = WriteOperation(coro)
    await _write_queue.put(op)

    # Wait for the write to complete
    return await op.future


def is_writer_running() -> bool:
    """Check if the writer task is running."""
    return _writer_task is not None and not _writer_task.done()


def get_queue_size() -> int:
    """Get the current number of pending writes."""
    if _write_queue is None:
        return 0
    return _write_queue.qsize()
