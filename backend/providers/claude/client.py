"""
Claude SDK client wrapper.

This module wraps the ClaudeSDKClient from claude_agent_sdk
to provide the AIClient interface for the provider abstraction.
"""

import logging
from typing import Any, AsyncIterator, Optional, Union

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from providers.base import AIClient

logger = logging.getLogger("ClaudeClient")


class ClaudeClient(AIClient):
    """Claude SDK client wrapper implementing AIClient interface.

    This wraps ClaudeSDKClient to provide a unified interface
    compatible with the multi-provider abstraction.

    Attributes:
        _client: The underlying ClaudeSDKClient instance
        _options: The ClaudeAgentOptions used to create the client
    """

    def __init__(self, options: ClaudeAgentOptions):
        """Initialize with Claude SDK options.

        Args:
            options: ClaudeAgentOptions for client configuration
        """
        self._options = options
        self._client: Optional[ClaudeSDKClient] = None

    async def connect(self) -> None:
        """Initialize the connection to Claude Code CLI."""
        if self._client is None:
            self._client = ClaudeSDKClient(options=self._options)
        await self._client.connect()
        logger.debug("Claude client connected")

    async def disconnect(self) -> None:
        """Close the connection cleanly."""
        if self._client is not None:
            try:
                await self._client.disconnect()
                logger.debug("Claude client disconnected")
            except Exception as e:
                logger.warning(f"Error disconnecting Claude client: {e}")
            finally:
                self._client = None

    async def query(self, message: Union[str, AsyncIterator[dict]]) -> None:
        """Send a message/query to Claude.

        Args:
            message: The message content - string or async iterator of content blocks

        Raises:
            RuntimeError: If client is not connected
        """
        if self._client is None:
            raise RuntimeError("Client not connected. Call connect() first.")
        await self._client.query(message)

    def receive_response(self) -> AsyncIterator[Any]:
        """Receive streaming response from Claude.

        This returns the underlying client's async iterator directly.

        Returns:
            Async iterator of SDK message objects

        Raises:
            RuntimeError: If client is not connected
        """
        if self._client is None:
            raise RuntimeError("Client not connected. Call connect() first.")
        return self._client.receive_response()

    async def interrupt(self) -> None:
        """Interrupt the current response generation."""
        if self._client is not None:
            try:
                await self._client.interrupt()
                logger.debug("Claude client interrupted")
            except Exception as e:
                logger.warning(f"Error interrupting Claude client: {e}")

    @property
    def session_id(self) -> Optional[str]:
        """Get the current session ID for resume support."""
        if self._options and hasattr(self._options, "resume"):
            return self._options.resume
        return None

    @property
    def options(self) -> ClaudeAgentOptions:
        """Get the Claude SDK options object."""
        return self._options

    @options.setter
    def options(self, value: ClaudeAgentOptions) -> None:
        """Update the Claude SDK options object.

        Note: This only affects future connections, not the current one.
        """
        self._options = value
        # If client exists, update its options too
        if self._client is not None:
            self._client.options = value

    @property
    def underlying_client(self) -> Optional[ClaudeSDKClient]:
        """Get the underlying ClaudeSDKClient instance.

        This is useful for advanced operations that need direct SDK access.
        """
        return self._client
