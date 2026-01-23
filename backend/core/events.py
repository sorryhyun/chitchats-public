"""
Event broadcasting system for Server-Sent Events (SSE).

This module provides the EventBroadcaster class which manages SSE connections
per room and broadcasts streaming events to connected clients in real-time.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator

logger = logging.getLogger("EventBroadcaster")


@dataclass(eq=False)
class SSEConnection:
    """Wraps an asyncio.Queue for a single SSE client."""

    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=100))
    room_id: int = 0
    client_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    async def send(self, event: dict) -> bool:
        """Send an event to this connection.

        Args:
            event: Event dict to send

        Returns:
            True if event was queued, False if queue was full (event dropped)
        """
        try:
            self.queue.put_nowait(event)
            return True
        except asyncio.QueueFull:
            logger.warning(f"SSE queue full for client {self.client_id}, dropping event")
            return False

    async def receive(self) -> dict:
        """Receive the next event from the queue.

        Returns:
            The next event dict
        """
        return await self.queue.get()


class EventBroadcaster:
    """Manages SSE connections per room and broadcasts events.

    Thread-safe with asyncio.Lock for concurrent access to connection registry.
    """

    def __init__(self):
        self._connections: dict[int, set[SSEConnection]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, room_id: int, client_id: str | None = None) -> SSEConnection:
        """Subscribe a client to a room's event stream.

        Args:
            room_id: Room ID to subscribe to
            client_id: Optional client identifier (auto-generated if not provided)

        Returns:
            SSEConnection for receiving events
        """
        connection = SSEConnection(
            room_id=room_id,
            client_id=client_id or uuid.uuid4().hex[:8],
        )

        async with self._lock:
            if room_id not in self._connections:
                self._connections[room_id] = set()
            self._connections[room_id].add(connection)

        logger.info(f"SSE client {connection.client_id} subscribed to room {room_id}")
        return connection

    async def unsubscribe(self, connection: SSEConnection) -> None:
        """Unsubscribe a client from events.

        Args:
            connection: The SSEConnection to remove
        """
        async with self._lock:
            if connection.room_id in self._connections:
                self._connections[connection.room_id].discard(connection)
                if not self._connections[connection.room_id]:
                    del self._connections[connection.room_id]

        logger.info(f"SSE client {connection.client_id} unsubscribed from room {connection.room_id}")

    async def broadcast(self, room_id: int, event: dict) -> int:
        """Broadcast an event to all clients subscribed to a room.

        Args:
            room_id: Room ID to broadcast to
            event: Event dict to send

        Returns:
            Number of clients the event was sent to
        """
        async with self._lock:
            connections = self._connections.get(room_id, set()).copy()

        sent_count = 0
        for connection in connections:
            if await connection.send(event):
                sent_count += 1

        if sent_count > 0:
            logger.debug(f"Broadcast event to {sent_count} clients in room {room_id}: {event.get('type', 'unknown')}")

        return sent_count

    def get_connection_count(self, room_id: int) -> int:
        """Get the number of active connections for a room.

        Args:
            room_id: Room ID to check

        Returns:
            Number of active connections
        """
        return len(self._connections.get(room_id, set()))

    async def shutdown(self) -> None:
        """Shutdown the broadcaster and close all connections.

        Sends a shutdown event to all connected clients and clears
        the connection registry.
        """
        async with self._lock:
            total_connections = sum(len(conns) for conns in self._connections.values())
            if total_connections > 0:
                logger.info(f"Closing {total_connections} SSE connections...")

                # Send shutdown event to all connections
                for room_id, connections in self._connections.items():
                    for connection in connections:
                        try:
                            connection.queue.put_nowait({"type": "shutdown"})
                        except asyncio.QueueFull:
                            pass  # Best effort

                # Clear all connections
                self._connections.clear()

            logger.info("EventBroadcaster shutdown complete")


async def generate_sse_events(
    connection: SSEConnection,
    broadcaster: EventBroadcaster,
    keepalive_interval: float = 30.0,
) -> AsyncIterator[dict]:
    """Generate SSE events for a connection.

    This is an async generator that yields events from the connection's queue
    and sends periodic keepalive pings.

    Args:
        connection: The SSE connection to generate events for
        broadcaster: The event broadcaster (for cleanup)
        keepalive_interval: Seconds between keepalive pings (default 30s)

    Yields:
        Event dicts to send to the client
    """
    try:
        while True:
            try:
                # Wait for next event with timeout for keepalive
                event = await asyncio.wait_for(
                    connection.receive(),
                    timeout=keepalive_interval,
                )

                # Check for shutdown signal - exit the generator
                if event.get("type") == "shutdown":
                    logger.debug(f"SSE shutdown received for client {connection.client_id}")
                    return

                yield event
            except asyncio.TimeoutError:
                # Send keepalive ping
                yield {"type": "keepalive", "timestamp": asyncio.get_event_loop().time()}
    except asyncio.CancelledError:
        logger.debug(f"SSE event generator cancelled for client {connection.client_id}")
        raise
    finally:
        await broadcaster.unsubscribe(connection)
