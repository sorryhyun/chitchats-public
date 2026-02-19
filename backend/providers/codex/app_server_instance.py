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
import logging
import shutil
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Set

from providers.configs import DEFAULT_CODEX_CONFIG, CodexStartupConfig, CodexTurnConfig

from .constants import AppServerMethod, map_approval_policy, map_sandbox
from .transport import JsonRpcTransport

logger = logging.getLogger("CodexAppServerInstance")


class CodexAppServerInstance:
    """Single Codex App Server instance.

    Manages one `codex app-server` subprocess with JSON-RPC 2.0 communication.
    Uses JsonRpcTransport for low-level message handling.

    Usage:
        instance = CodexAppServerInstance(instance_id=0)
        await instance.start()
        thread_id = await instance.create_thread(config)
        async for event in instance.start_turn(thread_id, "Hello!"):
            # Handle streaming events
        await instance.shutdown()
    """

    def __init__(
        self,
        instance_id: int,
        startup_config: Optional[CodexStartupConfig] = None,
        agent_key: Optional[str] = None,
    ):
        """Initialize an app server instance.

        Args:
            instance_id: Unique identifier for this instance (0, 1, 2, ...)
            startup_config: Static configuration for app-server launch (uses default if None)
            agent_key: Identifier for the agent this instance serves (for per-agent instances)
        """
        self._instance_id = instance_id
        self._startup_config = startup_config or DEFAULT_CODEX_CONFIG
        self._agent_key = agent_key

        self._transport: Optional[JsonRpcTransport] = None
        self._active_threads: Set[str] = set()
        self._current_turn_id: Optional[str] = None
        self._notification_queue: Optional[asyncio.Queue[Dict[str, Any]]] = None

        # Track last activity time for idle timeout
        self._last_activity: float = time.monotonic()
        self._created_at: float = time.monotonic()

    @property
    def instance_id(self) -> int:
        """Get the instance ID."""
        return self._instance_id

    @property
    def is_started(self) -> bool:
        """Check if the server is started."""
        return self._transport is not None and self._transport.is_started

    @property
    def is_healthy(self) -> bool:
        """Check if the server is healthy."""
        return self._transport is not None and self._transport.is_healthy

    @property
    def active_thread_count(self) -> int:
        """Get the number of active threads."""
        return len(self._active_threads)

    @property
    def active_threads(self) -> Set[str]:
        """Get the set of active thread IDs."""
        return self._active_threads.copy()

    @property
    def agent_key(self) -> Optional[str]:
        """Get the agent key this instance serves."""
        return self._agent_key

    @property
    def last_activity(self) -> float:
        """Get the last activity timestamp (monotonic)."""
        return self._last_activity

    @property
    def idle_seconds(self) -> float:
        """Get seconds since last activity."""
        return time.monotonic() - self._last_activity

    @property
    def process_pid(self) -> Optional[int]:
        """Get the process PID if running."""
        if self._transport and self._transport.process:
            return self._transport.process.pid
        return None

    def kill(self) -> None:
        """Forcefully kill the subprocess (sync, for emergency cleanup)."""
        if self._transport and self._transport.process:
            try:
                self._transport.process.kill()
            except ProcessLookupError:
                pass

    def touch(self) -> None:
        """Update last activity timestamp."""
        self._last_activity = time.monotonic()

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

    async def _handle_notification(self, message: Dict[str, Any]) -> None:
        """Handle notifications from the transport.

        Routes notifications to the active turn's queue.
        """
        if self._notification_queue is not None:
            await self._notification_queue.put(message)

    async def start(self) -> None:
        """Start the Codex App Server process and initialize connection."""
        if self.is_started:
            return

        # Codex supports native Windows — always resolve from PATH
        codex_path = shutil.which("codex")
        if not codex_path:
            raise RuntimeError("Codex CLI not found. Install it with: npm install -g @openai/codex")

        # Build command with CLI args from startup config
        cli_args = self._startup_config.to_cli_args()
        command = [codex_path, "app-server", *cli_args]

        logger.info(f"[Instance {self._instance_id}] Starting Codex App Server with args: {' '.join(cli_args)}")

        # Create and start transport
        self._transport = JsonRpcTransport(
            command=command,
            on_notification=self._handle_notification,
            instance_id=self._instance_id,
        )
        await self._transport.start()

        # Perform initialize handshake
        await self._initialize_handshake()

        logger.info(f"[Instance {self._instance_id}] Codex App Server started")

    async def _initialize_handshake(self) -> None:
        """Perform JSON-RPC initialize handshake."""
        if not self._transport:
            raise RuntimeError("Transport not initialized")

        logger.debug(f"[Instance {self._instance_id}] Sending initialize request...")

        result = await self._transport.send_request(
            "initialize",
            {
                "clientInfo": {
                    "name": "chitchats",
                    "version": "1.0.0",
                },
            },
        )

        logger.debug(f"[Instance {self._instance_id}] Initialize response: {result}")

        await self._transport.send_notification("initialized", {})
        logger.debug(f"[Instance {self._instance_id}] Sent initialized notification")

    async def create_thread(self, config: CodexTurnConfig) -> str:
        """Create a new thread for conversation.

        Args:
            config: Thread configuration

        Returns:
            Thread ID for subsequent turns
        """
        if not self._transport:
            raise RuntimeError("Instance not started")

        params: Dict[str, Any] = {}

        if config.cwd:
            params["cwd"] = config.cwd

        if config.model:
            params["model"] = config.model

        params["baseInstructions"] = config.developer_instructions
        params["sandbox"] = map_sandbox(self._startup_config.sandbox)
        params["approvalPolicy"] = map_approval_policy(self._startup_config.approval_policy)

        logger.debug(f"[Instance {self._instance_id}] Creating thread with params: {params}")

        result = await self._transport.send_request("thread/start", params)

        thread_data = result.get("thread", {})
        thread_id = thread_data.get("id") or result.get("threadId")
        if not thread_id:
            raise RuntimeError(f"thread/start did not return thread.id: {result}")

        self.register_thread(thread_id)
        logger.info(f"[Instance {self._instance_id}] Created thread {thread_id}")

        return thread_id

    async def resume_thread(self, thread_id: str, config: CodexTurnConfig) -> bool:
        """Resume an existing thread by ID.

        Args:
            thread_id: Thread ID to resume
            config: Thread configuration

        Returns:
            True if resume succeeded, False if thread not found
        """
        if not self._transport:
            raise RuntimeError("Instance not started")

        params: Dict[str, Any] = {"threadId": thread_id}

        if config.cwd:
            params["cwd"] = config.cwd

        logger.debug(f"[Instance {self._instance_id}] Resuming thread {thread_id}")

        try:
            result = await self._transport.send_request("thread/resume", params)

            thread_data = result.get("thread", {})
            resumed_id = thread_data.get("id") or result.get("threadId")

            if resumed_id:
                self.register_thread(thread_id)
                logger.info(f"[Instance {self._instance_id}] Resumed thread {thread_id}")
                return True
            else:
                logger.warning(f"[Instance {self._instance_id}] Resume returned no thread: {result}")
                return False

        except RuntimeError as e:
            logger.debug(f"[Instance {self._instance_id}] Failed to resume thread {thread_id}: {e}")
            return False

    async def start_turn(
        self,
        thread_id: str,
        input_items: List[Dict[str, Any]],
        config: CodexTurnConfig,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Start a turn and stream events.

        Args:
            thread_id: Thread ID from create_thread
            input_items: List of input items (text, localImage, etc.)
            config: Turn configuration

        Yields:
            Streaming events (deltas, item completions, etc.)
        """
        if not self._transport:
            raise RuntimeError("Instance not started")

        params: Dict[str, Any] = {
            "threadId": thread_id,
            "input": input_items,
            "baseInstructions": config.developer_instructions,
        }

        if config.model:
            params["model"] = config.model

        self.touch()

        # Log input summary
        text_items = [item.get("text", "")[:50] for item in input_items if item.get("type") == "text"]
        image_count = sum(1 for item in input_items if item.get("type") in ("localImage", "image"))
        logger.info(
            f"[Instance {self._instance_id}] Starting turn on thread {thread_id}, "
            f"items: {len(input_items)} ({image_count} images), "
            f"text preview: {text_items[0] if text_items else '(no text)'}..."
        )

        # Create notification queue for this turn
        self._notification_queue = asyncio.Queue()

        # Send request without waiting (we stream notifications)
        await self._transport.send_request_no_wait("turn/start", params)
        self._current_turn_id = None

        try:
            while True:
                try:
                    event = await asyncio.wait_for(self._notification_queue.get(), timeout=120.0)

                    # Extract turn_id from turn/started
                    if event.get("method") == AppServerMethod.TURN_STARTED:
                        params_data = event.get("params", {})
                        self._current_turn_id = params_data.get("turnId")
                        logger.debug(f"[Instance {self._instance_id}] Turn started: {self._current_turn_id}")

                    yield event

                    # Check for completion
                    method = event.get("method", "")
                    event_type = event.get("type", "")
                    if method == AppServerMethod.TURN_COMPLETED or event_type == "response_completed":
                        break

                except asyncio.TimeoutError:
                    logger.warning(f"[Instance {self._instance_id}] Turn timed out")
                    break

        finally:
            self._notification_queue = None
            self._current_turn_id = None
            self.touch()

    async def interrupt_turn(self, thread_id: str, turn_id: Optional[str] = None) -> bool:
        """Interrupt an ongoing turn.

        Args:
            thread_id: Thread ID
            turn_id: Turn ID (uses current if not specified)

        Returns:
            True if interrupt was successful
        """
        if not self._transport:
            return False

        turn_id = turn_id or self._current_turn_id
        if not turn_id:
            logger.warning(f"[Instance {self._instance_id}] No turn to interrupt")
            return False

        logger.info(f"[Instance {self._instance_id}] Interrupting turn {turn_id}")

        try:
            await self._transport.send_request(
                "turn/interrupt",
                {"threadId": thread_id, "turnId": turn_id},
            )
            return True
        except Exception as e:
            logger.error(f"[Instance {self._instance_id}] Interrupt failed: {e}")
            return False

    async def restart(self) -> None:
        """Restart the app server after a failure."""
        logger.info(f"[Instance {self._instance_id}] Restarting Codex App Server...")
        await self.shutdown()
        await self.start()

    async def shutdown(self) -> None:
        """Gracefully shutdown the app server."""
        logger.info(f"[Instance {self._instance_id}] Shutting down...")

        if self._transport:
            await self._transport.shutdown()
            self._transport = None

        self._notification_queue = None
        self._active_threads.clear()

        logger.info(f"[Instance {self._instance_id}] Shutdown complete")
