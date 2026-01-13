"""
CRUD operations for Agent entities.
"""

import logging
from datetime import datetime
from typing import List, Optional

from infrastructure.database import Agent
import schemas
from config import list_available_configs, parse_agent_config
from domain.agent_config import AgentConfigData
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from .helpers import merge_agent_configs, persist_agent_to_filesystem, save_base64_profile_pic

logger = logging.getLogger("CRUD")


async def create_agent(db: AsyncSession, agent: schemas.AgentCreate) -> Agent:
    """Create an agent as an independent entity (not tied to any room initially)."""
    config_file = agent.config_file

    # If no config_file provided but custom fields are given, persist to filesystem first
    if not config_file and (agent.in_a_nutshell or agent.characteristics):
        config_file = persist_agent_to_filesystem(
            agent_name=agent.name,
            group=agent.group,
            in_a_nutshell=agent.in_a_nutshell or "",
            characteristics=agent.characteristics or "",
            recent_events=agent.recent_events,
            profile_pic_base64=agent.profile_pic if agent.profile_pic and agent.profile_pic.startswith("data:") else None,
        )

    # Parse config file if provided to populate fields
    file_config = parse_agent_config(config_file) if config_file else None

    # Create AgentConfigData from provided values
    provided_config = AgentConfigData(
        in_a_nutshell=agent.in_a_nutshell, characteristics=agent.characteristics, recent_events=agent.recent_events
    )

    # Merge configs: use provided values, fall back to file values
    final_config = merge_agent_configs(provided_config, file_config)

    # For profile_pic: use provided value, or fall back to file config
    profile_pic = agent.profile_pic
    # Clear base64 data from DB field if saved to filesystem
    if profile_pic and profile_pic.startswith("data:"):
        profile_pic = None
    if not profile_pic and file_config:
        profile_pic = file_config.profile_pic

    # Build system prompt using centralized helper
    from services.prompt_builder import build_system_prompt

    system_prompt = build_system_prompt(agent.name, final_config)

    # Load group config to get interrupt_every_turn, priority, and transparent if agent belongs to a group
    interrupt_every_turn = agent.interrupt_every_turn  # Use provided value by default
    priority = agent.priority  # Use provided value by default
    transparent = agent.transparent  # Use provided value by default

    if agent.group:
        from sdk.config.loaders import get_group_config

        group_config = get_group_config(agent.group)
        # Override with group config if present
        if "interrupt_every_turn" in group_config:
            interrupt_every_turn = group_config["interrupt_every_turn"]
        if "priority" in group_config:
            priority = group_config["priority"]
        if "transparent" in group_config:
            transparent = group_config["transparent"]

    db_agent = Agent(
        name=agent.name,
        group=agent.group,
        config_file=config_file,
        profile_pic=profile_pic,
        in_a_nutshell=final_config.in_a_nutshell,
        characteristics=final_config.characteristics,
        recent_events=final_config.recent_events,
        system_prompt=system_prompt,
        is_critic=agent.is_critic,
        interrupt_every_turn=bool(interrupt_every_turn),
        priority=priority,
        transparent=bool(transparent),
    )
    db.add(db_agent)
    await db.commit()
    await db.refresh(db_agent)
    return db_agent


async def get_all_agents(db: AsyncSession) -> List[Agent]:
    """Get all agents globally."""
    result = await db.execute(select(Agent))
    return result.scalars().all()


async def get_agents_by_ids(db: AsyncSession, agent_ids: List[int]) -> List[Agent]:
    """
    Get agents by a list of IDs.

    More efficient than fetching all room agents when only a few are needed.

    Args:
        db: Database session
        agent_ids: List of agent IDs to fetch

    Returns:
        List of agents matching the provided IDs
    """
    if not agent_ids:
        return []
    result = await db.execute(select(Agent).where(Agent.id.in_(agent_ids)))
    return list(result.scalars().all())


async def get_agent(db: AsyncSession, agent_id: int) -> Optional[Agent]:
    """Get a specific agent by ID."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    return result.scalar_one_or_none()


async def delete_agent(db: AsyncSession, agent_id: int) -> bool:
    """Delete an agent permanently."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent:
        await db.delete(agent)
        await db.commit()
        return True
    return False


