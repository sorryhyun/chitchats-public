"""
Centralized thread lifecycle management for Codex App Server.

This module provides the ThreadSessionManager class that tracks thread
ownership and agent mappings across app-server instances.

Note: Methods are synchronous because Python dict operations are atomic
at the bytecode level, and there are no await points between operations.
"""

import logging
from typing import Optional

logger = logging.getLogger("ThreadSessionManager")


class ThreadSessionManager:
    """Centralized thread lifecycle management for Codex App Server.

    Responsibilities:
    - Track thread -> agent mappings (for resume support)
    - Track thread -> instance ownership
    - Coordinate thread operations across instances

    This class is used by CodexAppServerPool to manage thread state
    that persists across instance restarts.

    Note: Methods are synchronous since dict operations complete without
    yielding to the event loop, making them safe in async contexts.
    """

    def __init__(self):
        """Initialize the thread session manager."""
        # Thread ID -> agent key mapping
        self._thread_to_agent: dict[str, str] = {}
        # Thread ID -> instance ID mapping
        self._thread_to_instance: dict[str, int] = {}

    def register_thread(
        self,
        thread_id: str,
        agent_key: str,
        instance_id: Optional[int] = None,
    ) -> None:
        """Register a new thread.

        Args:
            thread_id: The thread ID
            agent_key: The agent key that owns this thread
            instance_id: Optional instance ID that created the thread
        """
        self._thread_to_agent[thread_id] = agent_key
        if instance_id is not None:
            self._thread_to_instance[thread_id] = instance_id
        logger.debug(f"Registered thread {thread_id} -> agent={agent_key}, instance={instance_id}")

    def get_thread_owner(self, thread_id: str) -> tuple[Optional[str], Optional[int]]:
        """Get the agent key and instance ID for a thread.

        Args:
            thread_id: The thread ID to look up

        Returns:
            Tuple of (agent_key, instance_id), either may be None
        """
        agent_key = self._thread_to_agent.get(thread_id)
        instance_id = self._thread_to_instance.get(thread_id)
        return agent_key, instance_id

    def get_agent_for_thread(self, thread_id: str) -> Optional[str]:
        """Get the agent key for a thread.

        Args:
            thread_id: The thread ID to look up

        Returns:
            The agent key, or None if not found
        """
        return self._thread_to_agent.get(thread_id)

    def release_thread(self, thread_id: str) -> bool:
        """Release a thread from tracking.

        Args:
            thread_id: The thread ID to release

        Returns:
            True if the thread was found and released
        """
        agent_key = self._thread_to_agent.pop(thread_id, None)
        self._thread_to_instance.pop(thread_id, None)
        if agent_key:
            logger.debug(f"Released thread {thread_id} from agent {agent_key}")
            return True
        return False

    def clear_instance_threads(self, instance_id: int) -> list[str]:
        """Clear all threads for a shutdown instance.

        This is called synchronously during cleanup to avoid deadlocks.
        It only clears the instance mapping, not the agent mapping,
        so threads can still be resumed on a new instance.

        Args:
            instance_id: The instance ID being shut down

        Returns:
            List of thread IDs that were associated with this instance
        """
        cleared: list[str] = []
        for thread_id, inst_id in list(self._thread_to_instance.items()):
            if inst_id == instance_id:
                del self._thread_to_instance[thread_id]
                cleared.append(thread_id)
        if cleared:
            logger.debug(f"Cleared {len(cleared)} threads from instance {instance_id}")
        return cleared

    def clear_all(self) -> None:
        """Clear all thread mappings (for shutdown)."""
        self._thread_to_agent.clear()
        self._thread_to_instance.clear()
        logger.debug("Cleared all thread mappings")

    @property
    def thread_count(self) -> int:
        """Get the total number of tracked threads."""
        return len(self._thread_to_agent)

    def get_stats(self) -> dict:
        """Get statistics about thread tracking.

        Returns:
            Dict with thread counts and mappings
        """
        return {
            "total_threads": len(self._thread_to_agent),
            "threads_with_instance": len(self._thread_to_instance),
            "agents": list(set(self._thread_to_agent.values())),
        }
