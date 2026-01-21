"""
Codex MCP client implementation.

This module provides a client that communicates with Codex via the MCP server pool,
implementing the AIClient interface for the provider abstraction.

The client uses a pool of persistent MCP server connections managed by CodexServerPool,
enabling parallel request handling for multi-agent conversations without the
bottleneck of a single shared server.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, Optional, Union

from providers.base import AIClient

from .events import agent_message, error, reasoning, thread_started, tool_call
from .mcp_server_pool import CodexServerPool

logger = logging.getLogger("CodexMCPClient")


@dataclass
class CodexMCPOptions:
    """Options for Codex MCP client.

    Attributes:
        system_prompt: System prompt (passed as developer_instructions in config)
        model: Model to use (optional)
        thread_id: Thread ID for continuing a conversation
        mcp_servers: Dict of MCP server configurations to pass to Codex
        approval_policy: Approval policy - "never", "on-request", "on-failure", "untrusted"
        sandbox: Sandbox mode - "danger-full-access", "workspace-write", "read-only"
        extra_config: Additional config options to pass to the tool (feature settings, etc.)
        cwd: Working directory for the session (use empty dir to avoid picking up AGENTS.md)
    """

    system_prompt: str = ""
    model: Optional[str] = None
    thread_id: Optional[str] = None
    mcp_servers: Dict[str, Any] = field(default_factory=dict)
    approval_policy: str = "never"
    sandbox: str = "danger-full-access"
    extra_config: Dict[str, Any] = field(default_factory=dict)
    cwd: Optional[str] = None


class CodexMCPClient(AIClient):
    """Codex MCP client implementing AIClient interface.

    This client uses the CodexServerPool to communicate with Codex
    via the MCP protocol, providing the same interface as the CLI-based client
    but with better performance through:
    - No subprocess spawn per query (persistent connections)
    - Multiple server instances for parallel request handling
    - Thread affinity routing for conversation continuity

    Usage:
        client = CodexMCPClient(options)
        await client.connect()
        await client.query("Hello!")
        async for message in client.receive_response():
            # Handle streaming events
        await client.disconnect()
    """

    def __init__(self, options: CodexMCPOptions):
        """Initialize with Codex MCP options."""
        self._options = options
        self._connected = False
        self._pending_message: Optional[str] = None
        self._thread_id: Optional[str] = options.thread_id
        self._pool: Optional[CodexServerPool] = None
        self._response_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._response_task: Optional[asyncio.Task[None]] = None

    async def connect(self) -> None:
        """Initialize the client by getting the MCP server pool.

        The actual server connections are managed by the pool singleton,
        which spawns multiple instances for parallel request handling.
        """
        self._pool = await CodexServerPool.get_instance()
        await self._pool.ensure_started()
        self._connected = True
        logger.debug("CodexMCPClient connected to MCP server pool")

    async def disconnect(self) -> None:
        """Disconnect the client.

        Note: This does NOT shutdown the pool since it's shared.
        If a thread_id is active, it will be released from its instance.
        """
        # Release thread affinity when disconnecting
        if self._pool and self._thread_id:
            await self._pool.release_thread(self._thread_id)

        self._connected = False
        self._pool = None
        if self._response_task and not self._response_task.done():
            self._response_task.cancel()
            try:
                await self._response_task
            except asyncio.CancelledError:
                pass
        logger.debug("CodexMCPClient disconnected")

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
            raise ValueError("Codex MCP client only supports string messages")

    def receive_response(self) -> AsyncIterator[Dict[str, Any]]:
        """Receive response from Codex.

        Returns:
            Async iterator of JSON event dicts (compatible with CodexStreamParser)

        Raises:
            RuntimeError: If no pending message
        """
        return self._receive_response_impl()

    async def _receive_response_impl(self) -> AsyncIterator[Dict[str, Any]]:
        """Implementation of receive_response as async generator.

        MCP returns complete responses (not streaming), so we emit events
        in a format compatible with the existing CodexStreamParser.

        Uses event helper functions from events.py for consistent event creation.
        """
        if self._pending_message is None:
            raise RuntimeError("No pending message. Call query() first.")

        if self._pool is None:
            raise RuntimeError("MCP pool not initialized")

        message = self._pending_message
        self._pending_message = None

        # Build config for the MCP tool call
        config = self._build_config()

        logger.info(f"Calling Codex MCP pool with thread_id={self._thread_id}, message: {message[:100]}...")

        try:
            # Call the MCP tool via the pool (handles instance routing)
            result = await self._pool.call_codex(
                prompt=message,
                config=config,
                thread_id=self._thread_id,
                approval_policy=self._options.approval_policy,
                sandbox=self._options.sandbox,
                cwd=self._options.cwd,
            )

            # Extract thread_id from result
            new_thread_id = result.get("thread_id")
            if new_thread_id:
                self._thread_id = new_thread_id
                # Emit thread.started event using helper
                yield thread_started(new_thread_id)

            # Process content into events
            for content_item in result.get("content", []):
                content_type = content_item.get("type", "")

                if content_type == "text":
                    text = content_item.get("text", "")
                    if text:
                        # Emit as item.completed with agent_message type
                        yield agent_message(text)

                elif content_type == "reasoning":
                    # Reasoning extracted from MCP result summary
                    text = content_item.get("text", "")
                    if text:
                        yield reasoning(text)

                elif content_type == "json":
                    data = content_item.get("data", {})
                    # Check for thread_id in JSON data
                    if "threadId" in data and not self._thread_id:
                        json_thread_id: str = data["threadId"]
                        self._thread_id = json_thread_id
                        yield thread_started(json_thread_id)

                    # Check for message content
                    if "message" in data:
                        yield agent_message(data["message"])

                    # Check for reasoning/thinking content
                    if "reasoning" in data:
                        yield reasoning(data["reasoning"])

                    # Check for tool calls
                    if "toolCalls" in data:
                        for tc in data["toolCalls"]:
                            tool_name = tc.get("name", "")
                            tool_args = tc.get("arguments", {})
                            yield tool_call(tool_name, tool_args)

            # Check for error
            if result.get("is_error"):
                yield error("MCP tool call returned error")

        except Exception as e:
            logger.error(f"Error calling Codex MCP: {e}")
            yield error(str(e))

    def _build_config(self) -> Dict[str, Any]:
        """Build the config dict for the MCP tool call."""
        config: Dict[str, Any] = {}

        # Add MCP servers configuration
        if self._options.mcp_servers:
            config["mcp_servers"] = self._options.mcp_servers

        # Add developer instructions (system prompt)
        # This is injected into the session without replacing default instructions
        if self._options.system_prompt:
            config["developer_instructions"] = self._options.system_prompt

        # Add model if specified
        if self._options.model:
            config["model"] = self._options.model

        # Merge extra config (feature settings, etc.)
        if self._options.extra_config:
            config.update(self._options.extra_config)

        return config

    async def interrupt(self) -> None:
        """Interrupt the current response.

        Note: MCP calls are synchronous, so this mainly cancels any waiting tasks.
        """
        if self._response_task and not self._response_task.done():
            self._response_task.cancel()
            logger.info("Interrupted Codex MCP response")

    @property
    def session_id(self) -> Optional[str]:
        """Get the current thread ID for resume support."""
        return self._thread_id or self._options.thread_id

    @property
    def options(self) -> CodexMCPOptions:
        """Get the Codex MCP options object."""
        return self._options

    @options.setter
    def options(self, value: CodexMCPOptions) -> None:
        """Update the Codex MCP options object."""
        self._options = value
        # Update thread_id if provided in new options
        if value.thread_id:
            self._thread_id = value.thread_id
