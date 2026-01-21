"""
Pool manager for multiple Codex MCP server instances.

This module provides the CodexServerPool class that manages multiple
`codex mcp-server` processes for parallel request handling.

Architecture:
    - Multiple MCP server instances (configurable via CODEX_POOL_SIZE)
    - Thread ID affinity routing (follow-up messages route to same instance)
    - Per-instance locks (enables parallel requests across instances)
    - Selection strategies: round_robin (default) or least_busy
    - Health monitoring with auto-recovery

Environment Variables:
    - CODEX_POOL_SIZE: Number of server instances (default: 3)
    - CODEX_SELECTION_STRATEGY: "round_robin" (default) or "least_busy"
"""

import asyncio
import logging
import os
from enum import Enum
from typing import Any, Dict, List, Optional

from .mcp_server_instance import CodexMCPServerInstance

logger = logging.getLogger("CodexServerPool")


class SelectionStrategy(Enum):
    """Strategy for selecting which instance to use for a request."""

    ROUND_ROBIN = "round_robin"
    LEAST_BUSY = "least_busy"


class CodexServerPool:
    """Pool manager for multiple Codex MCP server instances.

    This class manages multiple `codex mcp-server` processes to enable
    parallel request handling for multi-agent conversations.

    Features:
        - Multiple instances with configurable pool size
        - Thread ID affinity routing (follow-up messages go to same instance)
        - Selection strategies: round_robin or least_busy
        - Health monitoring with automatic recovery
        - Statistics for monitoring

    Usage:
        pool = await CodexServerPool.get_instance()
        await pool.ensure_started()
        result = await pool.call_codex("Hello!", thread_id="thread_1")
        # When done with a thread:
        await pool.release_thread("thread_1")
        # At shutdown:
        await pool.shutdown()
    """

    _instance: Optional["CodexServerPool"] = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __init__(self):
        """Initialize the pool manager (use get_instance() instead)."""
        # Configuration from environment
        self._pool_size = int(os.environ.get("CODEX_POOL_SIZE", "3"))
        strategy_str = os.environ.get("CODEX_SELECTION_STRATEGY", "round_robin")
        self._strategy = SelectionStrategy(strategy_str)

        # Instance management
        self._instances: List[CodexMCPServerInstance] = []
        self._round_robin_index = 0

        # Thread affinity mapping: thread_id -> instance_id
        self._thread_affinity: Dict[str, int] = {}
        self._affinity_lock = asyncio.Lock()

        # Pool state
        self._started = False
        self._shutdown_in_progress = False

        logger.info(
            f"CodexServerPool initialized with pool_size={self._pool_size}, "
            f"strategy={self._strategy.value}"
        )

    @classmethod
    async def get_instance(cls) -> "CodexServerPool":
        """Get the singleton instance of CodexServerPool.

        Returns:
            The singleton pool instance
        """
        async with cls._lock:
            if cls._instance is None:
                cls._instance = CodexServerPool()
            return cls._instance

    @classmethod
    async def reset_instance(cls) -> None:
        """Reset the singleton instance (for testing)."""
        async with cls._lock:
            if cls._instance is not None:
                await cls._instance.shutdown()
                cls._instance = None

    async def ensure_started(self) -> None:
        """Ensure all pool instances are started.

        This method is idempotent - calling it multiple times
        will only start instances once.
        """
        if self._started and len(self._instances) == self._pool_size:
            # Check health and restart unhealthy instances
            await self._recover_unhealthy_instances()
            return

        async with self._lock:
            # Double-check after acquiring lock
            if self._started and len(self._instances) == self._pool_size:
                await self._recover_unhealthy_instances()
                return

            await self._start_pool()

    async def _start_pool(self) -> None:
        """Start all pool instances."""
        logger.info(f"Starting Codex server pool with {self._pool_size} instances...")

        # Create instances if not already created
        while len(self._instances) < self._pool_size:
            instance_id = len(self._instances)
            instance = CodexMCPServerInstance(instance_id)
            self._instances.append(instance)

        # Start all instances in parallel
        start_tasks = [instance.start() for instance in self._instances]
        results = await asyncio.gather(*start_tasks, return_exceptions=True)

        # Log any failures
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Failed to start instance {i}: {result}")
                self._instances[i]._healthy = False
            else:
                logger.info(f"Instance {i} started successfully")

        self._started = True
        logger.info(
            f"Codex server pool started. "
            f"Healthy instances: {sum(1 for inst in self._instances if inst.is_healthy)}/{self._pool_size}"
        )

    async def _recover_unhealthy_instances(self) -> None:
        """Attempt to recover any unhealthy instances."""
        for instance in self._instances:
            if not instance.is_healthy:
                logger.info(f"Recovering unhealthy instance {instance.instance_id}...")
                try:
                    await instance.restart()
                    logger.info(f"Instance {instance.instance_id} recovered successfully")
                except Exception as e:
                    logger.error(f"Failed to recover instance {instance.instance_id}: {e}")

    async def _select_instance(self, thread_id: Optional[str]) -> CodexMCPServerInstance:
        """Select an instance for a request.

        Args:
            thread_id: Optional thread ID for affinity routing

        Returns:
            The selected instance
        """
        async with self._affinity_lock:
            # Check for existing thread affinity
            if thread_id and thread_id in self._thread_affinity:
                instance_id = self._thread_affinity[thread_id]
                instance = self._instances[instance_id]
                if instance.is_healthy:
                    logger.debug(f"Using affinity routing: thread {thread_id} -> instance {instance_id}")
                    return instance
                else:
                    # Instance is unhealthy, remove affinity and select new instance
                    logger.warning(
                        f"Instance {instance_id} is unhealthy for thread {thread_id}, "
                        "selecting new instance"
                    )
                    del self._thread_affinity[thread_id]

            # Select new instance based on strategy
            instance = await self._select_by_strategy()

            # Record affinity for thread
            if thread_id:
                self._thread_affinity[thread_id] = instance.instance_id
                instance.register_thread(thread_id)
                logger.debug(f"New affinity: thread {thread_id} -> instance {instance.instance_id}")

            return instance

    async def _select_by_strategy(self) -> CodexMCPServerInstance:
        """Select an instance based on the configured strategy.

        Returns:
            The selected instance
        """
        # Filter to healthy instances
        healthy_instances = [inst for inst in self._instances if inst.is_healthy]

        if not healthy_instances:
            logger.warning("No healthy instances available, using first instance")
            return self._instances[0]

        if self._strategy == SelectionStrategy.ROUND_ROBIN:
            # Round-robin among healthy instances
            self._round_robin_index = (self._round_robin_index + 1) % len(healthy_instances)
            instance = healthy_instances[self._round_robin_index]
            logger.debug(f"Round-robin selected instance {instance.instance_id}")
            return instance

        elif self._strategy == SelectionStrategy.LEAST_BUSY:
            # Select instance with fewest active threads
            instance = min(healthy_instances, key=lambda inst: inst.active_thread_count)
            logger.debug(
                f"Least-busy selected instance {instance.instance_id} "
                f"with {instance.active_thread_count} active threads"
            )
            return instance

        # Fallback to first healthy instance
        return healthy_instances[0]

    async def call_codex(
        self,
        prompt: str,
        config: Optional[Dict[str, Any]] = None,
        thread_id: Optional[str] = None,
        approval_policy: str = "never",
        sandbox: str = "danger-full-access",
        cwd: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Call the Codex MCP tool using an appropriate instance.

        This method handles instance selection based on thread affinity
        and the configured selection strategy.

        Args:
            prompt: The prompt/message to send
            config: Configuration dict (mcp_servers, developer_instructions, etc.)
            thread_id: Optional thread ID for continuing a conversation
            approval_policy: Approval policy
            sandbox: Sandbox mode
            cwd: Working directory for the session

        Returns:
            Dict containing the tool response with content and threadId
        """
        await self.ensure_started()

        # Select instance
        instance = await self._select_instance(thread_id)

        logger.info(
            f"Routing request to instance {instance.instance_id} "
            f"(thread_id={thread_id}, strategy={self._strategy.value})"
        )

        # Make the call
        result = await instance.call_codex(
            prompt=prompt,
            config=config,
            thread_id=thread_id,
            approval_policy=approval_policy,
            sandbox=sandbox,
            cwd=cwd,
        )

        # If a new thread_id was returned, update affinity
        # Note: The instance already registered the thread in call_codex if it was new
        new_thread_id = result.get("thread_id")
        if new_thread_id and new_thread_id != thread_id:
            async with self._affinity_lock:
                self._thread_affinity[new_thread_id] = instance.instance_id
                logger.debug(f"New thread affinity: {new_thread_id} -> instance {instance.instance_id}")

        return result

    async def release_thread(self, thread_id: str) -> None:
        """Release a thread from its instance affinity.

        Call this when a conversation/session is complete to free up
        the instance for other threads.

        Args:
            thread_id: The thread ID to release
        """
        async with self._affinity_lock:
            if thread_id in self._thread_affinity:
                instance_id = self._thread_affinity[thread_id]
                del self._thread_affinity[thread_id]
                if instance_id < len(self._instances):
                    self._instances[instance_id].release_thread(thread_id)
                logger.debug(f"Released thread {thread_id} from instance {instance_id}")

    async def shutdown(self) -> None:
        """Gracefully shutdown all pool instances."""
        if self._shutdown_in_progress:
            return

        self._shutdown_in_progress = True
        logger.info(f"Shutting down Codex server pool ({len(self._instances)} instances)...")

        # Shutdown all instances in parallel
        shutdown_tasks = [instance.shutdown() for instance in self._instances]
        await asyncio.gather(*shutdown_tasks, return_exceptions=True)

        self._instances.clear()
        self._thread_affinity.clear()
        self._started = False
        self._shutdown_in_progress = False
        logger.info("Codex server pool shutdown complete")

    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics for monitoring.

        Returns:
            Dict containing pool stats
        """
        return {
            "pool_size": self._pool_size,
            "strategy": self._strategy.value,
            "started": self._started,
            "instances": [
                {
                    "id": inst.instance_id,
                    "started": inst.is_started,
                    "healthy": inst.is_healthy,
                    "active_threads": inst.active_thread_count,
                }
                for inst in self._instances
            ],
            "thread_affinity_count": len(self._thread_affinity),
            "healthy_instance_count": sum(1 for inst in self._instances if inst.is_healthy),
        }

    @property
    def pool_size(self) -> int:
        """Get the configured pool size."""
        return self._pool_size

    @property
    def is_started(self) -> bool:
        """Check if the pool is started."""
        return self._started

    @property
    def healthy_instance_count(self) -> int:
        """Get the number of healthy instances."""
        return sum(1 for inst in self._instances if inst.is_healthy)
