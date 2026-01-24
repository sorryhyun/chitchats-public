"""
Codex App Server client implementation.

This module provides a client that communicates with Codex via the App Server,
implementing the AIClient interface for the provider abstraction.

The client uses a persistent App Server pool managed by CodexAppServerPool,
enabling parallel request processing with thread ID affinity routing.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Union

from providers.base import AIClient
from providers.configs import CodexStartupConfig, CodexTurnConfig

from .app_server_instance import CodexAppServerInstance
from .app_server_pool import CodexAppServerPool
from .constants import (
    AppServerMethod,
    SessionRecoveryError,
    agent_message,
    error,
    reasoning,
    thread_started,
    tool_call,
)
from .parser import AppServerStreamAccumulator

logger = logging.getLogger("CodexAppServerClient")


@dataclass
class CodexAppServerOptions:
    """Options for Codex App Server client.

    Attributes:
        agent_key: Unique identifier for the agent (e.g., "room_1_agent_5")
        startup_config: Configuration for app-server startup (includes MCP servers)
        system_prompt: System prompt (passed as developer_instructions in config)
        model: Model to use (optional)
        thread_id: Thread ID for continuing a conversation
        cwd: Working directory for the session
    """

    agent_key: str = ""
    startup_config: CodexStartupConfig = field(default_factory=CodexStartupConfig)
    system_prompt: str = ""
    model: Optional[str] = None
    thread_id: Optional[str] = None
    cwd: Optional[str] = None


class CodexAppServerClient(AIClient):
    """Codex App Server client implementing AIClient interface.

    This client uses the CodexAppServerPool to get a per-agent instance
    and communicates with Codex via JSON-RPC protocol, providing streaming responses.

    Usage:
        client = CodexAppServerClient(options)
        await client.connect()
        await client.query("Hello!")
        async for message in client.receive_response():
            # Handle streaming events
        await client.disconnect()
    """

    def __init__(self, options: CodexAppServerOptions):
        """Initialize with Codex App Server options."""
        self._options = options
        self._connected = False
        self._pending_input_items: Optional[List[Dict[str, Any]]] = None
        self._thread_id: Optional[str] = options.thread_id
        self._pool: Optional[CodexAppServerPool] = None
        self._instance: Optional[CodexAppServerInstance] = None
        self._interrupt_requested = False
        self._current_turn_task: Optional[asyncio.Task] = None

    async def connect(self) -> None:
        """Initialize the client by getting the App Server pool and instance.

        Gets or creates a dedicated app-server instance for this agent
        with MCP configurations baked in at startup.
        """
        self._pool = await CodexAppServerPool.get_instance()
        # Get or create instance for this agent
        self._instance = await self._pool.get_or_create_instance(
            agent_key=self._options.agent_key,
            startup_config=self._options.startup_config,
        )
        self._connected = True
        logger.debug(f"CodexAppServerClient connected to instance for {self._options.agent_key}")

    async def disconnect(self) -> None:
        """Disconnect the client.

        Note: This does NOT shutdown the pool since it's shared.
        """
        self._connected = False
        self._pool = None
        logger.debug("CodexAppServerClient disconnected")

    async def query(self, message: Union[str, AsyncIterator[dict], List[dict]]) -> None:
        """Send a message to Codex.

        This stores the message to be sent when receive_response() is called.
        Supports multimodal content with images.

        Args:
            message: The message content - can be:
                - A string (text only)
                - A list of content blocks (text and image)
                - An async iterator of content blocks

        Raises:
            RuntimeError: If client is not connected
        """
        if not self._connected:
            raise RuntimeError("Client not connected. Call connect() first.")

        # Handle different message formats
        if isinstance(message, str):
            # Simple text message
            self._pending_input_items = [{"type": "text", "text": message}]

        elif isinstance(message, list):
            # List of content blocks - convert to Codex format
            self._pending_input_items = self._convert_content_blocks(message)

        elif hasattr(message, "__aiter__"):
            # Async iterator - collect blocks then process
            content_blocks: List[Dict[str, Any]] = []
            async for block in message:
                if isinstance(block, dict):
                    # Handle various formats from different providers
                    msg_data = block.get("message", block)
                    if isinstance(msg_data, dict):
                        content = msg_data.get("content", "")
                        if isinstance(content, str):
                            content_blocks.append({"type": "text", "text": content})
                        elif isinstance(content, list):
                            content_blocks.extend(content)
                    elif isinstance(msg_data, str):
                        content_blocks.append({"type": "text", "text": msg_data})
                    elif block.get("type"):
                        # Direct content block
                        content_blocks.append(block)

            self._pending_input_items = self._convert_content_blocks(content_blocks)

        else:
            raise ValueError(f"Unsupported message type: {type(message)}")

    @staticmethod
    def _convert_content_blocks(content_blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert Claude-style content blocks to Codex input items.

        Args:
            content_blocks: List of content blocks
                [{"type": "text", "text": "..."},
                 {"type": "image", "source": {"type": "base64", "data": "...", "media_type": "..."}}]

        Returns:
            List of Codex input items
        """
        input_items: List[Dict[str, Any]] = []

        for block in content_blocks:
            block_type = block.get("type")

            if block_type == "text":
                text = block.get("text", "")
                if text:
                    input_items.append({"type": "text", "text": text})

            elif block_type == "image":
                source = block.get("source", {})
                if source.get("type") == "base64":
                    data = source.get("data", "")
                    media_type = source.get("media_type", "image/png")
                    # Use data URL (Codex docs: {"type": "image", "url": "..."})
                    data_url = f"data:{media_type};base64,{data}"
                    input_items.append({"type": "image", "url": data_url})
                    logger.debug(f"Added image: {media_type}, {len(data)} chars base64")

        return input_items

    def receive_response(self) -> AsyncIterator[Dict[str, Any]]:
        """Receive response from Codex.

        Returns:
            Async iterator of JSON event dicts (compatible with parser)

        Raises:
            RuntimeError: If no pending message
        """
        return self._receive_response_impl()

    async def _receive_response_impl(self) -> AsyncIterator[Dict[str, Any]]:
        """Implementation of receive_response as async generator.

        App Server provides streaming notifications, which we translate
        to the unified event format.
        """
        if self._pending_input_items is None:
            raise RuntimeError("No pending input items. Call query() first.")

        if self._instance is None:
            raise RuntimeError("App Server instance not initialized")

        input_items = self._pending_input_items
        self._pending_input_items = None
        self._interrupt_requested = False

        # Build config for the turn
        config = self._build_config()

        # Log input summary
        text_preview = ""
        for item in input_items:
            if item.get("type") == "text":
                text_preview = item.get("text", "")[:100]
                break
        image_count = sum(1 for item in input_items if item.get("type") in ("localImage", "image"))
        logger.info(
            f"Starting App Server turn thread_id={self._thread_id}, "
            f"items: {len(input_items)} ({image_count} images), text: {text_preview}..."
        )

        try:
            # Ensure we have a valid instance and thread (recovers/creates/resumes as needed)
            async for event in self._ensure_valid_instance_and_thread(config):
                yield event

            # Ensure we have a valid thread_id at this point
            thread_id = self._thread_id
            if not thread_id:
                raise RuntimeError("Failed to create thread")

            # Use accumulator to collect streaming events
            accumulator = AppServerStreamAccumulator()

            # Stream turn events
            async for event in self._instance.start_turn(thread_id, input_items, config):
                if self._interrupt_requested:
                    await self._instance.interrupt_turn(thread_id)
                    break

                # Check for JSON-RPC format (method field)
                method = event.get("method", "")
                if method:
                    # Handle JSON-RPC format
                    params = event.get("params", {})
                    if method == AppServerMethod.TURN_STARTED:
                        pass
                    elif method == AppServerMethod.AGENT_MESSAGE_DELTA:
                        delta = params.get("delta", "")
                        if delta:
                            yield agent_message(delta)  # Stream immediately
                    elif method == AppServerMethod.REASONING_DELTA:
                        delta = params.get("delta", "")
                        if delta:
                            yield reasoning(delta)  # Stream immediately
                    elif method == AppServerMethod.ITEM_COMPLETED:
                        item = params.get("item", {})
                        item_type = item.get("type", "")
                        if item_type == "mcpToolCall":
                            tool_name = item.get("name", "")
                            tool_args = item.get("arguments", {})
                            yield tool_call(tool_name, tool_args)
                    elif method == AppServerMethod.TURN_COMPLETED:
                        accumulator.mark_completed()
                        status = params.get("status", "")
                        if status == "failed":
                            error_info = params.get("codexErrorInfo", {})
                            error_msg = error_info.get("message", "Turn failed")
                            yield error(error_msg)

                # Check if completed
                if accumulator.is_completed:
                    break

        except SessionRecoveryError:
            # Let this propagate up to ResponseGenerator for retry with full history
            raise

        except Exception as e:
            logger.error(f"Error in App Server turn: {e}")
            yield error(str(e))

    def _build_config(self) -> CodexTurnConfig:
        """Build the CodexTurnConfig for the turn.

        Note: MCP servers are now configured at app-server startup via
        startup_config, not passed per-turn.
        """
        return CodexTurnConfig(
            developer_instructions=self._options.system_prompt,
            model=self._options.model,
            cwd=self._options.cwd,
        )

    async def _ensure_valid_instance_and_thread(self, config: CodexTurnConfig) -> AsyncIterator[Dict[str, Any]]:
        """Ensure we have a valid instance and thread, recovering as needed.

        This consolidated method handles:
        1. Instance health check and recovery
        2. Thread creation or resume

        Yields:
            thread_started event if a new thread was created

        After this method returns:
        - self._instance is guaranteed to be healthy
        - self._thread_id is guaranteed to be set
        """
        # Step 1: Ensure healthy instance
        if self._instance is None:
            raise RuntimeError("App Server instance not initialized")

        if not self._instance.is_healthy:
            logger.info(
                f"Instance for {self._options.agent_key} is no longer healthy, " "getting fresh instance from pool"
            )
            if self._pool is None:
                raise RuntimeError("Pool not available for instance refresh")

            self._instance = await self._pool.get_or_create_instance(
                agent_key=self._options.agent_key,
                startup_config=self._options.startup_config,
            )
            # Clear thread ownership since we have a new instance
            # Thread will be resumed or recreated below

        # Step 2: Ensure valid thread
        if not self._thread_id:
            # No thread - create a new one
            self._thread_id = await self._instance.create_thread(config)
            if self._pool:
                self._pool.register_thread(self._thread_id, self._options.agent_key)
            yield thread_started(self._thread_id)

        elif not self._instance.owns_thread(self._thread_id):
            # Thread exists but instance doesn't own it (e.g., after restart/recovery)
            logger.info(f"Instance doesn't own thread {self._thread_id}, attempting resume")
            resumed = await self._instance.resume_thread(self._thread_id, config)
            if resumed:
                logger.info(f"Successfully resumed thread {self._thread_id}")
            else:
                # Resume failed - create a new thread
                logger.info(f"Could not resume thread {self._thread_id}, creating new thread")
                self._thread_id = await self._instance.create_thread(config)
                if self._pool:
                    self._pool.register_thread(self._thread_id, self._options.agent_key)
                yield thread_started(self._thread_id)

    async def interrupt(self) -> None:
        """Interrupt the current response."""
        self._interrupt_requested = True
        if self._thread_id and self._instance:
            await self._instance.interrupt_turn(self._thread_id)
            logger.info("Interrupted App Server response")

    @property
    def session_id(self) -> Optional[str]:
        """Get the current thread ID for resume support."""
        return self._thread_id or self._options.thread_id

    @property
    def options(self) -> CodexAppServerOptions:
        """Get the Codex App Server options object."""
        return self._options

    @options.setter
    def options(self, value: CodexAppServerOptions) -> None:
        """Update the Codex App Server options object."""
        self._options = value
        # Update thread_id if provided in new options
        if value.thread_id:
            self._thread_id = value.thread_id
