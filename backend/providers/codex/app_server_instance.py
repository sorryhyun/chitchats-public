"""
Single Codex App Server instance using the official codex-app-server SDK.

This module manages one `codex app-server` subprocess via the official
sync Python SDK (AppServerClient), bridged to async via asyncio.to_thread().

The SDK handles:
- Subprocess lifecycle (stdio transport)
- JSON-RPC protocol framing
- Initialize handshake
- Typed Pydantic notification models (AgentMessageDelta, ItemCompleted, etc.)

This module provides ChitChats-specific wrapping:
- Async bridge via asyncio.to_thread()
- Per-agent instance management
- Thread ownership tracking
- Streaming turn events converted to internal dict format
- Idle timeout tracking
"""

import asyncio
import logging
import shutil
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Set

from codex_app_server import AppServerClient, AppServerConfig
from codex_app_server.errors import AppServerError, TransportClosedError
from codex_app_server.generated.v2_all import (
    AgentMessageDeltaNotification,
    ImageGenerationThreadItem,
    ItemCompletedNotification,
    McpToolCallThreadItem,
    ReasoningSummaryTextDeltaNotification,
    ReasoningTextDeltaNotification,
    TurnCompletedNotification,
    TurnStartedNotification,
)
from codex_app_server.models import Notification, UnknownNotification

from providers.configs import DEFAULT_CODEX_CONFIG, CodexStartupConfig, CodexTurnConfig

from .constants import (
    AppServerMethod,
    agent_message,
    error,
    generated_image,
    reasoning,
    tool_call,
)

logger = logging.getLogger("CodexAppServerInstance")


