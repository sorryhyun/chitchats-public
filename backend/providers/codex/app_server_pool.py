"""
Codex App Server pool manager.

This module provides the CodexAppServerPool class that manages multiple
`codex app-server` processes for parallel request processing with
thread ID affinity routing.

Architecture:
    - Pool of N server instances (configurable via CODEX_POOL_SIZE)
    - Thread ID affinity: follow-up messages route to the same instance
    - Different agents (different thread_ids) can run in parallel on different instances
    - Selection strategies: round_robin (default), least_busy
    - Automatic recovery from instance failures
"""

import asyncio
import logging
import os
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional

from .app_server_instance import AppServerConfig, CodexAppServerInstance

logger = logging.getLogger("CodexAppServerPool")


class SelectionStrategy(Enum):
    """Strategy for selecting a server instance for new conversations."""

    ROUND_ROBIN = "round_robin"
    LEAST_BUSY = "least_busy"


class CodexAppServerPool:
    """Pool manager for multiple Codex App Server instances.

    Manages a pool of server instances with thread ID affinity routing.
    Each agent gets its own thread_id, and follow-up messages are routed
    to the same instance that started the conversation.

    This enables parallelism: different agents (with different thread_ids)
    can be processed simultaneously on different server instances.

    Usage:
        pool = await CodexAppServerPool.get_instance()
        await pool.ensure_started()
        # New conversation - gets assigned to an instance
        thread_id = await pool.create_thread(config)
        # Stream turn events
        async for event in pool.start_turn(thread_id, "Hello!", config):
            # Handle events
        # When agent session ends
        pool.release_thread(thread_id)
        # At shutdown
        await pool.shutdown()
    """

    _instance: Optional["CodexAppServerPool"] = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __init__(self):
        """Initialize the pool (use get_instance() instead)."""
        # Configuration from environment
        self._pool_size = int(os.environ.get("CODEX_POOL_SIZE", "3"))
        strategy_name = os.environ.get("CODEX_SELECTION_STRATEGY", "round_robin")
        self._selection_strategy = SelectionStrategy(strategy_name)

        # Server instances
        self._instances: List[CodexAppServerInstance] = []

        # Thread affinity mapping: thread_id -> instance_index
        self._thread_affinity: Dict[str, int] = {}
        self._affinity_lock = asyncio.Lock()

        # Round-robin counter
        self._round_robin_counter = 0
        self._counter_lock = asyncio.Lock()

        self._started = False

    @classmethod
    async def get_instance(cls) -> "CodexAppServerPool":
        """Get the singleton instance of CodexAppServerPool.

        Returns:
            The singleton pool instance
        """
        async with cls._lock:
            if cls._instance is None:
                cls._instance = CodexAppServerPool()
            return cls._instance

    @classmethod
    async def reset_instance(cls) -> None:
        """Reset the singleton instance (for testing)."""
        async with cls._lock:
            if cls._instance is not None:
                await cls._instance.shutdown()
                cls._instance = None

    async def ensure_started(self) -> None:
        """Ensure the pool is started with all instances.

        This method is idempotent - calling it multiple times
        will only start the pool once.
        """
        if self._started:
            return

        async with self._lock:
            if self._started:
                return

            await self._start_pool()

    async def _start_pool(self) -> None:
        """Start all server instances in the pool."""
        logger.info(f"Starting Codex App Server pool ({self._pool_size} instances)...")

        # Create instances
        self._instances = [
            CodexAppServerInstance(instance_id=i)
            for i in range(self._pool_size)
        ]

        # Start all instances concurrently
        start_tasks = [instance.start() for instance in self._instances]
        results = await asyncio.gather(*start_tasks, return_exceptions=True)

        # Check for partial failures
        healthy_count = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Failed to start instance {i}: {result}")
            else:
                healthy_count += 1

        if healthy_count == 0:
            raise RuntimeError("All Codex App Server instances failed to start")

        if healthy_count < self._pool_size:
            logger.warning(
                f"Codex App Server pool started with reduced capacity: "
                f"{healthy_count}/{self._pool_size} instances"
            )
        else:
            logger.info(f"Codex App Server pool started ({self._pool_size} instances)")

        self._started = True

    async def _select_instance_for_new_conversation(self) -> CodexAppServerInstance:
        """Select an instance for a new conversation.

        Returns:
            Selected healthy instance

        Raises:
            RuntimeError: If no healthy instances available
        """
        healthy_instances = [i for i in self._instances if i.is_healthy]
        if not healthy_instances:
            # Try to restart unhealthy instances
            await self._recover_unhealthy_instances()
            healthy_instances = [i for i in self._instances if i.is_healthy]
            if not healthy_instances:
                raise RuntimeError("No healthy Codex App Server instances available")

        if self._selection_strategy == SelectionStrategy.LEAST_BUSY:
            # Select instance with fewest active threads
            selected = min(healthy_instances, key=lambda i: i.active_thread_count)
        else:
            # Round-robin selection
            async with self._counter_lock:
                selected_idx = self._round_robin_counter % len(healthy_instances)
                self._round_robin_counter += 1
            selected = healthy_instances[selected_idx]

        return selected

    async def _recover_unhealthy_instances(self) -> None:
        """Attempt to restart unhealthy instances."""
        unhealthy = [i for i in self._instances if not i.is_healthy]
        if not unhealthy:
            return

        logger.info(f"Attempting to recover {len(unhealthy)} unhealthy instances...")
        restart_tasks = [instance.restart() for instance in unhealthy]
        results = await asyncio.gather(*restart_tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Failed to recover instance {unhealthy[i].instance_id}: {result}")
            else:
                logger.info(f"Recovered instance {unhealthy[i].instance_id}")

    async def _get_instance_for_thread(self, thread_id: str) -> Optional[CodexAppServerInstance]:
        """Get the instance that owns a thread.

        Args:
            thread_id: The thread ID to look up

        Returns:
            The owning instance, or None if not found
        """
        async with self._affinity_lock:
            instance_idx = self._thread_affinity.get(thread_id)
            if instance_idx is not None and instance_idx < len(self._instances):
                return self._instances[instance_idx]
        return None

    async def _register_thread_affinity(
        self,
        thread_id: str,
        instance: CodexAppServerInstance,
    ) -> None:
        """Register thread ID to instance mapping.

        Args:
            thread_id: The thread ID
            instance: The instance that owns this thread
        """
        async with self._affinity_lock:
            self._thread_affinity[thread_id] = instance.instance_id
        instance.register_thread(thread_id)
        logger.debug(f"Registered thread {thread_id} -> instance {instance.instance_id}")

    async def create_thread(self, config: AppServerConfig) -> str:
        """Create a new thread via the pool.

        Selects an instance and creates a thread on it.

        Args:
            config: Thread configuration

        Returns:
            Thread ID for subsequent turns
        """
        await self.ensure_started()

        instance = await self._select_instance_for_new_conversation()
        thread_id = await instance.create_thread(config)

        await self._register_thread_affinity(thread_id, instance)

        return thread_id

    async def start_turn(
        self,
        thread_id: str,
        input_items: List[Dict[str, Any]],
        config: AppServerConfig,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Start a turn on an existing thread.

        Routes to the instance that owns the thread.

        Args:
            thread_id: Thread ID from create_thread
            input_items: List of input items (text, localImage, image)
            config: Turn configuration

        Yields:
            Streaming events
        """
        await self.ensure_started()

        # Find the owning instance
        instance = await self._get_instance_for_thread(thread_id)
        if instance is None:
            raise RuntimeError(f"Thread {thread_id} not found in pool")

        if not instance.is_healthy:
            logger.warning(
                f"Instance {instance.instance_id} for thread {thread_id} is unhealthy. "
                "Attempting restart..."
            )
            await instance.restart()

        logger.debug(f"Routing turn to instance {instance.instance_id} (thread={thread_id})")

        async for event in instance.start_turn(thread_id, input_items, config):
            yield event

    async def interrupt_turn(self, thread_id: str) -> bool:
        """Interrupt an ongoing turn.

        Args:
            thread_id: Thread ID

        Returns:
            True if interrupt was successful
        """
        instance = await self._get_instance_for_thread(thread_id)
        if instance is None:
            logger.warning(f"Cannot interrupt: thread {thread_id} not found")
            return False

        return await instance.interrupt_turn(thread_id)

    def release_thread(self, thread_id: str) -> bool:
        """Release a thread from the pool.

        Call this when an agent session ends to clean up thread affinity.

        Args:
            thread_id: The thread ID to release

        Returns:
            True if the thread was found and released
        """
        # Remove from affinity mapping
        instance_idx = self._thread_affinity.pop(thread_id, None)
        if instance_idx is not None and instance_idx < len(self._instances):
            instance = self._instances[instance_idx]
            instance.release_thread(thread_id)
            logger.debug(f"Released thread {thread_id} from instance {instance_idx}")
            return True
        return False

    async def shutdown(self) -> None:
        """Gracefully shutdown all server instances."""
        logger.info("Shutting down Codex App Server pool...")

        # Shutdown all instances concurrently
        shutdown_tasks = [instance.shutdown() for instance in self._instances]
        await asyncio.gather(*shutdown_tasks, return_exceptions=True)

        self._instances.clear()
        self._thread_affinity.clear()
        self._started = False
        self._round_robin_counter = 0

        logger.info("Codex App Server pool shutdown complete")

    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics.

        Returns:
            Dict with pool stats including instance health and thread counts
        """
        return {
            "pool_size": self._pool_size,
            "selection_strategy": self._selection_strategy.value,
            "started": self._started,
            "instances": [
                {
                    "id": instance.instance_id,
                    "healthy": instance.is_healthy,
                    "started": instance.is_started,
                    "active_threads": instance.active_thread_count,
                }
                for instance in self._instances
            ],
            "total_threads": len(self._thread_affinity),
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
        return sum(1 for i in self._instances if i.is_healthy)
