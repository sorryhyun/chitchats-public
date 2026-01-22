"""
Single Codex App Server instance.

This module provides the CodexAppServerInstance class that manages a single
`codex app-server` subprocess using JSON-RPC 2.0 protocol over stdio.

Unlike the MCP server, the App Server:
- Uses JSON-RPC 2.0 (without jsonrpc header field)
- Provides streaming notifications for real-time output
- Supports turn interruption via turn/interrupt method
- Requires explicit thread creation via thread/start
"""

import asyncio
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, Optional, Set

from .constants import AppServerMethod, map_approval_policy, map_sandbox
from .windows_support import get_bundled_codex_path

logger = logging.getLogger("CodexAppServerInstance")


@dataclass
class AppServerConfig:
    """Configuration for app server thread/turn.

    Attributes:
        developer_instructions: System prompt for the agent
        model: Model to use (e.g., "gpt-5.1-codex")
        mcp_servers: MCP server configurations
        approval_policy: Approval policy - "never", "on-request", "on-failure", "untrusted"
        sandbox: Sandbox mode - "danger-full-access", "workspace-write", "read-only"
        cwd: Working directory
        features: Feature flags (shell_tool, child_agents_md, etc.)
    """

    developer_instructions: str = ""
    model: Optional[str] = None
    mcp_servers: Dict[str, Any] = field(default_factory=dict)
    approval_policy: str = "never"
    sandbox: str = "danger-full-access"
    cwd: Optional[str] = None
    features: Dict[str, bool] = field(default_factory=dict)
    extra_config: Dict[str, Any] = field(default_factory=dict)


