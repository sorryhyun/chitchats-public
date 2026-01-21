"""
Single Codex MCP server instance.

This module provides the CodexMCPServerInstance class that manages a single
`codex mcp-server` subprocess. Multiple instances can be created and managed
by CodexServerPool for parallel request processing.

Extracted from mcp_server_manager.py for pool support.
"""

import asyncio
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .events import extract_reasoning_from_raw

logger = logging.getLogger("CodexMCPServerInstance")


@dataclass
class ReasoningCapture:
    """Stores captured reasoning text from Codex notifications."""

    texts: List[str] = field(default_factory=list)

    def add(self, text: str) -> None:
        """Add reasoning text."""
        if text and text not in self.texts:
            self.texts.append(text)

    def get_combined(self) -> str:
        """Get all reasoning combined."""
        return "\n".join(self.texts)

    def clear(self) -> None:
        """Clear captured reasoning."""
        self.texts.clear()


class _MCPNotificationCaptureFilter(logging.Filter):
    """Filter that captures reasoning from MCP notification validation failures.

    This combines capture and filtering - it extracts reasoning from the
    "Failed to validate notification" warnings AND suppresses them from output.
    Filters run before handlers, so this ensures we capture the data.
    """

    def __init__(self, reasoning_capture: "ReasoningCapture", instance_id: int):
        super().__init__()
        self._reasoning_capture = reasoning_capture
        self._instance_id = instance_id

    def filter(self, record: logging.LogRecord) -> bool:
        """Capture reasoning and suppress notification validation warnings."""
        msg = record.getMessage()
        if "Failed to validate notification" not in msg:
            return True  # Let other messages through

        # Try to extract reasoning from the notification
        if "Message was:" in msg:
            raw_part = msg.split("Message was:", 1)[1].strip()
            self._extract_reasoning(raw_part)

        return False  # Suppress the warning message

    def _extract_reasoning(self, raw_msg: str) -> None:
        """Extract reasoning from raw notification message.

        Codex notifications have structure:
        params={'_meta': {...}, 'msg': {'type': 'agent_reasoning', 'text': '...'}}
        """
        result = extract_reasoning_from_raw(raw_msg)
        if result:
            text, source = result
            logger.debug(f"[Instance {self._instance_id}] Captured {source}: {len(text)} chars")
            self._reasoning_capture.add(text)


