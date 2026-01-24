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

from .configs import CodexTurnConfig
from .parser import AppServerStreamAccumulator, parse_streaming_event
from .app_server_pool import CodexAppServerPool
from .constants import (
    AppServerMethod,
    SessionRecoveryError,
    agent_message,
    content_delta,
    error,
    reasoning,
    thinking_delta,
    thread_started,
    tool_call,
)
from .images import CodexImageManager

logger = logging.getLogger("CodexAppServerClient")


@dataclass
class CodexAppServerOptions:
    """Options for Codex App Server client.

    These are per-turn options passed to the client. Static settings like
    approval_policy and sandbox are handled by CodexStartupConfig at
    app-server launch time.

    Attributes:
        system_prompt: System prompt (passed as developer_instructions in config)
        model: Model to use (optional)
        thread_id: Thread ID for continuing a conversation
        mcp_servers: Dict of MCP server configurations to pass to Codex
        cwd: Working directory for the session
    """

    system_prompt: str = ""
    model: Optional[str] = None
    thread_id: Optional[str] = None
    mcp_servers: Dict[str, Any] = field(default_factory=dict)
    cwd: Optional[str] = None


class CodexAppServerClient(AIClient):
    """Codex App Server client implementing AIClient interface.

    This client uses the CodexAppServerPool to communicate with Codex
    via the JSON-RPC protocol, providing streaming responses.

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
        self._interrupt_requested = False
        self._current_turn_task: Optional[asyncio.Task] = None
        self._image_manager: Optional[CodexImageManager] = None

    async def connect(self) -> None:
        """Initialize the client by getting the App Server pool.

        The actual server connections are managed by the singleton pool.
        """
        self._pool = await CodexAppServerPool.get_instance()
        await self._pool.ensure_started()
        self._connected = True
        logger.debug("CodexAppServerClient connected to App Server pool")

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
        Supports multimodal content with images (saved to temp files).

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

        # Create new image manager for this turn (will be cleaned up after turn)
        self._image_manager = CodexImageManager()

        # Handle different message formats
        if isinstance(message, str):
            # Simple text message
            self._pending_input_items = [{"type": "text", "text": message}]

        elif isinstance(message, list):
            # List of content blocks - process with image manager
            self._pending_input_items = self._image_manager.process_content_blocks(message)
            if self._image_manager.temp_file_count > 0:
                logger.info(f"Created {self._image_manager.temp_file_count} temp image files for Codex")

        elif hasattr(message, "__aiter__"):
            # Async iterator - collect blocks then process
            content_blocks = []
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

            self._pending_input_items = self._image_manager.process_content_blocks(content_blocks)
            if self._image_manager.temp_file_count > 0:
                logger.info(f"Created {self._image_manager.temp_file_count} temp image files for Codex")

        else:
            raise ValueError(f"Unsupported message type: {type(message)}")

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

        if self._pool is None:
            raise RuntimeError("App Server pool not initialized")

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
            # Create thread if needed
            if not self._thread_id:
                self._thread_id = await self._pool.create_thread(config)
                yield thread_started(self._thread_id)  # thread_id is guaranteed non-None here

            # Ensure we have a valid thread_id at this point
            thread_id = self._thread_id
            if not thread_id:
                raise RuntimeError("Failed to create thread")

            # Use accumulator to collect streaming events
            accumulator = AppServerStreamAccumulator()

            # Stream turn events
            async for event in self._pool.start_turn(thread_id, input_items, config):
                if self._interrupt_requested:
                    await self._pool.interrupt_turn(thread_id)
                    break

                # Check for JSON-RPC format (method field)
                method = event.get("method", "")
                if method:
                    # Handle JSON-RPC format
                    params = event.get("params", {})
                    if method == AppServerMethod.TURN_STARTED:
                        pass
                    elif method == AppServerMethod.AGENT_MESSAGE_DELTA:
                        delta_text = params.get("delta", "")
                        if delta_text:
                            accumulator.add_text(delta_text)
                            self._streamed_content = True
                            yield content_delta(delta_text)
                    elif method == AppServerMethod.REASONING_DELTA:
                        delta_text = params.get("delta", "")
                        if delta_text:
                            accumulator.add_reasoning(delta_text)
                            self._streamed_reasoning = True
                            yield thinking_delta(delta_text)
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
                else:
                    # Handle streaming format (type/payload)
                    parsed = parse_streaming_event(event)
                    accumulator.add_event(parsed)

                    # Handle tool calls from streaming format
                    if parsed.tool_calls:
                        for tc in parsed.tool_calls:
                            yield tool_call(tc.get("name", ""), tc.get("input", {}))

                # Check if completed
                if accumulator.is_completed:
                    break

            # Emit accumulated content only if we didn't stream it
            # (streaming via deltas already sent the content incrementally)
            if accumulator.accumulated_text and not getattr(self, '_streamed_content', False):
                yield agent_message(accumulator.accumulated_text)
            if accumulator.accumulated_reasoning and not getattr(self, '_streamed_reasoning', False):
                yield reasoning(accumulator.accumulated_reasoning)

            # Reset streaming flags for next turn
            self._streamed_content = False
            self._streamed_reasoning = False

        except SessionRecoveryError:
            # Let this propagate up to ResponseGenerator for retry with full history
            raise

        except Exception as e:
            logger.error(f"Error in App Server turn: {e}")
            yield error(str(e))

        finally:
            # Clean up temporary image files
            if self._image_manager:
                removed = self._image_manager.cleanup()
                if removed > 0:
                    logger.debug(f"Cleaned up {removed} temp image files")
                self._image_manager = None

    def _build_config(self) -> CodexTurnConfig:
        """Build the CodexTurnConfig for the turn."""
        return CodexTurnConfig(
            developer_instructions=self._options.system_prompt,
            model=self._options.model,
            mcp_servers=self._options.mcp_servers,
            cwd=self._options.cwd,
        )

    async def interrupt(self) -> None:
        """Interrupt the current response."""
        self._interrupt_requested = True
        if self._thread_id and self._pool:
            await self._pool.interrupt_turn(self._thread_id)
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
