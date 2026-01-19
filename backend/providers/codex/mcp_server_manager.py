"""
Singleton manager for the Codex MCP server process.

This module provides the CodexMCPServerManager class that manages a single
`codex mcp-server` process and MCP client session for all Codex requests.

Architecture:
    - Single MCP server process shared across all agents
    - Async singleton pattern for thread-safe access
    - Request locking to serialize tool calls
    - Automatic restart on connection failure
"""

import asyncio
import logging
import os
import platform
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger("CodexMCPServerManager")


def _get_bundled_codex_path() -> Optional[str]:
    """Get the path to the bundled Codex Rust binary."""
    # Bundled paths by platform (relative to project root)
    bundled_paths = {
        "windows-amd64": "bundled/codex-x86_64-pc-windows-msvc.exe",
        "windows-x86_64": "bundled/codex-x86_64-pc-windows-msvc.exe",
        "darwin-arm64": "bundled/codex-aarch64-apple-darwin",
        "darwin-x86_64": "bundled/codex-x86_64-apple-darwin",
        "linux-x86_64": "bundled/codex-x86_64-unknown-linux-gnu",
        "linux-aarch64": "bundled/codex-aarch64-unknown-linux-gnu",
    }

    key = f"{platform.system().lower()}-{platform.machine().lower()}"
    relative_path = bundled_paths.get(key)
    if relative_path:
        # This file: backend/providers/codex/mcp_server_manager.py
        # Project root: 4 levels up
        project_root = Path(__file__).parent.parent.parent.parent
        bundled_path = project_root / relative_path
        if bundled_path.exists():
            logger.info(f"Found bundled Codex binary: {bundled_path}")
            return str(bundled_path)
    return None


