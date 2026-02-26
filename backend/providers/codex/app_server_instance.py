"""
Single Codex App Server instance.

This module provides the CodexAppServerInstance class that manages a single
`codex app-server` subprocess communicating via WebSocket JSON-RPC 2.0.

Unlike the MCP server, the App Server:
- Uses JSON-RPC 2.0 (without jsonrpc header field)
- Provides streaming notifications for real-time output
- Supports turn interruption via turn/interrupt method
- Requires explicit thread creation via thread/start
"""

import asyncio
import logging
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Set

from providers.configs import DEFAULT_CODEX_CONFIG, CodexStartupConfig, CodexTurnConfig

from .constants import AppServerMethod, RealtimeMethod, RealtimeNotification, map_approval_policy, map_sandbox, resolve_codex_path
from .ws_transport import WsJsonRpcTransport

logger = logging.getLogger("CodexAppServerInstance")


class CodexAppServerInstance:
    """Single Codex App Server instance.

    Manages one `codex app-server` subprocess with JSON-RPC 2.0 communication
    over WebSocket. Uses WsJsonRpcTransport for message handling.

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

        self._transport: Optional[WsJsonRpcTransport] = None
        self._process: Optional[asyncio.subprocess.Process] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._active_threads: Set[str] = set()
        self._current_turn_id: Optional[str] = None
        self._notification_queue: Optional[asyncio.Queue[Dict[str, Any]]] = None
        self._realtime_notification_queue: Optional[asyncio.Queue[Dict[str, Any]]] = None

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
        """Check if the server is healthy (WS connected AND process alive)."""
        if self._transport is None or not self._transport.is_healthy:
            return False
        if self._process is None or self._process.returncode is not None:
            return False
        return True

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
        if self._process and self._process.pid:
            return self._process.pid
        return None

    def kill(self) -> None:
        """Forcefully kill the subprocess and its children (sync, for emergency cleanup)."""
        if self._process:
            self._kill_process_tree(self._process)

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

        Routes realtime notifications to the realtime queue,
        and turn notifications to the turn queue.
        """
        method = message.get("method", "")

        # Route to realtime queue when a realtime session is active:
        # - thread/realtime/* notifications (started, outputAudio, closed, etc.)
        # - Generic error notifications ("error", "codex/event/error") that
        #   occur during a realtime session (e.g., "conversation is not running")
        if self._realtime_notification_queue is not None:
            if method.startswith("thread/realtime/") or method in ("error", "codex/event/error"):
                await self._realtime_notification_queue.put(message)
                return

        if self._notification_queue is not None:
            await self._notification_queue.put(message)

    @staticmethod
    def _find_free_port() -> int:
        """Find a free port by binding to port 0 and letting the OS assign one."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    async def _read_stderr(self) -> None:
        """Background task to log subprocess stderr at DEBUG level."""
        if not self._process or not self._process.stderr:
            return
        try:
            while True:
                line = await self._process.stderr.readline()
                if not line:
                    break
                text = line.decode(errors="replace").rstrip()
                if text:
                    # Show errors/warnings at INFO, routine messages at DEBUG
                    if "ERROR" in text or "WARN" in text or "error" in text.lower():
                        logger.info(f"[Instance {self._instance_id}] stderr: {text}")
                    else:
                        logger.debug(f"[Instance {self._instance_id}] stderr: {text}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"[Instance {self._instance_id}] stderr reader error: {e}")

    @staticmethod
    def _kill_process_tree(proc: asyncio.subprocess.Process) -> None:
        """Kill a process and all its children. Works on Windows and Unix."""
        pid = proc.pid
        if pid is None:
            return
        try:
            if sys.platform == "win32":
                # taskkill /F (force) /T (tree - kill children) /PID
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                # On Unix, kill the process group
                try:
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        pass
        except ProcessLookupError:
            pass
        except Exception:
            # Last resort: direct kill
            try:
                proc.kill()
            except ProcessLookupError:
                pass

    async def _terminate_process(self) -> None:
        """Terminate the subprocess and its children: SIGTERM -> 5s wait -> force kill tree."""
        if not self._process:
            return
        try:
            if self._process.returncode is None:
                if sys.platform == "win32":
                    # On Windows, always kill the entire process tree.
                    # process.terminate() only kills the main process, leaving children orphaned.
                    self._kill_process_tree(self._process)
                    try:
                        await self._process.wait()
                    except ProcessLookupError:
                        pass
                else:
                    # On Unix, try graceful SIGTERM first
                    self._process.terminate()
                    try:
                        await asyncio.wait_for(self._process.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        self._kill_process_tree(self._process)
                        try:
                            await self._process.wait()
                        except ProcessLookupError:
                            pass
        except ProcessLookupError:
            pass
        except Exception as e:
            if str(e):
                logger.warning(f"[Instance {self._instance_id}] Error terminating process: {e}")
        self._process = None

    async def start(self) -> None:
        """Start the Codex App Server process and initialize WebSocket connection."""
        if self.is_started:
            return

        # Prefer bundled alpha Codex binary (supports audio), fall back to PATH
        codex_path = resolve_codex_path()
        if not codex_path:
            raise RuntimeError("Codex CLI not found. Install it with: npm install -g @openai/codex")
        logger.info(f"[Instance {self._instance_id}] Using Codex: {codex_path}")

        # Allocate a free port for WebSocket
        port = self._find_free_port()
        ws_url = f"ws://127.0.0.1:{port}"

        # Build command with CLI args from startup config
        cli_args = self._startup_config.to_cli_args()
        command = [codex_path, "app-server", *cli_args, "--listen", ws_url]

        logger.info(f"[Instance {self._instance_id}] Starting Codex App Server on {ws_url} with args: {' '.join(cli_args)}")

        # Build environment with BROWSER="" to prevent subprocess from opening browser
        subprocess_env = {**os.environ, "BROWSER": ""}

        # Spawn subprocess with stdin/stdout detached (communication is via WebSocket)
        # On Windows, use CREATE_NEW_PROCESS_GROUP so taskkill /T can kill the tree.
        # On Unix, use start_new_session so os.killpg can kill the group.
        platform_kwargs: Dict[str, Any] = {}
        if sys.platform == "win32":
            platform_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            platform_kwargs["start_new_session"] = True

        self._process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env=subprocess_env,
            **platform_kwargs,
        )

        logger.info(f"[Instance {self._instance_id}] Process started (PID: {self._process.pid})")

        # Start stderr logging task
        self._stderr_task = asyncio.create_task(self._read_stderr())

        # Create WebSocket transport and connect with retry
        self._transport = WsJsonRpcTransport(
            on_notification=self._handle_notification,
            instance_id=self._instance_id,
        )
        try:
            await self._transport.connect(ws_url)
        except RuntimeError:
            # Connection failed — clean up the process
            await self._terminate_process()
            raise

        # Perform initialize handshake
        await self._initialize_handshake()

        logger.info(f"[Instance {self._instance_id}] Codex App Server started on {ws_url}")

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
                "capabilities": {
                    "experimentalApi": True,
                },
            },
        )

        logger.info(f"[Instance {self._instance_id}] Initialize response: {result}")

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

    # =========================================================================
    # Realtime voice session methods
    # =========================================================================

    async def start_realtime(
        self,
        thread_id: str,
        prompt: str,
        session_id: Optional[str] = None,
        start_timeout: float = 10.0,
    ) -> Dict[str, Any]:
        """Start a realtime voice session on a thread.

        Sends the start request and waits for the thread/realtime/started
        notification from the backend. If the notification doesn't arrive
        within start_timeout seconds, raises RuntimeError.

        Args:
            thread_id: Thread ID to attach the session to
            prompt: System prompt for the realtime model
            session_id: Optional session ID to resume a prior session
            start_timeout: Seconds to wait for the started notification

        Returns:
            Started notification params (contains sessionId, etc.)

        Raises:
            RuntimeError: If the session fails to start or times out
        """
        if not self._transport:
            raise RuntimeError("Instance not started")

        params: Dict[str, Any] = {
            "threadId": thread_id,
            "prompt": prompt,
        }
        if session_id:
            params["sessionId"] = session_id

        self._realtime_notification_queue = asyncio.Queue()
        self.touch()

        logger.info(f"[Instance {self._instance_id}] Starting realtime session on thread {thread_id}")
        result = await self._transport.send_request(RealtimeMethod.START, params)
        logger.info(f"[Instance {self._instance_id}] Realtime start RPC response: {result}")

        # Wait for the thread/realtime/started notification (confirms backend connected)
        logger.info(f"[Instance {self._instance_id}] Waiting for realtime started notification (timeout={start_timeout}s)...")
        deadline = asyncio.get_event_loop().time() + start_timeout
        errors_collected: List[str] = []

        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                error_detail = "; ".join(errors_collected) if errors_collected else "no response from Codex"
                self._realtime_notification_queue = None
                raise RuntimeError(
                    f"Realtime session failed to start within {start_timeout}s: {error_detail}"
                )

            try:
                notification = await asyncio.wait_for(
                    self._realtime_notification_queue.get(),
                    timeout=remaining,
                )
            except asyncio.TimeoutError:
                error_detail = "; ".join(errors_collected) if errors_collected else "no response from Codex"
                self._realtime_notification_queue = None
                raise RuntimeError(
                    f"Realtime session failed to start within {start_timeout}s: {error_detail}"
                )

            method = notification.get("method", "")
            notif_params = notification.get("params", {})

            if method == RealtimeNotification.STARTED:
                logger.info(
                    f"[Instance {self._instance_id}] Realtime session confirmed started: "
                    f"sessionId={notif_params.get('sessionId')}"
                )
                return notif_params

            elif method == RealtimeNotification.CLOSED:
                reason = notif_params.get("reason", "unknown")
                self._realtime_notification_queue = None
                raise RuntimeError(f"Realtime session closed before starting: {reason}")

            elif method in ("error", "codex/event/error"):
                # Collect error details
                error_msg = notif_params.get("error", {}).get("message", "") or \
                            notif_params.get("msg", {}).get("message", "")
                if error_msg:
                    errors_collected.append(error_msg)
                    logger.warning(f"[Instance {self._instance_id}] Realtime start error: {error_msg}")
                # First error is likely definitive — fail immediately
                self._realtime_notification_queue = None
                raise RuntimeError(f"Realtime session failed to start: {error_msg}")

            else:
                logger.debug(f"[Instance {self._instance_id}] Ignoring notification during start wait: {method}")

    async def append_audio(self, thread_id: str, audio_data: Dict[str, Any]) -> None:
        """Send audio data to the realtime session (fire-and-forget).

        Args:
            thread_id: Thread ID
            audio_data: Audio dict with data (base64), sampleRate, numChannels, samplesPerChannel
        """
        if not self._transport:
            raise RuntimeError("Instance not started")

        await self._transport.send_request_no_wait(
            RealtimeMethod.APPEND_AUDIO,
            {"threadId": thread_id, "audio": audio_data},
        )

    async def append_text(self, thread_id: str, text: str) -> None:
        """Send text input to the realtime session.

        Args:
            thread_id: Thread ID
            text: Text to send
        """
        if not self._transport:
            raise RuntimeError("Instance not started")

        await self._transport.send_request_no_wait(
            RealtimeMethod.APPEND_TEXT,
            {"threadId": thread_id, "text": text},
        )

    async def stop_realtime(self, thread_id: str) -> None:
        """Stop a realtime voice session.

        Args:
            thread_id: Thread ID
        """
        if not self._transport:
            return

        logger.info(f"[Instance {self._instance_id}] Stopping realtime session on thread {thread_id}")
        try:
            await self._transport.send_request(RealtimeMethod.STOP, {"threadId": thread_id})
        except Exception as e:
            logger.warning(f"[Instance {self._instance_id}] Error stopping realtime: {e}")
        finally:
            self._realtime_notification_queue = None
            self.touch()

    async def drain_realtime_notifications(self, timeout: float = 0.1) -> Optional[Dict[str, Any]]:
        """Get the next realtime notification, or None if the queue is empty/closed.

        Args:
            timeout: How long to wait for a notification

        Returns:
            Notification dict, or None on timeout / queue closed
        """
        if self._realtime_notification_queue is None:
            return None
        try:
            return await asyncio.wait_for(self._realtime_notification_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def restart(self) -> None:
        """Restart the app server after a failure."""
        logger.info(f"[Instance {self._instance_id}] Restarting Codex App Server...")
        await self.shutdown()
        await self.start()

    async def shutdown(self) -> None:
        """Gracefully shutdown the app server (transport + process)."""
        logger.info(f"[Instance {self._instance_id}] Shutting down...")

        # Shutdown WebSocket transport first
        if self._transport:
            await self._transport.shutdown()
            self._transport = None

        # Cancel stderr reader
        if self._stderr_task and not self._stderr_task.done():
            self._stderr_task.cancel()
            try:
                await self._stderr_task
            except asyncio.CancelledError:
                pass
            self._stderr_task = None

        # Terminate the subprocess
        await self._terminate_process()

        self._notification_queue = None
        self._realtime_notification_queue = None
        self._active_threads.clear()

        logger.info(f"[Instance {self._instance_id}] Shutdown complete")
