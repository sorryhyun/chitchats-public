"""
Codex CLI client implementation.

This module provides a client that communicates with Codex via CLI subprocess,
implementing the AIClient interface for the provider abstraction.

CLI Commands:
    - New conversation: codex exec --json --full-auto --skip-git-repo-check "prompt"
    - Resume thread: codex exec resume <thread-id> --json --full-auto "follow-up"
"""

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Union

from providers.base import AIClient

logger = logging.getLogger("CodexClient")


@dataclass
class CodexOptions:
    """Options for Codex CLI client.

    Attributes:
        system_prompt: System prompt (converted to instructions file or prepended)
        model: Model to use (optional, uses Codex default if not specified)
        thread_id: Thread ID for resume (codex exec resume <thread-id>)
        full_auto: Run in full-auto mode (default: True)
        skip_git_repo_check: Skip git repo check (default: True)
        working_dir: Working directory for the subprocess
        mcp_config_overrides: List of -c overrides for MCP servers (e.g., 'mcp_servers.name.command="python"')
        timeout: Timeout for subprocess operations (seconds)
        extra_args: Additional CLI arguments
    """

    system_prompt: str = ""
    model: Optional[str] = None
    thread_id: Optional[str] = None
    full_auto: bool = True
    skip_git_repo_check: bool = True
    working_dir: Optional[str] = None
    mcp_config_overrides: List[str] = field(default_factory=list)
    timeout: float = 300.0  # 5 minutes default
    extra_args: List[str] = field(default_factory=list)


