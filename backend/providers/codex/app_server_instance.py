"""
Single Codex App Server instance using the official openai-codex SDK.

This module manages one `codex app-server` subprocess via the SDK's
`AsyncCodexClient`, its JSON-RPC surface. The high-level `AsyncCodex`/
`AsyncThread` wrappers are not used because `AsyncThread.turn()` cannot carry
per-turn `baseInstructions`, which is how each agent's system prompt is sent.

The SDK handles:
- Subprocess lifecycle (stdio transport) and launch-arg assembly
- JSON-RPC protocol framing
- Initialize handshake
- Per-turn notification routing
- Typed Pydantic notification models (AgentMessageDelta, ItemCompleted, etc.)

This module provides ChitChats-specific wrapping:
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

from openai_codex import CodexConfig
from openai_codex.async_client import AsyncCodexClient
from openai_codex.errors import CodexError, TransportClosedError
from openai_codex.generated.v2_all import (
    AgentMessageDeltaNotification,
    ImageGenerationThreadItem,
    ItemCompletedNotification,
    McpToolCallThreadItem,
    ReasoningSummaryTextDeltaNotification,
    ReasoningTextDeltaNotification,
    TurnCompletedNotification,
    TurnStartedNotification,
)
from openai_codex.models import Notification, UnknownNotification

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

        self._client: Optional[AsyncCodexClient] = None
        self._active_threads: Set[str] = set()
        self._current_turn_id: Optional[str] = None

        self._last_activity: float = time.monotonic()
        self._created_at: float = time.monotonic()

    @property
    def instance_id(self) -> int:
        return self._instance_id

    @property
    def _proc(self):
        """The app-server subprocess, owned by the SDK's sync transport."""
        if self._client is None:
            return None
        return self._client._sync._proc

    @property
    def is_started(self) -> bool:
        return self._proc is not None

    @property
    def is_healthy(self) -> bool:
        proc = self._proc
        return proc is not None and proc.poll() is None  # Process still running

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
        proc = self._proc
        return proc.pid if proc else None

    def kill(self) -> None:
        """Forcefully kill the subprocess (sync, for emergency cleanup)."""
        proc = self._proc
        if proc:
            try:
                proc.kill()
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

    def _build_sdk_config(self) -> CodexConfig:
        """Build CodexConfig for the official SDK.

        The SDK assembles the launch command itself: it renders each override as
        `--config key=value` and appends `app-server --listen stdio://`.
        """
        codex_path = shutil.which("codex")
        if not codex_path:
            raise RuntimeError("Codex CLI not found. Install it with: npm install -g @openai/codex")

        return CodexConfig(
            codex_bin=codex_path,
            config_overrides=self._startup_config.to_config_overrides(),
            env={"BROWSER": ""},  # Prevent subprocess from opening browser
            client_name="chitchats",
            client_version="1.0.0",
        )

    async def start(self) -> None:
        """Start the Codex App Server using the official SDK."""
        if self.is_started:
            return

        sdk_config = self._build_sdk_config()

        logger.info(
            f"[Instance {self._instance_id}] Starting Codex App Server via official SDK "
            f"({sdk_config.codex_bin}, {len(sdk_config.config_overrides)} config overrides)"
        )

        client = AsyncCodexClient(sdk_config)
        try:
            await client.start()
            await client.initialize()
        except Exception:
            await client.close()
            raise

        self._client = client
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
            result = await self._client.thread_start(params)
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
            result = await self._client.thread_resume(thread_id)
            resumed_id = result.thread.id if result.thread else None
            if resumed_id:
                self.register_thread(thread_id)
                logger.info(f"[Instance {self._instance_id}] Resumed thread {thread_id}")
                return True
            else:
                logger.warning(f"[Instance {self._instance_id}] Resume returned no thread: {result}")
                return False
        except (CodexError, TransportClosedError) as e:
            logger.debug(f"[Instance {self._instance_id}] Failed to resume thread {thread_id}: {e}")
            return False

    async def start_turn(
        self,
        thread_id: str,
        input_items: List[Dict[str, Any]],
        config: CodexTurnConfig,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Start a turn and stream events.

        Consumes the SDK's per-turn notification stream and converts each typed
        Notification to our internal dict format.

        Yields:
            Streaming events as dicts (internal format for parser/client)
        """
        client = self._client
        if not client:
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

        started = await client.turn_start(thread_id, input_items, params=turn_params)
        turn_id = started.turn.id

        # Everything this turn emits is routed to a dedicated queue, NOT the global
        # one `next_notification()` drains — without registering, the events pile up
        # unread and the turn never completes. Registering also replays whatever
        # arrived between turn/start returning and this call.
        client.register_turn_notifications(turn_id)
        try:
            started_event = self._notification_to_event(
                Notification(
                    method="turn/started",
                    payload=UnknownNotification(params={"turnId": turn_id, "threadId": thread_id}),
                )
            )
            if started_event:
                yield started_event

            # Stream notifications until the turn completes. The queue carries only
            # this turn's events, so any turn/completed is ours.
            while True:
                try:
                    notification = await asyncio.wait_for(client.next_turn_notification(turn_id), timeout=120.0)
                except asyncio.TimeoutError:
                    logger.warning(f"[Instance {self._instance_id}] Turn timed out")
                    break
                except TransportClosedError:
                    break

                event = self._notification_to_event(notification)
                if event:
                    yield event

                if notification.method == "turn/completed":
                    break
        finally:
            client.unregister_turn_notifications(turn_id)
            self._current_turn_id = None
            self.touch()

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
            await self._client.turn_interrupt(thread_id, turn_id)
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
                await self._client.close()
            except Exception as e:
                logger.debug(f"[Instance {self._instance_id}] Error closing SDK client: {e}")
            self._client = None

        self._active_threads.clear()
        self._current_turn_id = None

        logger.info(f"[Instance {self._instance_id}] Shutdown complete")