class CodexAppServerInstance:
    """Single Codex App Server instance.

    Manages one `codex app-server` subprocess with JSON-RPC 2.0 communication.

    Usage:
        instance = CodexAppServerInstance(instance_id=0)
        await instance.start()
        thread_id = await instance.create_thread(config)
        async for event in instance.start_turn(thread_id, "Hello!"):
            # Handle streaming events
        await instance.shutdown()
    """

    def __init__(self, instance_id: int):
        """Initialize an app server instance.

        Args:
            instance_id: Unique identifier for this instance (0, 1, 2, ...)
        """
        self._instance_id = instance_id
        self._process: Optional[asyncio.subprocess.Process] = None
        self._started = False
        self._healthy = True
        self._request_lock = asyncio.Lock()
        self._request_id = 0
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._active_threads: Set[str] = set()
        self._reader_task: Optional[asyncio.Task] = None
        self._current_turn_id: Optional[str] = None

    @property
    def instance_id(self) -> int:
        """Get the instance ID."""
        return self._instance_id

    @property
    def is_started(self) -> bool:
        """Check if the server is started."""
        return self._started

    @property
    def is_healthy(self) -> bool:
        """Check if the server is healthy."""
        return self._healthy and self._started

    @property
    def active_thread_count(self) -> int:
        """Get the number of active threads."""
        return len(self._active_threads)

    @property
    def active_threads(self) -> Set[str]:
        """Get the set of active thread IDs."""
        return self._active_threads.copy()

    def owns_thread(self, thread_id: str) -> bool:
        """Check if this instance owns a thread."""
        return thread_id in self._active_threads

    def register_thread(self, thread_id: str) -> None:
        """Register a thread as owned by this instance."""
        self._active_threads.add(thread_id)
        logger.debug(f"[Instance {self._instance_id}] Registered thread {thread_id}")

    def release_thread(self, thread_id: str) -> bool:
        """Release a thread from this instance."""
        if thread_id in self._active_threads:
            self._active_threads.discard(thread_id)
            logger.debug(f"[Instance {self._instance_id}] Released thread {thread_id}")
            return True
        return False

    async def start(self) -> None:
        """Start the Codex App Server process and initialize connection."""
        if self._started:
            return

        # Prefer bundled Rust binary over npm-installed version (Windows support)
        codex_path = get_bundled_codex_path()
        if not codex_path:
            codex_path = shutil.which("codex")
        if not codex_path:
            raise RuntimeError("Codex CLI not found. Install it with: npm install -g @openai/codex")

        logger.info(f"[Instance {self._instance_id}] Starting Codex App Server...")

        # Start the subprocess
        self._process = await asyncio.create_subprocess_exec(
            codex_path,
            "app-server",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ},
        )

        # Start the stdout reader task
        self._reader_task = asyncio.create_task(self._read_stdout())

        # Perform initialize handshake
        await self._initialize_handshake()

        logger.info(f"[Instance {self._instance_id}] Codex App Server started")
        self._started = True
        self._healthy = True

    async def _initialize_handshake(self) -> None:
        """Perform JSON-RPC initialize handshake.

        Sends initialize request and waits for response, then sends initialized notification.
        """
        logger.debug(f"[Instance {self._instance_id}] Sending initialize request...")

        # Send initialize request
        result = await self._send_request("initialize", {
            "clientInfo": {
                "name": "chitchats",
                "version": "1.0.0",
            },
        })

        logger.debug(f"[Instance {self._instance_id}] Initialize response: {result}")

        # Send initialized notification (no id)
        await self._send_notification("initialized", {})
        logger.debug(f"[Instance {self._instance_id}] Sent initialized notification")

    async def create_thread(self, config: AppServerConfig) -> str:
        """Create a new thread for conversation.

        Args:
            config: Thread configuration

        Returns:
            Thread ID for subsequent turns
        """
        params: Dict[str, Any] = {}

        if config.cwd:
            params["cwd"] = config.cwd

        if config.model:
            params["model"] = config.model

        # Add base instructions (system prompt) to thread
        if config.developer_instructions:
            params["baseInstructions"] = config.developer_instructions

        params["sandbox"] = map_sandbox(config.sandbox)
        params["approvalPolicy"] = map_approval_policy(config.approval_policy)

        logger.debug(f"[Instance {self._instance_id}] Creating thread with params: {params}")

        result = await self._send_request("thread/start", params)

        # Extract thread ID from nested structure: result.thread.id
        thread_data = result.get("thread", {})
        thread_id = thread_data.get("id") or result.get("threadId")
        if not thread_id:
            raise RuntimeError(f"thread/start did not return thread.id: {result}")

        self.register_thread(thread_id)
        logger.info(f"[Instance {self._instance_id}] Created thread {thread_id}")

        return thread_id

    async def start_turn(
        self,
        thread_id: str,
        text: str,
        config: AppServerConfig,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Start a turn and stream events.

        Args:
            thread_id: Thread ID from create_thread
            text: User message text
            config: Turn configuration

        Yields:
            Streaming events (deltas, item completions, etc.)
        """
        # Build input array with typed content (per API docs)
        input_items = [{"type": "text", "text": text}]

        params: Dict[str, Any] = {
            "threadId": thread_id,
            "input": input_items,
        }

        # Add developer instructions if provided
        if config.developer_instructions:
            params["baseInstructions"] = config.developer_instructions

        # Add MCP servers if configured
        if config.mcp_servers:
            params["mcpServers"] = config.mcp_servers

        # Add model if specified
        if config.model:
            params["model"] = config.model

        # Add extra config options
        if config.extra_config:
            for key, value in config.extra_config.items():
                if key not in params:
                    params[key] = value

        logger.info(
            f"[Instance {self._instance_id}] Starting turn on thread {thread_id}, "
            f"message: {text[:100]}..."
        )

        # Use a queue to collect streaming events
        event_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        turn_complete_event = asyncio.Event()

        async def collect_events() -> None:
            """Collect streaming events until turn completes."""
            try:
                while not turn_complete_event.is_set():
                    try:
                        event = await asyncio.wait_for(
                            self._notification_queue.get(),
                            timeout=0.1,
                        )
                        await event_queue.put(event)

                        # Check if this is turn completion
                        # JSON-RPC format: method == "turn/completed"
                        # Streaming format: type == "response_completed"
                        method = event.get("method", "")
                        event_type = event.get("type", "")
                        if method == AppServerMethod.TURN_COMPLETED or event_type == "response_completed":
                            turn_complete_event.set()
                            break

                    except asyncio.TimeoutError:
                        continue
            except asyncio.CancelledError:
                pass

        # Create notification queue for this turn
        self._notification_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

        # Send the request (don't wait for response - we stream notifications)
        await self._send_request_no_wait("turn/start", params)
        self._current_turn_id = None  # Will be set when we get turn/started

        # Start collector task
        collector_task = asyncio.create_task(collect_events())

        try:
            while True:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=120.0)

                    # Extract turn_id from turn/started (JSON-RPC format)
                    if event.get("method") == AppServerMethod.TURN_STARTED:
                        params_data = event.get("params", {})
                        self._current_turn_id = params_data.get("turnId")
                        logger.debug(
                            f"[Instance {self._instance_id}] Turn started: {self._current_turn_id}"
                        )

                    yield event

                    # Check for completion
                    # JSON-RPC format: method == "turn/completed"
                    # Streaming format: type == "response_completed"
                    method = event.get("method", "")
                    event_type = event.get("type", "")
                    if method == AppServerMethod.TURN_COMPLETED or event_type == "response_completed":
                        break

                except asyncio.TimeoutError:
                    logger.warning(f"[Instance {self._instance_id}] Turn timed out")
                    break

        finally:
            collector_task.cancel()
            try:
                await collector_task
            except asyncio.CancelledError:
                pass
            self._current_turn_id = None

    async def interrupt_turn(self, thread_id: str, turn_id: Optional[str] = None) -> bool:
        """Interrupt an ongoing turn.

        Args:
            thread_id: Thread ID
            turn_id: Turn ID (uses current if not specified)

        Returns:
            True if interrupt was successful
        """
        turn_id = turn_id or self._current_turn_id
        if not turn_id:
            logger.warning(f"[Instance {self._instance_id}] No turn to interrupt")
            return False

        logger.info(f"[Instance {self._instance_id}] Interrupting turn {turn_id}")

        try:
            await self._send_request("turn/interrupt", {
                "threadId": thread_id,
                "turnId": turn_id,
            })
            return True
        except Exception as e:
            logger.error(f"[Instance {self._instance_id}] Interrupt failed: {e}")
            return False

    async def _send_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send a JSON-RPC request and wait for response.

        Args:
            method: RPC method name
            params: Request parameters

        Returns:
            Response result
        """
        async with self._request_lock:
            self._request_id += 1
            request_id = self._request_id

            message = {
                "method": method,
                "id": request_id,
                "params": params,
            }

            # Create future for response
            future: asyncio.Future[Dict[str, Any]] = asyncio.Future()
            self._pending_requests[request_id] = future

            # Send message
            await self._write_message(message)

            try:
                result = await asyncio.wait_for(future, timeout=30.0)
                return result
            except asyncio.TimeoutError:
                self._pending_requests.pop(request_id, None)
                raise TimeoutError(f"Request {method} timed out")
            finally:
                self._pending_requests.pop(request_id, None)

    async def _send_request_no_wait(self, method: str, params: Dict[str, Any]) -> int:
        """Send a JSON-RPC request without waiting for response.

        Used for turn/start where we stream notifications instead.

        Args:
            method: RPC method name
            params: Request parameters

        Returns:
            Request ID
        """
        self._request_id += 1
        request_id = self._request_id

        message = {
            "method": method,
            "id": request_id,
            "params": params,
        }

        await self._write_message(message)
        return request_id

    async def _send_notification(self, method: str, params: Dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no id, no response expected).

        Args:
            method: RPC method name
            params: Notification parameters
        """
        message = {
            "method": method,
            "params": params,
        }
        await self._write_message(message)

    async def _write_message(self, message: Dict[str, Any]) -> None:
        """Write a JSON-RPC message to stdin."""
        if not self._process or not self._process.stdin:
            raise RuntimeError("Process not started or stdin not available")

        line = json.dumps(message) + "\n"
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()
        logger.debug(f"[Instance {self._instance_id}] Sent: {line.strip()}")

    async def _read_stdout(self) -> None:
        """Read and process messages from stdout."""
        if not self._process or not self._process.stdout:
            return

        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    logger.warning(f"[Instance {self._instance_id}] stdout closed")
                    self._healthy = False
                    break

                line_str = line.decode().strip()
                if not line_str:
                    continue

                logger.debug(f"[Instance {self._instance_id}] Received: {line_str}")

                try:
                    message = json.loads(line_str)
                    await self._handle_message(message)
                except json.JSONDecodeError as e:
                    logger.warning(f"[Instance {self._instance_id}] Invalid JSON: {e}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[Instance {self._instance_id}] Reader error: {e}")
            self._healthy = False

    async def _handle_message(self, message: Dict[str, Any]) -> None:
        """Handle a received JSON-RPC message.

        Args:
            message: Parsed JSON message
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

        # This is a notification - can be JSON-RPC format or streaming format
        # JSON-RPC format: {"method": "...", "params": {...}}
        # Streaming format: {"timestamp": "...", "type": "...", "payload": {...}}
        if "method" in message or "type" in message:
            # Queue notification for turn processing
            if hasattr(self, "_notification_queue"):
                await self._notification_queue.put(message)

    async def restart(self) -> None:
        """Restart the app server after a failure."""
        logger.info(f"[Instance {self._instance_id}] Restarting Codex App Server...")
        await self._cleanup()
        self._started = False
        self._healthy = False
        await self.start()

    async def _cleanup(self) -> None:
        """Clean up server resources."""
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            except Exception as e:
                logger.warning(f"[Instance {self._instance_id}] Error terminating process: {e}")
            self._process = None

        # Clear pending requests
        for future in self._pending_requests.values():
            if not future.done():
                future.cancel()
        self._pending_requests.clear()

    async def shutdown(self) -> None:
        """Gracefully shutdown the app server."""
        logger.info(f"[Instance {self._instance_id}] Shutting down...")
        await self._cleanup()
        self._started = False
        self._healthy = False
        self._active_threads.clear()
        logger.info(f"[Instance {self._instance_id}] Shutdown complete")