class CodexClient(AIClient):
    """Codex CLI client implementing AIClient interface.

    This client spawns a subprocess to run Codex CLI commands
    and streams JSON output for real-time response handling.

    Usage:
        client = CodexClient(options)
        await client.connect()
        await client.query("Hello!")
        async for message in client.receive_response():
            # Handle streaming events
        await client.disconnect()
    """

    def __init__(self, options: CodexOptions):
        """Initialize with Codex options.

        Args:
            options: CodexOptions for client configuration
        """
        self._options = options
        self._process: Optional[asyncio.subprocess.Process] = None
        self._thread_id: Optional[str] = None
        self._pending_message: Optional[str] = None
        self._connected = False

    async def connect(self) -> None:
        """Initialize the client.

        For Codex, this is a no-op since we spawn a new subprocess per query.
        The "connection" state is just tracking readiness.
        """
        # Verify codex CLI is available
        codex_path = shutil.which("codex")
        if not codex_path:
            raise RuntimeError(
                "Codex CLI not found. Install it with: npm install -g @openai/codex"
            )

        self._connected = True
        logger.debug("Codex client ready")

    async def disconnect(self) -> None:
        """Close any running subprocess."""
        await self._cleanup_process()
        self._connected = False
        logger.debug("Codex client disconnected")

    async def _cleanup_process(self) -> None:
        """Clean up the subprocess if running."""
        if self._process is not None:
            try:
                if self._process.returncode is None:
                    self._process.terminate()
                    try:
                        await asyncio.wait_for(self._process.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        self._process.kill()
                        await self._process.wait()
            except Exception as e:
                logger.warning(f"Error cleaning up Codex process: {e}")
            finally:
                self._process = None

    async def query(self, message: Union[str, AsyncIterator[dict]]) -> None:
        """Send a message to Codex.

        This stores the message to be sent when receive_response() is called,
        since Codex CLI expects message as part of the command.

        Args:
            message: The message content (string only for Codex)

        Raises:
            RuntimeError: If client is not connected
            ValueError: If message is not a string (Codex doesn't support multimodal via CLI)
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
            raise ValueError("Codex client only supports string messages")

    def receive_response(self) -> AsyncIterator[Dict[str, Any]]:
        """Receive streaming response from Codex.

        Returns:
            Async iterator of JSON event dicts

        Raises:
            RuntimeError: If no pending message
        """
        return self._receive_response_impl()

    async def _receive_response_impl(self) -> AsyncIterator[Dict[str, Any]]:
        """Implementation of receive_response as async generator."""
        if self._pending_message is None:
            raise RuntimeError("No pending message. Call query() first.")

        # Build CLI command
        cmd = self._build_command(self._pending_message)
        self._pending_message = None

        logger.info(f"Running Codex: {' '.join(cmd)}")

        # Start subprocess
        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._options.working_dir,
            )
        except Exception as e:
            logger.error(f"Failed to start Codex process: {e}")
            yield {"type": "error", "data": {"message": str(e)}}
            return

        # Stream stdout line by line
        if self._process.stdout:
            try:
                while True:
                    line = await asyncio.wait_for(
                        self._process.stdout.readline(),
                        timeout=self._options.timeout,
                    )
                    if not line:
                        break

                    line_str = line.decode("utf-8").strip()
                    if not line_str:
                        continue

                    # Parse JSON
                    try:
                        event = json.loads(line_str)

                        # Extract thread_id from thread.started event
                        if event.get("type") == "thread.started":
                            data = event.get("data", {})
                            self._thread_id = data.get("thread_id") or data.get("id")

                        yield event

                    except json.JSONDecodeError:
                        # Non-JSON output (might be errors or status messages)
                        logger.debug(f"Non-JSON output: {line_str[:100]}")

            except asyncio.TimeoutError:
                logger.warning("Codex response timed out")
                yield {"type": "error", "data": {"message": "Response timeout"}}

        # Wait for process to complete
        await self._process.wait()

        # Check for errors
        if self._process.returncode != 0 and self._process.stderr:
            stderr = await self._process.stderr.read()
            error_msg = stderr.decode("utf-8").strip()
            if error_msg:
                logger.error(f"Codex stderr: {error_msg}")
                yield {"type": "error", "data": {"message": error_msg}}

        self._process = None

    def _build_command(self, message: str) -> List[str]:
        """Build the Codex CLI command.

        Args:
            message: The user message to send

        Returns:
            List of command parts for subprocess
        """
        cmd = ["codex", "exec"]

        # Handle thread resume
        if self._options.thread_id or self._thread_id:
            thread_id = self._options.thread_id or self._thread_id
            cmd.extend(["resume", thread_id])

        # Add flags
        cmd.append("--json")

        if self._options.full_auto:
            cmd.append("--full-auto")

        if self._options.skip_git_repo_check:
            cmd.append("--skip-git-repo-check")

        if self._options.model:
            cmd.extend(["--model", self._options.model])

        # Add MCP server overrides via -c flag (doesn't touch ~/.codex/config.toml)
        if self._options.mcp_config_overrides:
            for override in self._options.mcp_config_overrides:
                cmd.extend(["-c", override])

        # Add extra args
        if self._options.extra_args:
            cmd.extend([arg for arg in self._options.extra_args if arg])

        # Build prompt with system prompt if provided
        prompt = message
        if self._options.system_prompt and not self._thread_id:
            # Only prepend system prompt for new conversations
            prompt = f"{self._options.system_prompt}\n\n---\n\n{message}"

        cmd.append(prompt)

        return cmd

    async def interrupt(self) -> None:
        """Interrupt the current response by terminating the subprocess."""
        if self._process is not None and self._process.returncode is None:
            logger.info("Interrupting Codex process")
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            self._process = None

    @property
    def session_id(self) -> Optional[str]:
        """Get the current thread ID for resume support."""
        return self._thread_id or self._options.thread_id

    @property
    def options(self) -> CodexOptions:
        """Get the Codex options object."""
        return self._options

    @options.setter
    def options(self, value: CodexOptions) -> None:
        """Update the Codex options object."""
        self._options = value
        # Update thread_id if provided in new options
        if value.thread_id:
            self._thread_id = value.thread_id