class CodexMCPServerInstance:
    """Single Codex MCP server instance.

    Manages one `codex mcp-server` subprocess with its own request lock
    and thread tracking for affinity routing.

    Usage:
        instance = CodexMCPServerInstance(instance_id=0)
        await instance.start()
        result = await instance.call_codex("Hello!", config={...})
        await instance.shutdown()
    """

    def __init__(self, instance_id: int):
        """Initialize a server instance.

        Args:
            instance_id: Unique identifier for this instance (0, 1, 2, ...)
        """
        self._instance_id = instance_id
        self._session: Optional[ClientSession] = None
        self._read_stream: Optional[Any] = None
        self._write_stream: Optional[Any] = None
        self._process_context: Optional[Any] = None
        self._session_context: Optional[Any] = None
        self._started = False
        self._healthy = True
        self._request_lock = asyncio.Lock()  # Per-instance lock
        self._available_tools: Dict[str, Any] = {}
        self._active_threads: Set[str] = set()  # Threads owned by this instance
        # Reasoning capture shared across requests (cleared before each call)
        self._reasoning_capture = ReasoningCapture()
        self._capture_filter: Optional[_MCPNotificationCaptureFilter] = None

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
        """Release a thread from this instance.

        Returns:
            True if the thread was owned and released, False otherwise
        """
        if thread_id in self._active_threads:
            self._active_threads.discard(thread_id)
            logger.debug(f"[Instance {self._instance_id}] Released thread {thread_id}")
            return True
        return False

    async def start(self) -> None:
        """Start the Codex MCP server process and establish connection."""
        if self._started:
            return

        codex_path = shutil.which("codex")
        if not codex_path:
            raise RuntimeError("Codex CLI not found. Install it with: npm install -g @openai/codex")

        logger.info(f"[Instance {self._instance_id}] Starting Codex MCP server...")

        # Register notification capture filter before starting
        if self._capture_filter is None:
            self._capture_filter = _MCPNotificationCaptureFilter(
                self._reasoning_capture, self._instance_id
            )
            logging.getLogger().addFilter(self._capture_filter)
            logger.debug(f"[Instance {self._instance_id}] Registered notification capture filter")

        # Create server parameters for stdio transport
        server_params = StdioServerParameters(
            command=codex_path,
            args=["mcp-server"],
            env={**os.environ},
        )

        # Start the server process with stdio transport
        self._process_context = stdio_client(server_params)
        read_stream, write_stream = await self._process_context.__aenter__()
        self._read_stream = read_stream
        self._write_stream = write_stream

        # Create MCP session
        self._session_context = ClientSession(read_stream, write_stream)  # type: ignore[arg-type]
        session = await self._session_context.__aenter__()
        self._session = session
        assert session is not None, "MCP session failed to initialize"

        # Initialize the session
        await session.initialize()

        # Discover available tools
        tools_result = await session.list_tools()
        self._available_tools = {tool.name: tool for tool in tools_result.tools}

        logger.info(
            f"[Instance {self._instance_id}] Codex MCP server started. "
            f"Tools: {list(self._available_tools.keys())}"
        )
        self._started = True
        self._healthy = True

    async def call_codex(
        self,
        prompt: str,
        config: Optional[Dict[str, Any]] = None,
        thread_id: Optional[str] = None,
        approval_policy: str = "never",
        sandbox: str = "danger-full-access",
        cwd: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Call the Codex MCP tool.

        Args:
            prompt: The prompt/message to send
            config: Configuration dict (mcp_servers, developer_instructions, etc.)
            thread_id: Optional thread ID for continuing a conversation
            approval_policy: Approval policy - "never", "on-request", "on-failure", "untrusted"
            sandbox: Sandbox mode - "danger-full-access", "workspace-write", "read-only"
            cwd: Working directory for the session

        Returns:
            Dict containing the tool response with content and threadId
        """
        if not self._started:
            raise RuntimeError(f"[Instance {self._instance_id}] Server not started")

        async with self._request_lock:
            return await self._call_tool_impl(prompt, config, thread_id, approval_policy, sandbox, cwd)

    async def _call_tool_impl(
        self,
        prompt: str,
        config: Optional[Dict[str, Any]],
        thread_id: Optional[str],
        approval_policy: str,
        sandbox: str,
        cwd: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Implementation of the tool call."""
        if self._session is None:
            raise RuntimeError(f"[Instance {self._instance_id}] MCP session not initialized")

        # Clear reasoning capture before the call
        self._reasoning_capture.clear()

        # Determine which tool to use
        tool_name = "codex-reply" if thread_id else "codex"

        # Build arguments
        arguments: Dict[str, Any] = {
            "prompt": prompt,
            "approval-policy": approval_policy,
            "sandbox": sandbox,
        }

        if cwd:
            arguments["cwd"] = cwd

        if config:
            arguments["config"] = config

        if thread_id:
            arguments["threadId"] = thread_id

        logger.info(
            f"[Instance {self._instance_id}] Calling '{tool_name}' "
            f"thread_id={thread_id}, prompt: {prompt[:100]}..."
        )

        try:
            result = await self._session.call_tool(tool_name, arguments)

            # Parse the result
            response: Dict[str, Any] = {
                "content": [],
                "thread_id": None,
                "is_error": result.isError if hasattr(result, "isError") else False,
            }

            # Check for threadId in structuredContent
            if hasattr(result, "structuredContent") and isinstance(result.structuredContent, dict):
                if "threadId" in result.structuredContent:
                    response["thread_id"] = result.structuredContent["threadId"]
                    logger.debug(
                        f"[Instance {self._instance_id}] Found threadId: "
                        f"{result.structuredContent['threadId']}"
                    )

            # Extract content from the result
            if hasattr(result, "content") and result.content:
                for item in result.content:
                    if hasattr(item, "type"):
                        if item.type == "text":
                            text_content = item.text if hasattr(item, "text") else str(item)
                            response["content"].append({
                                "type": "text",
                                "text": text_content,
                            })
                        elif item.type == "reasoning":
                            reasoning_text = ""
                            summary = getattr(item, "summary", None)
                            if summary:
                                for summary_item in summary:
                                    if hasattr(summary_item, "type") and summary_item.type == "summary_text":
                                        if hasattr(summary_item, "text"):
                                            reasoning_text += summary_item.text
                            if reasoning_text:
                                response["content"].append({
                                    "type": "reasoning",
                                    "text": reasoning_text,
                                })
                        elif item.type == "json":
                            try:
                                data = json.loads(item.text) if hasattr(item, "text") else {}
                                response["content"].append({
                                    "type": "json",
                                    "data": data,
                                })
                            except json.JSONDecodeError:
                                response["content"].append({
                                    "type": "text",
                                    "text": item.text if hasattr(item, "text") else str(item),
                                })

            # Add captured reasoning from notifications (if any)
            captured_reasoning = self._reasoning_capture.get_combined()
            if captured_reasoning:
                has_reasoning = any(
                    item.get("type") == "reasoning" for item in response.get("content", [])
                )
                if not has_reasoning:
                    response["content"].append({
                        "type": "reasoning",
                        "text": captured_reasoning,
                    })
                    logger.debug(
                        f"[Instance {self._instance_id}] Added captured reasoning: "
                        f"{len(captured_reasoning)} chars"
                    )

            # Register new thread if created
            if response.get("thread_id") and not thread_id:
                self.register_thread(response["thread_id"])

            logger.info(
                f"[Instance {self._instance_id}] Call complete. "
                f"Thread ID: {response.get('thread_id')}, "
                f"content items: {len(response.get('content', []))}"
            )
            return response

        except Exception as e:
            logger.error(f"[Instance {self._instance_id}] MCP tool call failed: {e}")
            # Mark as unhealthy on connection errors
            if "connection" in str(e).lower() or "closed" in str(e).lower():
                self._healthy = False
                logger.warning(f"[Instance {self._instance_id}] Marked unhealthy due to connection error")
            raise

    async def restart(self) -> None:
        """Restart the MCP server after a failure."""
        logger.info(f"[Instance {self._instance_id}] Restarting Codex MCP server...")
        await self._cleanup()
        self._started = False
        self._healthy = False
        await self.start()

    async def _cleanup(self) -> None:
        """Clean up server resources."""
        # Remove notification capture filter
        if self._capture_filter is not None:
            logging.getLogger().removeFilter(self._capture_filter)
            self._capture_filter = None

        if self._session_context is not None:
            try:
                await self._session_context.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"[Instance {self._instance_id}] Error closing session: {e}")
            self._session_context = None
            self._session = None

        if self._process_context is not None:
            try:
                await self._process_context.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"[Instance {self._instance_id}] Error closing process: {e}")
            self._process_context = None
            self._read_stream = None
            self._write_stream = None

    async def shutdown(self) -> None:
        """Gracefully shutdown the MCP server."""
        logger.info(f"[Instance {self._instance_id}] Shutting down...")
        await self._cleanup()
        self._started = False
        self._healthy = False
        self._available_tools = {}
        self._active_threads.clear()
        logger.info(f"[Instance {self._instance_id}] Shutdown complete")

    @property
    def available_tools(self) -> Dict[str, Any]:
        """Get the available MCP tools."""
        return self._available_tools
