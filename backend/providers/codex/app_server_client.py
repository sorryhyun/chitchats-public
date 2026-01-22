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
from typing import Any, AsyncIterator, Dict, Optional, Union

from providers.base import AIClient

from .app_server_instance import AppServerConfig
from .app_server_parser import AppServerStreamAccumulator, parse_streaming_event
from .app_server_pool import CodexAppServerPool
from .events import (
    AppServerMethod,
    SessionRecoveryError,
    agent_message,
    error,
    reasoning,
    thread_started,
    tool_call,
)

logger = logging.getLogger("CodexAppServerClient")


@dataclass
class CodexAppServerOptions:
    """Options for Codex App Server client.

    Attributes:
        system_prompt: System prompt (passed as developer_instructions in config)
        model: Model to use (optional)
        thread_id: Thread ID for continuing a conversation
        mcp_servers: Dict of MCP server configurations to pass to Codex
        approval_policy: Approval policy - "never", "on-request", "on-failure", "untrusted"
        sandbox: Sandbox mode - "danger-full-access", "workspace-write", "read-only"
        extra_config: Additional config options
        cwd: Working directory for the session
    """

    system_prompt: str = ""
    model: Optional[str] = None
    thread_id: Optional[str] = None
    mcp_servers: Dict[str, Any] = field(default_factory=dict)
    approval_policy: str = "never"
    sandbox: str = "danger-full-access"
    extra_config: Dict[str, Any] = field(default_factory=dict)
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
        self._pending_message: Optional[str] = None
        self._thread_id: Optional[str] = options.thread_id
        self._pool: Optional[CodexAppServerPool] = None
        self._interrupt_requested = False
        self._current_turn_task: Optional[asyncio.Task] = None

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

    async def query(self, message: Union[str, AsyncIterator[dict]]) -> None:
        """Send a message to Codex.

        This stores the message to be sent when receive_response() is called.

        Args:
            message: The message content (string only for Codex)

        Raises:
            RuntimeError: If client is not connected
            ValueError: If message is not a string
        """
        if not self._connected:
            raise RuntimeError("Client not connected. Call connect() first.")

        # Extract string message
        if isinstance(message, str):
            self._pending_message = message
        elif hasattr(message, "__aiter__"):
            # Async iterator - try to extract text content
            text_parts = []
            async for block in message:
                if isinstance(block, dict):
                    msg_data = block.get("message", block)
                    if isinstance(msg_data, dict):
                        content = msg_data.get("content", "")
                        if isinstance(content, str):
                            text_parts.append(content)
                        elif isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict) and item.get("type") == "text":
                                    text_parts.append(item.get("text", ""))
                    elif isinstance(msg_data, str):
                        text_parts.append(msg_data)
            self._pending_message = "\n".join(text_parts)
        else:
            raise ValueError("Codex App Server client only supports string messages")

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
        if self._pending_message is None:
            raise RuntimeError("No pending message. Call query() first.")

        if self._pool is None:
            raise RuntimeError("App Server pool not initialized")

        message = self._pending_message
        self._pending_message = None
        self._interrupt_requested = False

        # Build config for the turn
        config = self._build_config()

        logger.info(
            f"Starting App Server turn thread_id={self._thread_id}, message: {message[:100]}..."
        )

        try:
            # Create thread if needed
            if not self._thread_id:
                new_thread_id = await self._pool.create_thread(config)
                self._thread_id = new_thread_id
                yield thread_started(new_thread_id)

            # Ensure we have a valid thread_id at this point
            thread_id = self._thread_id
            if not thread_id:
                raise RuntimeError("Failed to create thread")

            # Use accumulator to collect streaming events
            accumulator = AppServerStreamAccumulator()

            # Stream turn events
            async for event in self._pool.start_turn(thread_id, message, config):
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
                        delta = params.get("delta", "")
                        if delta:
                            accumulator.add_text(delta)
                    elif method == AppServerMethod.REASONING_DELTA:
                        delta = params.get("delta", "")
                        if delta:
                            accumulator.add_reasoning(delta)
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

            # Emit accumulated content
            if accumulator.accumulated_text:
                yield agent_message(accumulator.accumulated_text)
            if accumulator.accumulated_reasoning:
                yield reasoning(accumulator.accumulated_reasoning)

        except SessionRecoveryError:
            # Let this propagate up to ResponseGenerator for retry with full history
            raise

        except Exception as e:
            logger.error(f"Error in App Server turn: {e}")
            yield error(str(e))

    def _build_config(self) -> AppServerConfig:
        """Build the AppServerConfig for the turn."""
        return AppServerConfig(
            developer_instructions=self._options.system_prompt,
            model=self._options.model,
            mcp_servers=self._options.mcp_servers,
            approval_policy=self._options.approval_policy,
            sandbox=self._options.sandbox,
            cwd=self._options.cwd,
            extra_config=self._options.extra_config,
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
