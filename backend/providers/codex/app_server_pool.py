"""
Codex App Server pool manager.

This module provides the CodexAppServerPool class that manages per-agent
`codex app-server` processes with idle timeout and instance limits.

Architecture:
    - Per-agent instances: each agent gets a dedicated app-server with MCP configs
    - Lazy creation: instances are spawned on first interaction
    - Idle timeout: instances are terminated after CODEX_IDLE_TIMEOUT seconds
    - Max instances: limited by CODEX_MAX_INSTANCES, oldest idle evicted when exceeded
    - Thread resume: threads can be resumed even after instance restart
"""

import asyncio
import logging
import os
from typing import Any, Dict, Optional

from providers.configs import CodexStartupConfig, CodexTurnConfig

from .app_server_instance import CodexAppServerInstance
from .thread_manager import ThreadSessionManager

logger = logging.getLogger("CodexAppServerPool")

# Default configuration
DEFAULT_MAX_INSTANCES = 10
DEFAULT_IDLE_TIMEOUT = 600  # seconds (10 minutes - suitable for interactive chat)
DEFAULT_CLEANUP_INTERVAL = 60  # seconds


class CodexAppServerPool:
    """Pool manager for per-agent Codex App Server instances.

    Each agent gets a dedicated app-server instance with agent-specific
    MCP configurations baked in at startup via -c flags.

    Features:
        - Lazy instance creation on first agent interaction
        - Idle timeout: instances terminated after inactivity
        - Max instances limit with LRU eviction
        - Thread resume support across instance restarts

    Usage:
        pool = await CodexAppServerPool.get_instance()

        # Get or create instance for agent
        instance = await pool.get_or_create_instance(agent_key, startup_config)

        # Create thread and start turns
        thread_id = await instance.create_thread(turn_config)
        async for event in instance.start_turn(thread_id, items, turn_config):
            # Handle events

        # At shutdown
        await pool.shutdown()
    """

    _instance: Optional["CodexAppServerPool"] = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __init__(self):
        """Initialize the pool (use get_instance() instead)."""
        # Configuration from environment
        self._max_instances = int(os.environ.get("CODEX_MAX_INSTANCES", str(DEFAULT_MAX_INSTANCES)))
        self._idle_timeout = float(os.environ.get("CODEX_IDLE_TIMEOUT", str(DEFAULT_IDLE_TIMEOUT)))
        self._cleanup_interval = float(os.environ.get("CODEX_CLEANUP_INTERVAL", str(DEFAULT_CLEANUP_INTERVAL)))

        # Per-agent instances: agent_key -> instance
        self._instances: Dict[str, CodexAppServerInstance] = {}
        self._instances_lock = asyncio.Lock()

        # Thread session management (centralized)
        self._thread_manager = ThreadSessionManager()

        # Instance counter for unique IDs
        self._instance_counter = 0

        # Cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()

    @classmethod
    async def get_instance(cls) -> "CodexAppServerPool":
        """Get the singleton instance of CodexAppServerPool.

        Returns:
            The singleton pool instance
        """
        async with cls._lock:
            if cls._instance is None:
                cls._instance = CodexAppServerPool()
                cls._instance._start_cleanup_task()
            return cls._instance

    @classmethod
    async def reset_instance(cls) -> None:
        """Reset the singleton instance (for testing)."""
        async with cls._lock:
            if cls._instance is not None:
                await cls._instance.shutdown()
                cls._instance = None

    def _start_cleanup_task(self) -> None:
        """Start the background cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.debug("Started cleanup task")

    async def _cleanup_loop(self) -> None:
        """Background loop that cleans up idle instances."""
        while not self._shutdown_event.is_set():
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=self._cleanup_interval)
                # Shutdown event was set
                break
            except asyncio.TimeoutError:
                # Normal timeout - run cleanup
                try:
                    await self._cleanup_idle_instances()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.debug(f"Cleanup error (ignoring): {e}")
            except asyncio.CancelledError:
                break

    async def _cleanup_idle_instances(self) -> None:
        """Terminate instances that have been idle too long."""
        if self._shutdown_event.is_set():
            return  # Don't cleanup during shutdown

        async with self._instances_lock:
            idle_keys = []

            for agent_key, instance in self._instances.items():
                if instance.idle_seconds > self._idle_timeout:
                    idle_keys.append(agent_key)

            for agent_key in idle_keys:
                instance = self._instances.pop(agent_key)
                logger.info(
                    f"Terminating idle instance for {agent_key} "
                    f"(idle {instance.idle_seconds:.1f}s > {self._idle_timeout}s)"
                )
                try:
                    await instance.shutdown()
                except Exception as e:
                    logger.debug(f"Error shutting down instance {agent_key}: {e}")

            if idle_keys:
                logger.info(f"Cleaned up {len(idle_keys)} idle instances")

    async def _evict_if_needed(self) -> None:
        """Evict oldest idle instance if at max capacity.

        Must be called with _instances_lock held.
        """
        if len(self._instances) < self._max_instances:
            return

        # Find the instance with oldest last_activity (most idle)
        oldest_key = None
        oldest_time = float("inf")

        for agent_key, instance in self._instances.items():
            if instance.last_activity < oldest_time:
                oldest_time = instance.last_activity
                oldest_key = agent_key

        if oldest_key:
            instance = self._instances.pop(oldest_key)
            logger.info(f"Evicting instance for {oldest_key} to make room " f"(idle {instance.idle_seconds:.1f}s)")
            await instance.shutdown()

    async def get_or_create_instance(
        self,
        agent_key: str,
        startup_config: CodexStartupConfig,
    ) -> CodexAppServerInstance:
        """Get existing instance or create new one for agent.

        Args:
            agent_key: Unique identifier for the agent (e.g., "room_1_agent_5")
            startup_config: Configuration with MCP servers for this agent

        Returns:
            Running CodexAppServerInstance for the agent
        """
        async with self._instances_lock:
            # Return existing instance if available and healthy
            if agent_key in self._instances:
                instance = self._instances[agent_key]
                if instance.is_healthy:
                    instance.touch()
                    return instance
                else:
                    # Unhealthy - remove and recreate
                    logger.warning(f"Instance for {agent_key} is unhealthy, recreating")
                    await instance.shutdown()
                    del self._instances[agent_key]

            # Evict if at capacity
            await self._evict_if_needed()

            # Create new instance
            self._instance_counter += 1
            instance = CodexAppServerInstance(
                instance_id=self._instance_counter,
                startup_config=startup_config,
                agent_key=agent_key,
            )

            logger.info(f"Creating new instance {self._instance_counter} for {agent_key}")
            await instance.start()

            self._instances[agent_key] = instance
            return instance

    async def get_instance_for_thread(
        self,
        thread_id: str,
    ) -> Optional[CodexAppServerInstance]:
        """Get the instance that owns a thread.

        Args:
            thread_id: The thread ID to look up

        Returns:
            The owning instance, or None if not found
        """
        agent_key = self._thread_manager.get_agent_for_thread(thread_id)

        if agent_key is None:
            return None

        async with self._instances_lock:
            return self._instances.get(agent_key)

    def register_thread(
        self,
        thread_id: str,
        agent_key: str,
        instance_id: Optional[int] = None,
    ) -> None:
        """Register a thread to agent mapping.

        Args:
            thread_id: The thread ID
            agent_key: The agent key that owns this thread
            instance_id: Optional instance ID that created the thread
        """
        self._thread_manager.register_thread(thread_id, agent_key, instance_id)

    async def try_resume_thread(
        self,
        thread_id: str,
        agent_key: str,
        startup_config: CodexStartupConfig,
        turn_config: CodexTurnConfig,
    ) -> Optional[CodexAppServerInstance]:
        """Try to resume a thread on an instance.

        This is called when a thread_id from the database needs to be resumed
        (e.g., after instance restart). Creates a new instance if needed and
        attempts thread/resume.

        Args:
            thread_id: The thread ID to resume
            agent_key: The agent key
            startup_config: Startup config for new instance if needed
            turn_config: Turn configuration for resume

        Returns:
            The instance that successfully resumed the thread, or None
        """
        # Get or create instance for the agent
        instance = await self.get_or_create_instance(agent_key, startup_config)

        try:
            success = await instance.resume_thread(thread_id, turn_config)
            if success:
                self.register_thread(thread_id, agent_key)
                logger.info(f"Successfully resumed thread {thread_id} on instance {instance.instance_id}")
                return instance
        except Exception as e:
            logger.warning(f"Failed to resume thread {thread_id}: {e}")

        return None

    def release_thread(self, thread_id: str) -> bool:
        """Release a thread from tracking.

        Args:
            thread_id: The thread ID to release

        Returns:
            True if the thread was found and released
        """
        return self._thread_manager.release_thread(thread_id)

    async def shutdown(self) -> None:
        """Gracefully shutdown all server instances."""
        logger.info("Shutting down Codex App Server pool...")

        try:
            # Stop cleanup task
            self._shutdown_event.set()
            if self._cleanup_task and not self._cleanup_task.done():
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass

            # Shutdown all instances concurrently with timeout
            try:
                async with asyncio.timeout(10.0):  # 10 second timeout for all shutdowns
                    async with self._instances_lock:
                        shutdown_tasks = [instance.shutdown() for instance in self._instances.values()]
                        await asyncio.gather(*shutdown_tasks, return_exceptions=True)
                        self._instances.clear()
            except asyncio.TimeoutError:
                logger.warning("Shutdown timed out, forcing cleanup")
                # Force kill any remaining processes
                for instance in self._instances.values():
                    if instance.is_healthy:
                        try:
                            instance.kill()
                        except Exception:
                            pass
                self._instances.clear()

            self._thread_manager.clear_all()

            self._instance_counter = 0
            self._shutdown_event.clear()

            logger.info("Codex App Server pool shutdown complete")

        except asyncio.CancelledError:
            # Shutdown was interrupted - force cleanup
            logger.warning("Shutdown interrupted, forcing cleanup")
            for instance in list(self._instances.values()):
                if instance.is_healthy:
                    try:
                        instance.kill()
                    except Exception:
                        pass
            self._instances.clear()
            self._thread_manager.clear_all()
            raise  # Re-raise to let the caller know

    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics.

        Returns:
            Dict with pool stats including instance health and counts
        """
        return {
            "max_instances": self._max_instances,
            "idle_timeout": self._idle_timeout,
            "active_instances": len(self._instances),
            "total_threads": self._thread_manager.thread_count,
            "instances": [
                {
                    "id": instance.instance_id,
                    "agent_key": instance.agent_key,
                    "healthy": instance.is_healthy,
                    "started": instance.is_started,
                    "idle_seconds": round(instance.idle_seconds, 1),
                    "active_threads": instance.active_thread_count,
                }
                for instance in self._instances.values()
            ],
            "thread_stats": self._thread_manager.get_stats(),
        }

    @property
    def max_instances(self) -> int:
        """Get the configured max instances."""
        return self._max_instances

    @property
    def idle_timeout(self) -> float:
        """Get the configured idle timeout."""
        return self._idle_timeout

    @property
    def active_instance_count(self) -> int:
        """Get the number of active instances."""
        return len(self._instances)

    @property
    def healthy_instance_count(self) -> int:
        """Get the number of healthy instances."""
        return sum(1 for i in self._instances.values() if i.is_healthy)
