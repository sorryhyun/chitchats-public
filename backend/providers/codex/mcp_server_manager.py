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
import shutil
import sys
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger("CodexMCPServerManager")

# Windows detection for subprocess handling
IS_WINDOWS = sys.platform == "win32"

# Codex Windows executable name
_CODEX_WINDOWS_EXE_NAME = "codex-x86_64-pc-windows-msvc.exe"

# Project root directory (backend's parent) - for development
# backend/providers/codex/mcp_server_manager.py -> 4 parents to reach project root
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
_BUNDLED_CODEX_DEV = _PROJECT_ROOT / "bundled" / _CODEX_WINDOWS_EXE_NAME

# Next to the main executable - for packaged Windows builds (e.g., chitchat.exe)
_BUNDLED_CODEX_PACKAGED = Path(sys.executable).parent / _CODEX_WINDOWS_EXE_NAME


def _get_bundled_codex_path() -> Optional[Path]:
    """Get the bundled Codex executable path on Windows.

    Checks two locations:
    1. Next to the main executable (for packaged builds: chitchat.exe + codex-...exe)
    2. In bundled/ folder (for development)

    Returns:
        Path to the bundled executable if found, None otherwise.
    """
    if not IS_WINDOWS:
        return None

    # First check next to the executable (packaged builds)
    if _BUNDLED_CODEX_PACKAGED.exists():
        return _BUNDLED_CODEX_PACKAGED

    # Fall back to bundled/ folder (development)
    if _BUNDLED_CODEX_DEV.exists():
        return _BUNDLED_CODEX_DEV

    return None


def _get_codex_executable() -> str:
    """Get the Codex executable path based on platform.

    Returns the bundled Windows executable on Windows (if found),
    or 'codex' (npm-installed) on other platforms.
    """
    bundled_path = _get_bundled_codex_path()
    if bundled_path:
        return str(bundled_path)
    return "codex"