async def update_agent(db: AsyncSession, agent_id: int, agent_update: schemas.AgentUpdate) -> Optional[Agent]:
    """Update an agent's nutshell, characteristics, backgrounds, memory, or recent events and rebuild system prompt."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()

    if not agent:
        return None

    # Update fields if provided
    if agent_update.profile_pic is not None:
        # Check if it's a base64 data URL
        if agent_update.profile_pic.startswith("data:image/"):
            # Save to filesystem and clear database field
            save_base64_profile_pic(agent.name, agent_update.profile_pic)
            agent.profile_pic = None  # Clear DB field - images served from filesystem
        else:
            # Store as-is (for backward compatibility)
            agent.profile_pic = agent_update.profile_pic
    if agent_update.in_a_nutshell is not None:
        agent.in_a_nutshell = agent_update.in_a_nutshell
    if agent_update.characteristics is not None:
        agent.characteristics = agent_update.characteristics
    if agent_update.recent_events is not None:
        agent.recent_events = agent_update.recent_events

    # Rebuild system prompt using centralized helper
    from services.prompt_builder import build_system_prompt

    config_data = agent.get_config_data(use_cache=False)  # Don't use cache during update
    agent.system_prompt = build_system_prompt(agent.name, config_data)

    await db.commit()
    await db.refresh(agent)

    # Invalidate agent config cache
    from infrastructure.cache import agent_config_key, agent_object_key, get_cache

    cache = get_cache()
    cache.invalidate(agent_config_key(agent_id))
    cache.invalidate(agent_object_key(agent_id))

    return agent


async def reload_agent_from_config(db: AsyncSession, agent_id: int) -> Optional[Agent]:
    """Reload an agent's data from its config file and rebuild system prompt."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()

    if not agent:
        return None

    # Check if agent has a config file
    if not agent.config_file:
        raise ValueError(f"Agent {agent.name} does not have a config file to reload from")

    # Load config using service
    from services import AgentConfigService

    config_data = AgentConfigService.load_agent_config(agent.config_file)

    if not config_data:
        raise ValueError(f"Failed to load config from {agent.config_file}")

    # Update all fields from config file (config_data is now AgentConfigData)
    agent.in_a_nutshell = config_data.in_a_nutshell
    agent.characteristics = config_data.characteristics
    agent.recent_events = config_data.recent_events
    agent.profile_pic = config_data.profile_pic

    # Auto-detect if agent is a critic based on name
    agent.is_critic = agent.name.lower() == "critic"

    # Load group config to update interrupt_every_turn, priority, and transparent if agent belongs to a group
    if agent.group:
        from sdk.config.loaders import get_group_config

        group_config = get_group_config(agent.group)
        if "interrupt_every_turn" in group_config:
            agent.interrupt_every_turn = bool(group_config["interrupt_every_turn"])
        else:
            agent.interrupt_every_turn = False  # Reset to default if not in group config

        if "priority" in group_config:
            agent.priority = group_config["priority"]
        else:
            agent.priority = 0  # Reset to default if not in group config

        if "transparent" in group_config:
            agent.transparent = bool(group_config["transparent"])
        else:
            agent.transparent = False  # Reset to default if not in group config
    else:
        # Reset to defaults if no group
        agent.interrupt_every_turn = False
        agent.priority = 0
        agent.transparent = False

    # Rebuild system prompt from updated values using centralized helper
    from services.prompt_builder import build_system_prompt

    config_obj = agent.get_config_data(use_cache=False)  # Don't use cache during reload
    agent.system_prompt = build_system_prompt(agent.name, config_obj)

    await db.commit()
    await db.refresh(agent)

    # Invalidate agent config cache
    from infrastructure.cache import agent_config_key, agent_object_key, get_cache

    cache = get_cache()
    cache.invalidate(agent_config_key(agent_id))
    cache.invalidate(agent_object_key(agent_id))

    return agent


async def append_agent_memory(db: AsyncSession, agent_id: int, memory_entry: str) -> Optional[Agent]:
    """
    Append a new memory entry to an agent's recent_events file.
    FILESYSTEM-PRIMARY: Only writes to filesystem, database is cache.

    Args:
        db: Database session
        agent_id: ID of the agent
        memory_entry: One-liner memory to append (will be prefixed with "- ")

    Returns:
        Agent object (unchanged) or None if agent not found
    """
    from services import AgentConfigService

    # Get the agent
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()

    if not agent:
        return None

    # FILESYSTEM-PRIMARY: Only write to filesystem
    # Database will be loaded fresh from filesystem on next read via get_config_data()
    if agent.config_file:
        timestamp = datetime.utcnow()
        success = AgentConfigService.append_to_recent_events(
            config_file=agent.config_file, memory_entry=memory_entry, timestamp=timestamp
        )
        if success:
            # Invalidate agent config cache since recent_events changed
            from infrastructure.cache import agent_config_key, get_cache

            cache = get_cache()
            cache.invalidate(agent_config_key(agent_id))
        else:
            logger.warning(f"Failed to append memory to {agent.config_file}")
    else:
        logger.warning(f"Agent {agent.name} has no config file, cannot append memory")

    # Return agent without modifying database
    return agent


async def seed_agents_from_configs(db: AsyncSession) -> None:
    """
    Seed agents from config files at startup if they don't exist.
    Only creates agents that don't already exist in the database.
    Supports both grouped and ungrouped agents.
    """
    available_configs = list_available_configs()

    for agent_name, config_info in available_configs.items():
        config_path = config_info["path"]
        group_name = config_info["group"]

        # Check if agent already exists
        result = await db.execute(select(Agent).where(Agent.name == agent_name))
        existing_agent = result.scalar_one_or_none()

        if not existing_agent:
            # Auto-detect if agent is a critic based on name
            is_critic = agent_name.lower() == "critic"

            # Create agent from config file
            agent_data = schemas.AgentCreate(
                name=agent_name, group=group_name, config_file=config_path, is_critic=is_critic
            )
            await create_agent(db, agent_data)
            agent_type = "critic" if is_critic else "participant"
            group_info = f" (group: {group_name})" if group_name else ""
            logger.info(f"Created {agent_type} agent '{agent_name}'{group_info} from config file: {config_path}")
