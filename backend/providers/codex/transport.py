"""
JSON-RPC transport layer for Codex App Server.

Handles low-level subprocess management and JSON-RPC 2.0 communication
over stdin/stdout.
"""

import asyncio
import json
import logging
import os
import shutil
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger("JsonRpcTransport")


class JsonRpcTransport:
    """Low-level JSON-RPC transport over subprocess stdin/stdout.

    Manages:
    - Subprocess lifecycle (start, terminate, kill)
    - Message serialization and writing to stdin
    - Buffered reading from stdout (handles large messages)
    - Request/response correlation via request IDs
    - Notification routing via callback

    Usage:
        transport = JsonRpcTransport(
            command=["codex", "app-server", "--sandbox", "none"],
            on_notification=handle_notification,
        )
        await transport.start()
        result = await transport.send_request("initialize", {...})
        await transport.send_notification("initialized", {})
        await transport.shutdown()
    """

    def __init__(
        self,
        command: List[str],
        on_notification: Callable[[Dict[str, Any]], Awaitable[None]],
        instance_id: int = 0,
    ):
        """Initialize the transport.

        Args:
            command: Command and args to execute (e.g., ["codex", "app-server", ...])
            on_notification: Async callback for received notifications
            instance_id: Identifier for logging purposes
        """
        self._command = command
        self._on_notification = on_notification
        self._instance_id = instance_id

        self._process: Optional[asyncio.subprocess.Process] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._request_lock = asyncio.Lock()
        self._request_id = 0
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._started = False
        self._healthy = True

    @property
    def is_started(self) -> bool:
        """Check if the transport is started."""
        return self._started

    @property
    def is_healthy(self) -> bool:
        """Check if the transport is healthy.

        Checks:
        - _healthy flag (set to False on errors)
        - _started flag (set to True after successful start)
        - Process is still running (returncode is None while running)
        """
        if not self._healthy or not self._started:
            return False
        if self._process is None or self._process.returncode is not None:
            return False
        return True

    @property
    def process(self) -> Optional[asyncio.subprocess.Process]:
        """Get the underlying subprocess (for advanced operations)."""
        return self._process

    async def start(self) -> None:
        """Start the subprocess and begin reading stdout."""
        if self._started:
            return

        # Validate command executable exists
        executable = self._command[0]
        if not shutil.which(executable):
            raise RuntimeError(f"{executable} not found in PATH")

        logger.info(f"[Transport {self._instance_id}] Starting: {' '.join(self._command)}")

        self._process = await asyncio.create_subprocess_exec(
            *self._command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ},
        )

        self._reader_task = asyncio.create_task(self._read_stdout())
        self._started = True
        self._healthy = True

        logger.info(f"[Transport {self._instance_id}] Started (PID: {self._process.pid})")

    async def send_request(self, method: str, params: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
        """Send a JSON-RPC request and wait for response.

        Args:
            method: RPC method name
            params: Request parameters
            timeout: Response timeout in seconds

        Returns:
            Response result dict

        Raises:
            TimeoutError: If response not received within timeout
            RuntimeError: If RPC returns an error
        """
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
        """Send a JSON-RPC request without waiting for response.

        Args:
            method: RPC method name
            params: Request parameters

        Returns:
            Request ID for tracking
        """
        async with self._request_lock:
            self._request_id += 1
            request_id = self._request_id

        message = {"method": method, "params": params, "id": request_id}
        await self._write_message(message)
        return request_id

    async def send_notification(self, method: str, params: Dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no id, no response expected).

        Args:
            method: RPC method name
            params: Notification parameters
        """
        message = {"method": method, "params": params}
        await self._write_message(message)

    async def _write_message(self, message: Dict[str, Any]) -> None:
        """Write a JSON-RPC message to stdin."""
        if not self._process or not self._process.stdin:
            self._healthy = False
            raise RuntimeError("Process not started or stdin not available")

        if self._process.returncode is not None:
            self._healthy = False
            raise RuntimeError(f"Process has exited with code {self._process.returncode}")

        try:
            line = json.dumps(message) + "\n"
            self._process.stdin.write(line.encode())
            await self._process.stdin.drain()
            logger.debug(f"[Transport {self._instance_id}] Sent: {line.strip()}")
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            self._healthy = False
            raise RuntimeError(f"Failed to write to process: {e}")

    async def _read_stdout(self) -> None:
        """Read and process messages from stdout.

        Uses manual buffering to handle large messages (e.g., base64 images)
        that exceed the default readline() buffer limit of 64KB.
        """
        if not self._process or not self._process.stdout:
            return

        buffer = b""
        chunk_size = 1024 * 1024  # 1MB chunks

        try:
            while True:
                chunk = await self._process.stdout.read(chunk_size)
                if not chunk:
                    logger.warning(f"[Transport {self._instance_id}] stdout closed")
                    self._healthy = False
                    break

                buffer += chunk

                # Process complete lines
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    line_str = line.decode().strip()
                    if not line_str:
                        continue

                    try:
                        message = json.loads(line_str)
                        await self._handle_message(message)
                    except json.JSONDecodeError as e:
                        logger.warning(f"[Transport {self._instance_id}] Invalid JSON: {e}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[Transport {self._instance_id}] Reader error: {e}")
            self._healthy = False

    async def _handle_message(self, message: Dict[str, Any]) -> None:
        """Handle a received JSON-RPC message.

        Routes responses to pending futures, notifications to callback.
        """
        # Check if this is a response (has 'id' and 'result' or 'error')
        if "id" in message and ("result" in message or "error" in message):
            request_id = message["id"]
            future = self._pending_requests.get(request_id)
            if future and not future.done():
                if "error" in message:
                    error = message["error"]
                    future.set_exception(RuntimeError(f"RPC error: {error}"))
                else:
                    future.set_result(message.get("result", {}))
            return

        # This is a notification - route to callback
        if "method" in message or "type" in message:
            await self._on_notification(message)

    async def shutdown(self) -> None:
        """Gracefully shutdown the transport."""
        logger.info(f"[Transport {self._instance_id}] Shutting down...")

        # Cancel reader task
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        # Terminate process
        if self._process:
            try:
                if self._process.returncode is None:
                    self._process.terminate()
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                try:
                    self._process.kill()
                    await self._process.wait()
                except ProcessLookupError:
                    pass
            except ProcessLookupError:
                pass
            except Exception as e:
                if str(e):
                    logger.warning(f"[Transport {self._instance_id}] Error terminating: {e}")
            self._process = None

        # Cancel pending requests
        for future in self._pending_requests.values():
            if not future.done():
                future.cancel()
        self._pending_requests.clear()

        self._started = False
        self._healthy = False
        logger.info(f"[Transport {self._instance_id}] Shutdown complete")