class _MCPNotificationFilter(logging.Filter):
    """Filter to suppress verbose MCP validation warnings for Codex custom notifications."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Suppress "Failed to validate notification" warnings from Codex's codex/event
        if "Failed to validate notification" in record.getMessage():
            return False
        return True


# Apply filter to root logger to suppress Codex's custom MCP notification warnings
logging.getLogger().addFilter(_MCPNotificationFilter())


class CodexMCPServerManager:
    """Singleton manager for the Codex MCP server process.

    This class manages a single `codex mcp-server` process and provides
    methods to call the `codex` and `codex-reply` MCP tools.

    Usage:
        manager = await CodexMCPServerManager.get_instance()
        await manager.ensure_started()
        result = await manager.call_codex("Hello!", config={...})
        # Later at shutdown:
        await manager.shutdown()
    """

    _instance: Optional["CodexMCPServerManager"] = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __init__(self):
        """Initialize the manager (use get_instance() instead)."""
        self._session: Optional[ClientSession] = None
        self._read_stream: Optional[Any] = None
        self._write_stream: Optional[Any] = None
        self._process_context: Optional[Any] = None
        self._session_context: Optional[Any] = None
        self._started = False
        self._request_lock = asyncio.Lock()
        self._available_tools: Dict[str, Any] = {}

    @classmethod
    async def get_instance(cls) -> "CodexMCPServerManager":
        """Get the singleton instance of CodexMCPServerManager.

        Returns:
            The singleton manager instance
        """
        async with cls._lock:
            if cls._instance is None:
                cls._instance = CodexMCPServerManager()
            return cls._instance

    @classmethod
    async def reset_instance(cls) -> None:
        """Reset the singleton instance (for testing)."""
        async with cls._lock:
            if cls._instance is not None:
                await cls._instance.shutdown()
                cls._instance = None

    async def ensure_started(self) -> None:
        """Ensure the MCP server is started and connected.

        This method is idempotent - calling it multiple times
        will only start the server once.
        """
        if self._started and self._session is not None:
            return

        async with self._request_lock:
            # Double-check after acquiring lock
            if self._started and self._session is not None:
                return

            await self._start_server()

    async def _start_server(self) -> None:
        """Start the Codex MCP server process and establish connection."""
        # Prefer bundled Rust binary over npm-installed Node.js version
        # The Rust binary properly supports MCP server mode
        codex_path = _get_bundled_codex_path()
        if not codex_path:
            codex_path = shutil.which("codex")
        if not codex_path:
            raise RuntimeError("Codex CLI not found. Install it with: npm install -g @openai/codex")

        logger.info(f"Starting Codex MCP server using: {codex_path}")

        # Create server parameters for stdio transport
        server_params = StdioServerParameters(
            command=codex_path,
            args=["mcp-server"],
            env={**os.environ},  # Pass through environment
        )

        # Start the server process with stdio transport
        self._process_context = stdio_client(server_params)
        read_stream, write_stream = await self._process_context.__aenter__()
        self._read_stream = read_stream
        self._write_stream = write_stream

        # Create MCP session (type: ignore for MCP library's Any types)
        self._session_context = ClientSession(read_stream, write_stream)  # type: ignore[arg-type]
        session = await self._session_context.__aenter__()
        self._session = session
        assert session is not None, "MCP session failed to initialize"

        # Initialize the session
        await session.initialize()

        # Discover available tools
        tools_result = await session.list_tools()
        self._available_tools = {tool.name: tool for tool in tools_result.tools}

        logger.info(f"Codex MCP server started. Available tools: {list(self._available_tools.keys())}")
        self._started = True

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
            config: Configuration dict (mcp_servers, developer_instructions, feature settings, etc.)
            thread_id: Optional thread ID for continuing a conversation
            approval_policy: Approval policy - "never", "on-request", "on-failure", "untrusted"
            sandbox: Sandbox mode - "danger-full-access", "workspace-write", "read-only"
            cwd: Working directory for the session

        Returns:
            Dict containing the tool response with content and threadId
        """
        await self.ensure_started()

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
            raise RuntimeError("MCP session not initialized")

        # Determine which tool to use
        tool_name = "codex-reply" if thread_id else "codex"

        # Build arguments with minimal permissions prompt
        # Note: Codex MCP uses kebab-case for parameter names
        arguments: Dict[str, Any] = {
            "prompt": prompt,
            "approval-policy": approval_policy,
            "sandbox": sandbox,
        }

        # cwd is a top-level parameter
        if cwd:
            arguments["cwd"] = cwd

        # config contains developer_instructions, mcp_servers, features, etc.
        if config:
            arguments["config"] = config

        if thread_id:
            arguments["threadId"] = thread_id

        logger.info(f"Calling MCP tool '{tool_name}' with thread_id={thread_id}, prompt: {prompt[:100]}...")

        try:
            result = await self._session.call_tool(tool_name, arguments)

            # Parse the result
            response: Dict[str, Any] = {
                "content": [],
                "thread_id": None,
                "is_error": result.isError if hasattr(result, "isError") else False,
            }

            # Log raw result structure for debugging
            logger.debug(f"Raw MCP result repr: {repr(result)}")

            # Check for threadId in structuredContent (where Codex MCP returns it)
            if hasattr(result, "structuredContent") and isinstance(result.structuredContent, dict):
                if "threadId" in result.structuredContent:
                    response["thread_id"] = result.structuredContent["threadId"]
                    logger.info(f"Found threadId in structuredContent: {result.structuredContent['threadId']}")

            # Extract content from the result
            if hasattr(result, "content") and result.content:
                for item in result.content:
                    if hasattr(item, "type"):
                        if item.type == "text":
                            text_content = item.text if hasattr(item, "text") else str(item)
                            response["content"].append(
                                {
                                    "type": "text",
                                    "text": text_content,
                                }
                            )
                        elif item.type == "reasoning":
                            # Extract reasoning from summary array
                            # Format: {type: "reasoning", summary: [{type: "summary_text", text: "..."}]}
                            reasoning_text = ""
                            summary = getattr(item, "summary", None)
                            if summary:
                                for summary_item in summary:  # type: ignore[union-attr]
                                    if hasattr(summary_item, "type") and summary_item.type == "summary_text":
                                        if hasattr(summary_item, "text"):
                                            reasoning_text += summary_item.text
                            if reasoning_text:
                                response["content"].append(
                                    {
                                        "type": "reasoning",
                                        "text": reasoning_text,
                                    }
                                )
                        elif item.type == "json":
                            # Parse JSON content to extract structured data
                            import json

                            try:
                                data = json.loads(item.text) if hasattr(item, "text") else {}
                                response["content"].append(
                                    {
                                        "type": "json",
                                        "data": data,
                                    }
                                )
                            except json.JSONDecodeError:
                                response["content"].append(
                                    {
                                        "type": "text",
                                        "text": item.text if hasattr(item, "text") else str(item),
                                    }
                                )

            logger.info(
                f"MCP tool call complete. Thread ID: {response.get('thread_id')}, content items: {len(response.get('content', []))}"
            )
            return response

        except Exception as e:
            logger.error(f"MCP tool call failed: {e}")
            # Try to restart the server on connection errors
            if "connection" in str(e).lower() or "closed" in str(e).lower():
                logger.info("Connection error detected, attempting restart...")
                await self._restart_server()
                # Retry once
                return await self._call_tool_impl(prompt, config, thread_id, approval_policy, sandbox, cwd)
            raise

    async def _restart_server(self) -> None:
        """Restart the MCP server after a failure."""
        logger.info("Restarting Codex MCP server...")
        await self._cleanup()
        self._started = False
        await self._start_server()

    async def _cleanup(self) -> None:
        """Clean up server resources."""
        if self._session_context is not None:
            try:
                await self._session_context.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error closing MCP session: {e}")
            self._session_context = None
            self._session = None

        if self._process_context is not None:
            try:
                await self._process_context.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error closing MCP process: {e}")
            self._process_context = None
            self._read_stream = None
            self._write_stream = None

    async def shutdown(self) -> None:
        """Gracefully shutdown the MCP server."""
        logger.info("Shutting down Codex MCP server...")
        await self._cleanup()
        self._started = False
        self._available_tools = {}
        logger.info("Codex MCP server shutdown complete")

    @property
    def is_started(self) -> bool:
        """Check if the MCP server is started."""
        return self._started

    @property
    def available_tools(self) -> Dict[str, Any]:
        """Get the available MCP tools."""
        return self._available_tools


@asynccontextmanager
async def get_mcp_server_manager():
    """Context manager for getting the MCP server manager.

    Ensures the server is started before yielding.

    Usage:
        async with get_mcp_server_manager() as manager:
            result = await manager.call_codex("Hello!")
    """
    manager = await CodexMCPServerManager.get_instance()
    await manager.ensure_started()
    yield manager