def _get_clean_environment() -> Dict[str, str]:
    """Create a minimal, clean environment for the Codex subprocess.

    Passing the full os.environ can cause stdout pollution from development
    tools (Node.js diagnostics, Python warnings, etc.) that interfere with
    the MCP JSON-RPC protocol.

    Returns:
        A dict with only essential environment variables for Codex to run.
    """
    # Essential variables to keep
    essential_vars = {
        # System essentials
        "PATH",
        "SystemRoot",
        "SYSTEMROOT",
        "COMSPEC",
        "TEMP",
        "TMP",
        # User identity
        "HOME",
        "USERPROFILE",
        "USERNAME",
        "USER",
        # Codex/OpenAI authentication
        "OPENAI_API_KEY",
        "OPENAI_ORG_ID",
        "OPENAI_PROJECT_ID",
        # Windows-specific
        "HOMEDRIVE",
        "HOMEPATH",
        "APPDATA",
        "LOCALAPPDATA",
        "ProgramFiles",
        "ProgramFiles(x86)",
        "windir",
    }

    clean_env: Dict[str, str] = {}
    for key in essential_vars:
        if key in os.environ:
            clean_env[key] = os.environ[key]

    # Force non-interactive/plain output mode
    # These suppress fancy terminal UI elements that corrupt JSON-RPC
    clean_env["NO_COLOR"] = "1"
    clean_env["CI"] = "true"
    clean_env["TERM"] = "dumb"
    clean_env["FORCE_COLOR"] = "0"

    return clean_env


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
        # Captured reasoning from notifications during tool calls
        self._captured_reasoning: List[str] = []

    def _create_message_handler(self) -> Callable:
        """Create a message handler callback for capturing Codex notifications.

        This handler captures agent_reasoning events from Codex's custom
        MCP notifications, which are not part of the standard tool result.
        """

        def handle_message(message: Any) -> None:
            """Handle incoming MCP messages including custom notifications."""
            try:
                # Handle different message formats
                if hasattr(message, "params"):
                    params = message.params
                    # Check for Codex's custom event notification
                    if hasattr(params, "type") and params.type == "agent_reasoning":
                        text = getattr(params, "text", "")
                        if text:
                            self._captured_reasoning.append(text)
                            logger.debug(f"Captured agent_reasoning: {len(text)} chars")
                    # Also check for nested payload format
                    elif hasattr(params, "payload"):
                        payload = params.payload
                        if isinstance(payload, dict) and payload.get("type") == "agent_reasoning":
                            text = payload.get("text", "")
                            if text:
                                self._captured_reasoning.append(text)
                                logger.debug(f"Captured agent_reasoning from payload: {len(text)} chars")
                # Handle dict format
                elif isinstance(message, dict):
                    msg_type = message.get("type", "")
                    if msg_type == "event_msg":
                        payload = message.get("payload", {})
                        if payload.get("type") == "agent_reasoning":
                            text = payload.get("text", "")
                            if text:
                                self._captured_reasoning.append(text)
                                logger.debug(f"Captured agent_reasoning: {len(text)} chars")
                    elif msg_type == "response_item":
                        # Handle response_item with reasoning type
                        payload = message.get("payload", {})
                        if payload.get("type") == "reasoning":
                            # Extract from summary array
                            summary = payload.get("summary", [])
                            for summary_item in summary:
                                if isinstance(summary_item, dict) and summary_item.get("type") == "summary_text":
                                    text = summary_item.get("text", "")
                                    if text:
                                        self._captured_reasoning.append(text)
                                        logger.debug(f"Captured reasoning from summary: {len(text)} chars")
            except Exception as e:
                logger.debug(f"Error handling message: {e}")

        return handle_message

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
        # Use bundled executable on Windows if available, otherwise fall back to npm-installed
        bundled_path = _get_bundled_codex_path()
        if bundled_path:
            codex_path = str(bundled_path)
            logger.info(f"Using bundled Codex executable: {codex_path}")
        else:
            codex_path = shutil.which("codex")
            if not codex_path:
                raise RuntimeError("Codex CLI not found. Install it with: npm install -g @openai/codex")

        logger.info("Starting Codex MCP server...")
        logger.info(f"Codex path: {codex_path}")

        # Create a minimal, clean environment for the Codex subprocess
        # Passing the full environment can cause stdout pollution from
        # development tools (Node.js, Python, etc.) that emit diagnostics
        clean_env = _get_clean_environment()
        logger.debug(f"Clean environment keys: {list(clean_env.keys())}")

        # Create server parameters for stdio transport
        server_params = StdioServerParameters(
            command=codex_path,
            args=["mcp-server"],
            env=clean_env,
        )

        try:
            # Start the server process with stdio transport
            self._process_context = stdio_client(server_params)
            read_stream, write_stream = await self._process_context.__aenter__()
            self._read_stream = read_stream
            self._write_stream = write_stream

            # Create MCP session with message handler to capture Codex notifications
            # (type: ignore for MCP library's Any types)
            message_handler = self._create_message_handler()
            self._session_context = ClientSession(
                read_stream,
                write_stream,
                message_handler=message_handler,
            )  # type: ignore[arg-type]
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
        except Exception as e:
            logger.error(f"❌ Failed to start Codex MCP server: {e}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            raise

    async def call_codex(
        self,
        prompt: str,
        config: Optional[Dict[str, Any]] = None,
        thread_id: Optional[str] = None,
        approval_policy: str = "never",
        sandbox: str = "danger-full-access",
        cwd: Optional[str] = None,
        full_conversation: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Call the Codex MCP tool.

        Args:
            prompt: The prompt/message to send
            config: Configuration dict (mcp_servers, developer_instructions, feature settings, etc.)
            thread_id: Optional thread ID for continuing a conversation
            approval_policy: Approval policy - "never", "on-request", "on-failure", "untrusted"
            sandbox: Sandbox mode - "danger-full-access", "workspace-write", "read-only"
            cwd: Working directory for the session
            full_conversation: Full conversation history for session recovery

        Returns:
            Dict containing the tool response with content and threadId
        """
        await self.ensure_started()

        async with self._request_lock:
            return await self._call_tool_impl(prompt, config, thread_id, approval_policy, sandbox, cwd, full_conversation)

    async def _call_tool_impl(
        self,
        prompt: str,
        config: Optional[Dict[str, Any]],
        thread_id: Optional[str],
        approval_policy: str,
        sandbox: str,
        cwd: Optional[str] = None,
        full_conversation: Optional[str] = None,
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

        # Clear any previously captured reasoning before this call
        self._captured_reasoning.clear()

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

            # Add any reasoning captured from notifications during the tool call
            if self._captured_reasoning:
                combined_reasoning = "\n".join(self._captured_reasoning)
                response["content"].append(
                    {
                        "type": "reasoning",
                        "text": combined_reasoning,
                    }
                )
                logger.info(f"Added captured reasoning: {len(combined_reasoning)} chars from {len(self._captured_reasoning)} notification(s)")
                self._captured_reasoning.clear()

            # Handle "Session not found" error by falling back to new session
            if response.get("is_error") and thread_id:
                error_text = ""
                for item in response.get("content", []):
                    if item.get("type") == "text":
                        error_text += item.get("text", "")

                if "session not found" in error_text.lower():
                    logger.warning(
                        f"Session not found for thread_id {thread_id}, starting new session with full conversation..."
                    )
                    # Retry without thread_id to start a fresh session
                    # Use full_conversation if available to preserve context
                    recovery_prompt = full_conversation if full_conversation else prompt
                    return await self._call_tool_impl(
                        recovery_prompt, config, None, approval_policy, sandbox, cwd, None
                    )

            return response

        except Exception as e:
            logger.error(f"MCP tool call failed: {e}")
            # Try to restart the server on connection errors
            if "connection" in str(e).lower() or "closed" in str(e).lower():
                logger.info("Connection error detected, attempting restart...")
                await self._restart_server()
                # Retry once with full_conversation
                return await self._call_tool_impl(prompt, config, thread_id, approval_policy, sandbox, cwd, full_conversation)
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
