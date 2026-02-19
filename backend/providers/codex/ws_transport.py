"""
WebSocket JSON-RPC transport layer for Codex App Server.

Handles JSON-RPC 2.0 communication over WebSocket. Does NOT manage the
subprocess — that responsibility belongs to CodexAppServerInstance.
"""

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

import websockets

logger = logging.getLogger("WsJsonRpcTransport")


class WsJsonRpcTransport:
    """JSON-RPC transport over WebSocket.

    Manages:
    - WebSocket connection with retry logic
    - Message serialization and sending
    - Native WebSocket message framing (no manual buffering)
    - Request/response correlation via request IDs
    - Notification routing via callback

    Usage:
        transport = WsJsonRpcTransport(
            on_notification=handle_notification,
            instance_id=0,
        )
        await transport.connect("ws://127.0.0.1:12345")
        result = await transport.send_request("initialize", {...})
        await transport.send_notification("initialized", {})
        await transport.shutdown()
    """

    def __init__(
        self,
        on_notification: Callable[[Dict[str, Any]], Awaitable[None]],
        instance_id: int = 0,
    ):
        self._on_notification = on_notification
        self._instance_id = instance_id

        self._ws: Optional[websockets.ClientConnection] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._request_lock = asyncio.Lock()
        self._request_id = 0
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._started = False
        self._healthy = True

    @property
    def is_started(self) -> bool:
        return self._started

    @property
    def is_healthy(self) -> bool:
        if not self._healthy or not self._started:
            return False
        if self._ws is None:
            return False
        return True

    async def connect(self, url: str, max_retries: int = 20, retry_delay: float = 0.25) -> None:
        """Connect to the WebSocket server with retry logic.

        The subprocess needs time to start the WS listener, so we retry.

        Args:
            url: WebSocket URL (e.g., "ws://127.0.0.1:12345")
            max_retries: Maximum connection attempts
            retry_delay: Delay between retries in seconds
        """
        if self._started:
            return

        last_error: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                self._ws = await websockets.connect(
                    url,
                    compression=None,  # Avoid tungstenite negotiation issues
                    max_size=10 * 1024 * 1024,  # 10MB max message
                )
                self._reader_task = asyncio.create_task(self._read_messages())
                self._started = True
                self._healthy = True
                logger.info(f"[WsTransport {self._instance_id}] Connected to {url} (attempt {attempt + 1})")
                return
            except (OSError, websockets.exceptions.WebSocketException) as e:
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)

        raise RuntimeError(
            f"[WsTransport {self._instance_id}] Failed to connect to {url} "
            f"after {max_retries} attempts: {last_error}"
        )

    async def send_request(self, method: str, params: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
        """Send a JSON-RPC request and wait for response."""
        async with self._request_lock:
            self._request_id += 1
            request_id = self._request_id

        message = {"method": method, "params": params, "id": request_id}
        future: asyncio.Future[Dict[str, Any]] = asyncio.Future()
        self._pending_requests[request_id] = future

        await self._write_message(message)

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            raise TimeoutError(f"Request {method} timed out after {timeout}s")
        finally:
            self._pending_requests.pop(request_id, None)

    async def send_request_no_wait(self, method: str, params: Dict[str, Any]) -> int:
        """Send a JSON-RPC request without waiting for response."""
        async with self._request_lock:
            self._request_id += 1
            request_id = self._request_id

        message = {"method": method, "params": params, "id": request_id}
        await self._write_message(message)
        return request_id

    async def send_notification(self, method: str, params: Dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no id, no response expected)."""
        message = {"method": method, "params": params}
        await self._write_message(message)

    async def _write_message(self, message: Dict[str, Any]) -> None:
        """Write a JSON-RPC message to the WebSocket."""
        if not self._ws:
            self._healthy = False
            raise RuntimeError("WebSocket not connected")

        try:
            data = json.dumps(message)
            await self._ws.send(data)
            logger.debug(f"[WsTransport {self._instance_id}] Sent: {data[:200]}")
        except (websockets.exceptions.WebSocketException, OSError) as e:
            self._healthy = False
            raise RuntimeError(f"Failed to write to WebSocket: {e}")

    async def _read_messages(self) -> None:
        """Read and process messages from WebSocket using native async iteration."""
        if not self._ws:
            return

        try:
            async for raw in self._ws:
                if isinstance(raw, bytes):
                    raw = raw.decode()

                try:
                    message = json.loads(raw)
                    await self._handle_message(message)
                except json.JSONDecodeError as e:
                    logger.warning(f"[WsTransport {self._instance_id}] Invalid JSON: {e}")

        except asyncio.CancelledError:
            pass
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"[WsTransport {self._instance_id}] Connection closed: {e}")
            self._healthy = False
        except Exception as e:
            logger.error(f"[WsTransport {self._instance_id}] Reader error: {e}")
            self._healthy = False

    async def _handle_message(self, message: Dict[str, Any]) -> None:
        """Handle a received JSON-RPC message.

        Three-way discrimination:
        - Responses (has id + result/error) -> resolve pending futures
        - Notifications (has method, no id) -> route to callback
        - Server requests (has method + id) -> log (not expected)
        """
        msg_id = message.get("id")
        has_result_or_error = "result" in message or "error" in message

        # Response to our request
        if msg_id is not None and has_result_or_error:
            future = self._pending_requests.get(msg_id)
            if future and not future.done():
                if "error" in message:
                    error = message["error"]
                    future.set_exception(RuntimeError(f"RPC error: {error}"))
                else:
                    future.set_result(message.get("result", {}))
            return

        # Server-initiated request (unexpected)
        if msg_id is not None and "method" in message:
            logger.debug(f"[WsTransport {self._instance_id}] Server request (ignored): {message.get('method')}")
            return

        # Notification
        if "method" in message or "type" in message:
            await self._on_notification(message)

    async def shutdown(self) -> None:
        """Gracefully shutdown the WebSocket transport."""
        logger.info(f"[WsTransport {self._instance_id}] Shutting down...")

        # Cancel reader task
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        # Close WebSocket
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        # Cancel pending requests
        for future in self._pending_requests.values():
            if not future.done():
                future.cancel()
        self._pending_requests.clear()

        self._started = False
        self._healthy = False
        logger.info(f"[WsTransport {self._instance_id}] Shutdown complete")