class CodexAppServerInstance:
    """Single Codex App Server instance.

    Manages one `codex app-server` subprocess via the official Python SDK.
    All blocking SDK calls are bridged to async via asyncio.to_thread().

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
        self._instance_id = instance_id
        self._startup_config = startup_config or DEFAULT_CODEX_CONFIG
        self._agent_key = agent_key

        self._client: Optional[AppServerClient] = None
        self._active_threads: Set[str] = set()
        self._current_turn_id: Optional[str] = None

        self._last_activity: float = time.monotonic()
        self._created_at: float = time.monotonic()

    @property
    def instance_id(self) -> int:
        return self._instance_id

    @property
    def is_started(self) -> bool:
        return self._client is not None and self._client._proc is not None

    @property
    def is_healthy(self) -> bool:
        if self._client is None or self._client._proc is None:
            return False
        return self._client._proc.poll() is None  # Process still running

    @property
    def active_thread_count(self) -> int:
        return len(self._active_threads)

    @property
    def active_threads(self) -> Set[str]:
        return self._active_threads.copy()

    @property
    def agent_key(self) -> Optional[str]:
        return self._agent_key

    @property
    def last_activity(self) -> float:
        return self._last_activity

    @property
    def idle_seconds(self) -> float:
        return time.monotonic() - self._last_activity

    @property
    def process_pid(self) -> Optional[int]:
        if self._client and self._client._proc:
            return self._client._proc.pid
        return None

    def kill(self) -> None:
        """Forcefully kill the subprocess (sync, for emergency cleanup)."""
        if self._client and self._client._proc:
            try:
                self._client._proc.kill()
            except ProcessLookupError:
                pass

    def touch(self) -> None:
        self._last_activity = time.monotonic()

    def owns_thread(self, thread_id: str) -> bool:
        return thread_id in self._active_threads

    def register_thread(self, thread_id: str) -> None:
        self._active_threads.add(thread_id)
        logger.debug(f"[Instance {self._instance_id}] Registered thread {thread_id}")

    def release_thread(self, thread_id: str) -> bool:
        if thread_id in self._active_threads:
            self._active_threads.discard(thread_id)
            logger.debug(f"[Instance {self._instance_id}] Released thread {thread_id}")
            return True
        return False

    def _build_sdk_config(self) -> AppServerConfig:
        """Build AppServerConfig for the official SDK."""
        codex_path = shutil.which("codex")
        if not codex_path:
            raise RuntimeError("Codex CLI not found. Install it with: npm install -g @openai/codex")

        # Build CLI args from startup config
        cli_args = self._startup_config.to_cli_args()

        # The SDK expects launch_args_override as the full command
        # Format: codex --config key=value ... app-server --listen stdio://
        launch_args = [codex_path]
        # Convert -c flags to --config flags (SDK uses --config)
        i = 0
        while i < len(cli_args):
            if cli_args[i] == "-c" and i + 1 < len(cli_args):
                launch_args.extend(["--config", cli_args[i + 1]])
                i += 2
            else:
                launch_args.append(cli_args[i])
                i += 1
        launch_args.extend(["app-server", "--listen", "stdio://"])

        env = {"BROWSER": ""}  # Prevent subprocess from opening browser

        return AppServerConfig(
            launch_args_override=tuple(launch_args),
            env=env,
            client_name="chitchats",
            client_version="1.0.0",
        )

    async def start(self) -> None:
        """Start the Codex App Server using the official SDK."""
        if self.is_started:
            return

        sdk_config = self._build_sdk_config()

        logger.info(
            f"[Instance {self._instance_id}] Starting Codex App Server via official SDK, "
            f"command: {' '.join(sdk_config.launch_args_override or [])}"
        )

        def _start_sync():
            client = AppServerClient(sdk_config)
            client.start()
            client.initialize()
            return client

        try:
            self._client = await asyncio.to_thread(_start_sync)
        except Exception:
            self._client = None
            raise

        logger.info(f"[Instance {self._instance_id}] Codex App Server started (PID: {self.process_pid})")

    async def create_thread(self, config: CodexTurnConfig) -> str:
        """Create a new thread for conversation."""
        if not self._client:
            raise RuntimeError("Instance not started")

        params: Dict[str, Any] = {}
        if config.cwd:
            params["cwd"] = config.cwd
        if config.model:
            params["model"] = config.model
        if config.developer_instructions:
            params["baseInstructions"] = config.developer_instructions
        params["sandbox"] = self._startup_config.sandbox
        params["approvalPolicy"] = self._startup_config.approval_policy

        logger.debug(f"[Instance {self._instance_id}] Creating thread with params: {params}")

        try:
            result = await asyncio.to_thread(self._client.thread_start, params)
        except Exception as e:
            if "validation error" in str(e).lower():
                raise RuntimeError("코덱스 업데이트해주세요!") from e
            raise

        thread_id = result.thread.id
        if not thread_id:
            raise RuntimeError(f"thread/start did not return thread.id: {result}")

        self.register_thread(thread_id)
        logger.info(f"[Instance {self._instance_id}] Created thread {thread_id}")
        return thread_id

    async def resume_thread(self, thread_id: str, config: CodexTurnConfig) -> bool:  # noqa: ARG002
        """Resume an existing thread by ID."""
        if not self._client:
            raise RuntimeError("Instance not started")

        logger.debug(f"[Instance {self._instance_id}] Resuming thread {thread_id}")

        try:
            result = await asyncio.to_thread(self._client.thread_resume, thread_id)
            resumed_id = result.thread.id if result.thread else None
            if resumed_id:
                self.register_thread(thread_id)
                logger.info(f"[Instance {self._instance_id}] Resumed thread {thread_id}")
                return True
            else:
                logger.warning(f"[Instance {self._instance_id}] Resume returned no thread: {result}")
                return False
        except (AppServerError, TransportClosedError) as e:
            logger.debug(f"[Instance {self._instance_id}] Failed to resume thread {thread_id}: {e}")
            return False

    async def start_turn(
        self,
        thread_id: str,
        input_items: List[Dict[str, Any]],
        config: CodexTurnConfig,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Start a turn and stream events.

        Uses the SDK's sync API in a background thread, piping typed
        Notification objects through an asyncio.Queue and converting
        them to internal dict format.

        Yields:
            Streaming events as dicts (internal format for parser/client)
        """
        if not self._client:
            raise RuntimeError("Instance not started")

        self.touch()

        # Log input summary
        text_items = [item.get("text", "")[:50] for item in input_items if item.get("type") == "text"]
        image_count = sum(1 for item in input_items if item.get("type") in ("localImage", "image"))
        logger.info(
            f"[Instance {self._instance_id}] Starting turn on thread {thread_id}, "
            f"items: {len(input_items)} ({image_count} images), "
            f"text preview: {text_items[0] if text_items else '(no text)'}..."
        )

        # Build turn params
        turn_params: Dict[str, Any] = {}
        if config.developer_instructions:
            turn_params["baseInstructions"] = config.developer_instructions
        if config.model:
            turn_params["model"] = config.model

        # Queue for passing notifications from sync thread to async
        queue: asyncio.Queue[Optional[Notification]] = asyncio.Queue()
        turn_error: List[Optional[Exception]] = [None]

        def _run_turn_sync():
            """Run the turn in a sync thread, collecting notifications."""
            try:
                client = self._client
                if client is None:
                    return

                # Start the turn
                started = client.turn_start(thread_id, input_items, params=turn_params)
                turn_id = started.turn.id

                # Put turn started event
                turn_started_notif = Notification(
                    method="turn/started",
                    payload=UnknownNotification(params={"turnId": turn_id, "threadId": thread_id}),
                )
                queue.put_nowait(turn_started_notif)

                # Stream notifications until turn completes
                while True:
                    try:
                        notification = client.next_notification()
                        queue.put_nowait(notification)

                        # Check for turn completion
                        if notification.method == "turn/completed":
                            if isinstance(notification.payload, TurnCompletedNotification):
                                if notification.payload.turn.id == turn_id:
                                    break
                            else:
                                break
                    except TransportClosedError:
                        break
                    except Exception as e:
                        turn_error[0] = e
                        break
            except Exception as e:
                turn_error[0] = e
            finally:
                # Signal completion
                queue.put_nowait(None)

        # Run the sync turn in a background thread
        loop = asyncio.get_event_loop()
        turn_future = loop.run_in_executor(None, _run_turn_sync)

        try:
            while True:
                try:
                    notification = await asyncio.wait_for(queue.get(), timeout=120.0)
                except asyncio.TimeoutError:
                    logger.warning(f"[Instance {self._instance_id}] Turn timed out")
                    break

                if notification is None:
                    # Turn completed or errored
                    break

                # Convert typed Notification to internal dict format
                event = self._notification_to_event(notification)
                if event:
                    yield event

                # Check for turn completion in the event
                method = notification.method
                if method == "turn/completed":
                    break
        finally:
            self._current_turn_id = None
            self.touch()
            # Ensure the background thread completes
            try:
                await asyncio.wait_for(asyncio.wrap_future(turn_future), timeout=5.0)
            except (asyncio.TimeoutError, Exception):
                pass

        # Propagate errors from the sync thread
        if turn_error[0]:
            logger.error(f"[Instance {self._instance_id}] Turn error: {turn_error[0]}")

    def _notification_to_event(self, notification: Notification) -> Optional[Dict[str, Any]]:
        """Convert a typed SDK Notification to our internal event dict format."""
        method = notification.method
        payload = notification.payload

        # Turn started
        if method == "turn/started":
            if isinstance(payload, TurnStartedNotification):
                self._current_turn_id = payload.turn.id
                return {"method": AppServerMethod.TURN_STARTED, "params": {"turnId": payload.turn.id}}
            elif isinstance(payload, UnknownNotification):
                turn_id = payload.params.get("turnId")
                self._current_turn_id = turn_id
                return {"method": AppServerMethod.TURN_STARTED, "params": {"turnId": turn_id}}

        # Agent message delta (streaming text)
        if method == "item/agentMessage/delta" and isinstance(payload, AgentMessageDeltaNotification):
            return agent_message(payload.delta) if payload.delta else None

        # Reasoning text delta (streaming thinking)
        if method == "item/reasoning/textDelta" and isinstance(payload, ReasoningTextDeltaNotification):
            return reasoning(payload.delta) if payload.delta else None

        # Reasoning summary text delta
        if method == "item/reasoning/summaryTextDelta" and isinstance(payload, ReasoningSummaryTextDeltaNotification):
            return reasoning(payload.delta) if payload.delta else None

        # Item completed (tool calls, final messages)
        if method == "item/completed" and isinstance(payload, ItemCompletedNotification):
            item = payload.item.root  # Unwrap RootModel
            if isinstance(item, McpToolCallThreadItem):
                # Parse arguments
                args = item.arguments
                if isinstance(args, str):
                    import json
                    try:
                        args = json.loads(args)
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                return tool_call(item.tool, args if isinstance(args, dict) else {})

            if isinstance(item, ImageGenerationThreadItem):
                # Codex generated an image. Persist to disk and emit an event.
                from infrastructure.generated_images import save_generated_image

                saved = save_generated_image(item.result or "", media_type="image/png")
                if saved is None:
                    logger.warning(
                        f"[Instance {self._instance_id}] Failed to persist generated image "
                        f"(id={item.id}, status={item.status})"
                    )
                    return None
                url, media_type = saved
                return generated_image(url, media_type, item.revised_prompt or "")

        # Turn completed
        if method == "turn/completed":
            params: Dict[str, Any] = {}
            if isinstance(payload, TurnCompletedNotification):
                params["turnId"] = payload.turn.id
                status = getattr(payload.turn, "status", None)
                if status:
                    status_val = status.value if hasattr(status, "value") else str(status)
                    params["status"] = status_val
                    if status_val == "failed":
                        return error(f"Turn failed: {payload.turn.id}")
            return {"method": AppServerMethod.TURN_COMPLETED, "params": params}

        # Other notifications (ignored for now)
        return None

    async def interrupt_turn(self, thread_id: str, turn_id: Optional[str] = None) -> bool:
        """Interrupt an ongoing turn."""
        if not self._client:
            return False

        turn_id = turn_id or self._current_turn_id
        if not turn_id:
            logger.warning(f"[Instance {self._instance_id}] No turn to interrupt")
            return False

        logger.info(f"[Instance {self._instance_id}] Interrupting turn {turn_id}")

        try:
            await asyncio.to_thread(self._client.turn_interrupt, thread_id, turn_id)
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

        if self._client:
            try:
                await asyncio.to_thread(self._client.close)
            except Exception as e:
                logger.debug(f"[Instance {self._instance_id}] Error closing SDK client: {e}")
            self._client = None

        self._active_threads.clear()
        self._current_turn_id = None

        logger.info(f"[Instance {self._instance_id}] Shutdown complete")
