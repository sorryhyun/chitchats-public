"""
Service layer for agent operations.

This module handles high-level agent operations that require coordination
between CRUD operations and other services (like agent manager cleanup).
"""

from typing import TYPE_CHECKING

import crud
from domain.task_identifier import TaskIdentifier
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from orchestration import ChatOrchestrator
    from sdk import AgentManager


async def delete_agent_with_cleanup(db: AsyncSession, agent_id: int, agent_manager: "AgentManager") -> bool:
    """
    Delete an agent permanently and cleanup all associated clients.

    Args:
        db: Database session
        agent_id: ID of the agent to delete
        agent_manager: AgentManager instance for cleanup

    Returns:
        True if agent was deleted, False if agent not found
    """
    # Delete from database
    success = await crud.delete_agent(db, agent_id)
    if not success:
        return False

    # Cleanup all clients for this agent across all rooms
    # Use ClientPool's get_keys_for_agent helper
    pool_keys_to_cleanup = agent_manager.client_pool.get_keys_for_agent(agent_id)
    for pool_key in pool_keys_to_cleanup:
        await agent_manager.client_pool.cleanup(pool_key)

    return True


async def remove_agent_from_room_with_cleanup(
    db: AsyncSession, room_id: int, agent_id: int, agent_manager: "AgentManager"
) -> bool:
    """
    Remove an agent from a room and cleanup the associated client.

    Args:
        db: Database session
        room_id: ID of the room
        agent_id: ID of the agent to remove
        agent_manager: AgentManager instance for cleanup

    Returns:
        True if agent was removed, False if room or agent not found
    """
    # Remove from database
    success = await crud.remove_agent_from_room(db, room_id, agent_id)
    if not success:
        return False

    # Cleanup the client for this room-agent pair
    pool_key = TaskIdentifier(room_id=room_id, agent_id=agent_id)
    await agent_manager.client_pool.cleanup(pool_key)

    return True


async def delete_room_with_cleanup(
    db: AsyncSession, room_id: int, agent_manager: "AgentManager", chat_orchestrator: "ChatOrchestrator" = None
) -> bool:
    """
    Delete a room and cleanup all associated agent clients and orchestrator state.

    Args:
        db: Database session
        room_id: ID of the room to delete
        agent_manager: AgentManager instance for cleanup
        chat_orchestrator: ChatOrchestrator instance for state cleanup (optional for backwards compatibility)

    Returns:
        True if room was deleted, False if room not found
    """
    import logging

    logger = logging.getLogger("AgentService")

    # Get all agents in the room before deletion for cleanup
    agents = await crud.get_agents(db, room_id)

    # Clean up orchestrator state FIRST (interrupts any active processing)
    if chat_orchestrator:
        try:
            logger.info(f"🧹 Cleaning up orchestrator state for room {room_id}")
            await chat_orchestrator.cleanup_room_state(room_id, agent_manager)
        except Exception as e:
            logger.error(f"❌ Error cleaning orchestrator state for room {room_id}: {e}")
            # Continue with deletion even if orchestrator cleanup fails
    else:
        logger.warning(f"⚠️  No chat_orchestrator provided for room {room_id} deletion - state may leak")

    # Delete from database
    success = await crud.delete_room(db, room_id)
    if not success:
        return False

    # Cleanup all clients for this room (with error handling for each client)
    for agent in agents:
        try:
            pool_key = TaskIdentifier(room_id=room_id, agent_id=agent.id)
            await agent_manager.client_pool.cleanup(pool_key)
            logger.info(f"✅ Cleaned up client for agent {agent.id} in room {room_id}")
        except Exception as e:
            logger.error(f"❌ Error cleaning up client for agent {agent.id} in room {room_id}: {e}")
            # Continue cleaning up other agents even if one fails

    logger.info(f"✅ Room {room_id} deleted successfully")
    return True


async def clear_room_messages_with_cleanup(
    db: AsyncSession, room_id: int, agent_manager: "AgentManager", chat_orchestrator: "ChatOrchestrator" = None
) -> bool:
    """
    Clear all messages from a room and reset agent sessions.

    When messages are cleared, we also need to:
    1. Interrupt any active processing
    2. Clear agent session IDs (so they start fresh conversations)
    3. Cleanup agent clients (so they don't try to resume invalid sessions)

    Args:
        db: Database session
        room_id: ID of the room to clear messages from
        agent_manager: AgentManager instance for cleanup
        chat_orchestrator: ChatOrchestrator instance for interrupting active processing (optional)

    Returns:
        True if messages were cleared, False if room not found
    """
    import logging

    logger = logging.getLogger("AgentService")

    # Get all agents in the room for cleanup
    agents = await crud.get_agents(db, room_id)
    logger.info(f"🗑️  Clearing room {room_id} messages | Agents: {len(agents)}")

    # Interrupt any active processing FIRST (don't save partial responses since we're clearing all)
    if chat_orchestrator:
        try:
            logger.info(f"🛑 Interrupting room {room_id} processing before clearing messages")
            await chat_orchestrator.interrupt_room_processing(room_id, agent_manager, save_partial_responses=False)
        except Exception as e:
            logger.error(f"❌ Error interrupting room {room_id}: {e}")
            # Continue with cleanup even if interruption fails

    # Delete all messages
    success = await crud.delete_room_messages(db, room_id)
    if not success:
        return False
    logger.info(f"✅ Deleted all messages from room {room_id}")

    # Clear all session IDs for this room (fresh start)
    # This is done by deleting the RoomAgentSession records
    from database import serialized_write
    from infrastructure.database import RoomAgentSession
    from sqlalchemy import delete

    async with serialized_write():
        await db.execute(delete(RoomAgentSession).where(RoomAgentSession.room_id == room_id))
        await db.commit()
    logger.info(f"✅ Cleared all session IDs for room {room_id}")

    # Cleanup all clients for this room (they may have stale session references)
    for agent in agents:
        try:
            pool_key = TaskIdentifier(room_id=room_id, agent_id=agent.id)
            logger.info(f"🧹 Calling client_pool.cleanup for {pool_key}")
            await agent_manager.client_pool.cleanup(pool_key)
        except Exception as e:
            logger.error(f"❌ Error cleaning up client for agent {agent.id}: {e}")
            # Continue with other agents

    # Invalidate caches so subsequent polls don't return stale messages
    crud.invalidate_room_cache(room_id)
    logger.info(f"🧽 Invalidated room {room_id} cache after clearing messages")

    logger.info(f"✅ Room {room_id} cleared successfully")
    return True
