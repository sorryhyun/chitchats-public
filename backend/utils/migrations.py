"""
Database migration utilities for Claude Code Role Play.

This module provides automatic schema migration functionality to handle
database upgrades without requiring manual deletion of the database file.
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


async def run_migrations(engine: AsyncEngine):
    """
    Run all database migrations to ensure schema is up-to-date.

    This function checks for missing columns and adds them with appropriate
    defaults, allowing seamless upgrades from older database versions.

    Args:
        engine: SQLAlchemy async engine connected to the database
    """
    logger.info("🔄 Running database migrations...")

    async with engine.begin() as conn:
        # Migration 1: Add participant fields to messages table (PR #11)
        await _add_participant_fields(conn)

        # Migration 2: Add is_critic field to agents table (PR #11)
        await _add_is_critic_field(conn)

        # Migration 3: Fix existing Critic agents to have is_critic=1
        await _fix_critic_agents(conn)

        # Migration 4: Add anti_pattern field to agents table
        await _add_anti_pattern_field(conn)

        # Migration 5: Refresh profile_pic data from filesystem
        await _refresh_profile_pics(conn)

        # Migration 6: Reload system prompt for all agents
        await _reload_system_prompts(conn)

        # Migration 7: Add group field to agents table
        await _add_group_field(conn)

        # Migration 8: Sync agent paths and groups from filesystem
        await _sync_agent_paths_from_filesystem(conn)

        # Migration 9: Add last_read_at field to rooms table
        await _add_last_read_at_field(conn)

        # Migration 10: Remove backgrounds and memory columns from agents table
        await _remove_deprecated_memory_fields(conn)

        # Migration 11: Add composite index for room/timestamp on messages
        await _add_message_timestamp_index(conn)

        # Migration 12: Add index for room last_activity_at lookups
        await _add_last_activity_index(conn)

        # Migration 13: Remove anti_pattern column from agents table
        await _remove_anti_pattern_field(conn)

        # Migration 14: Add owner_id to rooms and scope uniqueness by owner
        await _add_room_owner_and_scoped_uniqueness(conn)

        # Migration 15: Add joined_at to room_agents for invitation tracking
        await _add_joined_at_to_room_agents(conn)

        # Migration 16: Add image_data column to messages for image attachments
        await _add_image_data_to_messages(conn)

    logger.info("✅ Database migrations completed")


async def _add_participant_fields(conn):
    """Add participant_type and participant_name columns to messages table."""
    # Check if participant_type column exists
    result = await conn.execute(
        text("SELECT COUNT(*) as count FROM pragma_table_info('messages') WHERE name='participant_type'")
    )
    row = result.first()

    if row and row.count == 0:
        logger.info("  Adding participant_type column to messages table...")
        await conn.execute(text("ALTER TABLE messages ADD COLUMN participant_type VARCHAR"))
        logger.info("  ✓ Added participant_type column")

    # Check if participant_name column exists
    result = await conn.execute(
        text("SELECT COUNT(*) as count FROM pragma_table_info('messages') WHERE name='participant_name'")
    )
    row = result.first()

    if row and row.count == 0:
        logger.info("  Adding participant_name column to messages table...")
        await conn.execute(text("ALTER TABLE messages ADD COLUMN participant_name VARCHAR"))
        logger.info("  ✓ Added participant_name column")


async def _add_is_critic_field(conn):
    """Add is_critic column to agents table."""
    # Check if is_critic column exists
    result = await conn.execute(
        text("SELECT COUNT(*) as count FROM pragma_table_info('agents') WHERE name='is_critic'")
    )
    row = result.first()

    if row and row.count == 0:
        logger.info("  Adding is_critic column to agents table...")
        await conn.execute(text("ALTER TABLE agents ADD COLUMN is_critic INTEGER DEFAULT 0"))
        logger.info("  ✓ Added is_critic column")


async def _fix_critic_agents(conn):
    """Fix existing agents named 'Critic' to have is_critic=1."""
    logger.info("  Checking for Critic agents to fix...")
    result = await conn.execute(text("UPDATE agents SET is_critic = 1 WHERE LOWER(name) = 'critic' AND is_critic = 0"))
    if result.rowcount > 0:
        logger.info(f"  ✓ Fixed {result.rowcount} Critic agent(s) to have is_critic=1")
    else:
        logger.info("  No Critic agents needed fixing")


async def _add_anti_pattern_field(conn):
    """Add anti_pattern column to agents table."""
    # Check if anti_pattern column exists
    result = await conn.execute(
        text("SELECT COUNT(*) as count FROM pragma_table_info('agents') WHERE name='anti_pattern'")
    )
    row = result.first()

    if row and row.count == 0:
        logger.info("  Adding anti_pattern column to agents table...")
        await conn.execute(text("ALTER TABLE agents ADD COLUMN anti_pattern TEXT"))
        logger.info("  ✓ Added anti_pattern column")


async def _refresh_profile_pics(conn):
    """Refresh profile_pic data from filesystem for all agents."""
    from pathlib import Path

    logger.info("  Refreshing profile_pic data from filesystem...")

    # Get all agents
    result = await conn.execute(text("SELECT id, name, config_file, profile_pic FROM agents"))
    agents = result.fetchall()

    if not agents:
        logger.info("  No agents found to refresh")
        return

    updated_count = 0
    backend_dir = Path(__file__).parent
    project_root = backend_dir.parent
    agents_dir = project_root / "agents"

    # Common image extensions
    image_extensions = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"]
    common_names = ["profile", "avatar", "picture", "photo"]

    for agent in agents:
        agent_id = agent.id
        agent_name = agent.name
        config_file = agent.config_file
        current_profile_pic = agent.profile_pic

        # Skip if profile_pic is already set to a base64 data URL
        if current_profile_pic and current_profile_pic.startswith("data:"):
            continue

        # Try to find profile picture in filesystem
        found_pic = None

        # Check folder-based config
        if config_file:
            agent_folder = agents_dir / agent_name
            if agent_folder.exists() and agent_folder.is_dir():
                # First, try common profile pic filenames
                for name in common_names:
                    for ext in image_extensions:
                        pic_path = agent_folder / f"{name}{ext}"
                        if pic_path.exists():
                            found_pic = pic_path.name
                            break
                    if found_pic:
                        break

                # If no common name found, look for any image file
                if not found_pic:
                    for ext in image_extensions:
                        for file in agent_folder.glob(f"*{ext}"):
                            found_pic = file.name
                            break
                        if found_pic:
                            break

        # Also check legacy single-file format
        if not found_pic:
            for ext in image_extensions:
                legacy_pic = agents_dir / f"{agent_name}{ext}"
                if legacy_pic.exists():
                    found_pic = legacy_pic.name
                    break

        # Update database if we found a profile pic and it's different from current
        if found_pic and found_pic != current_profile_pic:
            await conn.execute(
                text("UPDATE agents SET profile_pic = :pic WHERE id = :id"), {"pic": found_pic, "id": agent_id}
            )
            logger.info(f"  ✓ Updated profile_pic for '{agent_name}': {found_pic}")
            updated_count += 1

    if updated_count > 0:
        logger.info(f"  ✓ Refreshed profile_pic for {updated_count} agent(s)")
    else:
        logger.info("  No profile_pic updates needed")


async def _reload_system_prompts(conn):
    """Reload system prompt from filesystem for all agents."""
    from config import get_base_system_prompt, parse_agent_config
    from domain.agent_config import AgentConfigData

    logger.info("  Reloading system prompts from filesystem...")

    # Load current system prompt from file
    system_prompt_template = get_base_system_prompt()

    # Get all agents
    result = await conn.execute(text("SELECT id, name, config_file FROM agents"))
    agents = result.fetchall()

    if not agents:
        logger.info("  No agents found to update")
        return

    # Update each agent's system prompt
    updated_count = 0
    for agent in agents:
        agent_id = agent.id
        agent_name = agent.name
        config_file = agent.config_file

        # Format system prompt with agent name
        from utils.korean_particles import format_with_particles

        formatted_prompt = format_with_particles(system_prompt_template, agent_name=agent_name)

        # Always append character configuration with markdown headings
        if config_file:
            # Load agent config from filesystem
            file_config = parse_agent_config(config_file)
            if file_config:
                # Convert to AgentConfigData and generate markdown
                agent_config = AgentConfigData(
                    in_a_nutshell=file_config.in_a_nutshell,
                    characteristics=file_config.characteristics,
                    recent_events=file_config.recent_events,
                    long_term_memory_subtitles=file_config.long_term_memory_subtitles,
                )
                config_markdown = agent_config.to_system_prompt_markdown(agent_name)
                if config_markdown:
                    formatted_prompt += config_markdown

        # Update the agent's system prompt in database
        await conn.execute(
            text("UPDATE agents SET system_prompt = :prompt WHERE id = :id"),
            {"prompt": formatted_prompt, "id": agent_id},
        )
        updated_count += 1

    logger.info(f"  ✓ Reloaded system prompt for {updated_count} agent(s)")


async def _add_group_field(conn):
    """Add group column to agents table."""
    # Check if group column exists
    result = await conn.execute(text("SELECT COUNT(*) as count FROM pragma_table_info('agents') WHERE name='group'"))
    row = result.first()

    if row and row.count == 0:
        logger.info("  Adding group column to agents table...")
        await conn.execute(text('ALTER TABLE agents ADD COLUMN "group" VARCHAR'))
        # Create index on group column
        await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_agents_group ON agents("group")'))
        logger.info("  ✓ Added group column with index")


async def _sync_agent_paths_from_filesystem(conn):
    """Sync agent config_file paths and groups from filesystem."""
    from config import list_available_configs

    logger.info("  Syncing agent paths and groups from filesystem...")

    # Get current filesystem structure
    available_configs = list_available_configs()

    if not available_configs:
        logger.info("  No agent configs found in filesystem")
        return

    # Get all agents from database
    result = await conn.execute(text('SELECT id, name, config_file, "group" FROM agents'))
    agents = result.fetchall()

    if not agents:
        logger.info("  No agents found in database")
        return

    updated_count = 0
    for agent in agents:
        agent_id = agent.id
        agent_name = agent.name
        current_config_file = agent.config_file
        current_group = agent.group

        # Check if agent exists in filesystem
        if agent_name not in available_configs:
            logger.warning(f"  ⚠ Agent '{agent_name}' not found in filesystem, skipping")
            continue

        # Get correct path and group from filesystem
        fs_config = available_configs[agent_name]
        correct_path = fs_config["path"]
        correct_group = fs_config["group"]

        # Update if path or group has changed
        if current_config_file != correct_path or current_group != correct_group:
            await conn.execute(
                text('UPDATE agents SET config_file = :path, "group" = :group WHERE id = :id'),
                {"path": correct_path, "group": correct_group, "id": agent_id},
            )
            logger.info(f"  ✓ Updated '{agent_name}': path={correct_path}, group={correct_group}")
            updated_count += 1

    if updated_count > 0:
        logger.info(f"  ✓ Synced paths/groups for {updated_count} agent(s)")
    else:
        logger.info("  No path/group updates needed")


async def _add_last_read_at_field(conn):
    """Add last_read_at column to rooms table for tracking unread messages."""
    # Check if last_read_at column exists
    result = await conn.execute(
        text("SELECT COUNT(*) as count FROM pragma_table_info('rooms') WHERE name='last_read_at'")
    )
    row = result.first()

    if row and row.count == 0:
        logger.info("  Adding last_read_at column to rooms table...")
        await conn.execute(text("ALTER TABLE rooms ADD COLUMN last_read_at DATETIME"))
        logger.info("  ✓ Added last_read_at column")


async def _remove_deprecated_memory_fields(conn):
    """
    Remove deprecated backgrounds and memory columns from agents table.

    These fields have been replaced by consolidated_memory.md files.
    Uses SQLite's ALTER TABLE DROP COLUMN (requires SQLite 3.35.0+).
    Falls back gracefully if not supported.
    """
    # Check if backgrounds column exists
    result = await conn.execute(
        text("SELECT COUNT(*) as count FROM pragma_table_info('agents') WHERE name='backgrounds'")
    )
    row = result.first()

    if row and row.count > 0:
        logger.info("  Removing deprecated backgrounds column from agents table...")
        try:
            await conn.execute(text("ALTER TABLE agents DROP COLUMN backgrounds"))
            logger.info("  ✓ Removed backgrounds column")
        except Exception as e:
            logger.warning(f"  ⚠ Could not drop backgrounds column (SQLite version may not support it): {e}")
            logger.info("  Column will remain in database but is unused")

    # Check if memory column exists
    result = await conn.execute(text("SELECT COUNT(*) as count FROM pragma_table_info('agents') WHERE name='memory'"))
    row = result.first()

    if row and row.count > 0:
        logger.info("  Removing deprecated memory column from agents table...")
        try:
            await conn.execute(text("ALTER TABLE agents DROP COLUMN memory"))
            logger.info("  ✓ Removed memory column")
        except Exception as e:
            logger.warning(f"  ⚠ Could not drop memory column (SQLite version may not support it): {e}")
            logger.info("  Column will remain in database but is unused")


async def _add_message_timestamp_index(conn):
    """Add composite index on messages(room_id, timestamp) if missing."""
    result = await conn.execute(
        text("SELECT COUNT(*) as count FROM pragma_index_list('messages') WHERE name='idx_message_room_timestamp'")
    )
    row = result.first()

    if row and row.count == 0:
        logger.info("  Adding idx_message_room_timestamp index to messages table...")
        await conn.execute(text("CREATE INDEX idx_message_room_timestamp ON messages (room_id, timestamp)"))
        logger.info("  ✓ Added idx_message_room_timestamp index")
    else:
        logger.info("  idx_message_room_timestamp index already exists")


async def _add_last_activity_index(conn):
    """Add index on rooms.last_activity_at for active room lookups."""
    result = await conn.execute(
        text("SELECT COUNT(*) as count FROM pragma_index_list('rooms') WHERE name='ix_rooms_last_activity_at'")
    )
    row = result.first()

    if row and row.count == 0:
        logger.info("  Adding ix_rooms_last_activity_at index to rooms table...")
        await conn.execute(text("CREATE INDEX ix_rooms_last_activity_at ON rooms (last_activity_at)"))
        logger.info("  ✓ Added ix_rooms_last_activity_at index")
    else:
        logger.info("  ix_rooms_last_activity_at index already exists")


async def _remove_anti_pattern_field(conn):
    """
    Remove anti_pattern column from agents table.

    This field is being disabled to allow observation of agent behavior
    before deciding on a refactored approach.
    Uses SQLite's ALTER TABLE DROP COLUMN (requires SQLite 3.35.0+).
    Falls back gracefully if not supported.
    """
    # Check if anti_pattern column exists
    result = await conn.execute(
        text("SELECT COUNT(*) as count FROM pragma_table_info('agents') WHERE name='anti_pattern'")
    )
    row = result.first()

    if row and row.count > 0:
        logger.info("  Removing anti_pattern column from agents table...")
        try:
            await conn.execute(text("ALTER TABLE agents DROP COLUMN anti_pattern"))
            logger.info("  ✓ Removed anti_pattern column")
        except Exception as e:
            logger.warning(f"  ⚠ Could not drop anti_pattern column (SQLite version may not support it): {e}")
            logger.info("  Column will remain in database but is unused")


async def _add_room_owner_and_scoped_uniqueness(conn):
    """Add owner_id column and enforce room-name uniqueness per owner."""

    # Check existing schema
    result = await conn.execute(text("PRAGMA table_info('rooms')"))
    columns = result.fetchall()
    has_owner_column = any(col.name == "owner_id" for col in columns)

    result = await conn.execute(text("PRAGMA index_list('rooms')"))
    indexes = result.fetchall()
    has_composite_unique = any(index.name == "ux_rooms_owner_name" for index in indexes)

    if has_owner_column and has_composite_unique:
        logger.info("  Rooms table already has owner_id and scoped uniqueness")
        return

    logger.info("  Rebuilding rooms table with owner_id and per-owner unique constraint...")

    await conn.execute(text("PRAGMA foreign_keys=off"))
    await conn.execute(text("ALTER TABLE rooms RENAME TO rooms_old"))

    await conn.execute(
        text(
            """
            CREATE TABLE rooms (
                id INTEGER NOT NULL PRIMARY KEY,
                owner_id VARCHAR,
                name VARCHAR NOT NULL,
                max_interactions INTEGER,
                is_paused INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
                last_activity_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
                last_read_at DATETIME
            );
            """
        )
    )

    await conn.execute(text("CREATE UNIQUE INDEX ux_rooms_owner_name ON rooms(owner_id, name)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_rooms_last_activity_at ON rooms(last_activity_at)"))

    if has_owner_column:
        insert_sql = (
            "INSERT INTO rooms (id, owner_id, name, max_interactions, is_paused, created_at, last_activity_at, last_read_at) "
            "SELECT id, owner_id, name, max_interactions, is_paused, created_at, last_activity_at, last_read_at FROM rooms_old"
        )
    else:
        insert_sql = (
            "INSERT INTO rooms (id, owner_id, name, max_interactions, is_paused, created_at, last_activity_at, last_read_at) "
            "SELECT id, 'admin' as owner_id, name, max_interactions, is_paused, created_at, last_activity_at, last_read_at FROM rooms_old"
        )

    await conn.execute(text(insert_sql))

    await conn.execute(text("DROP TABLE rooms_old"))
    await conn.execute(text("PRAGMA foreign_keys=on"))
    logger.info("  ✓ Rooms table rebuilt with owner_id and scoped uniqueness")


async def _add_joined_at_to_room_agents(conn):
    """Add joined_at column to room_agents table for invitation tracking."""
    # Check if joined_at column exists
    result = await conn.execute(
        text("SELECT COUNT(*) as count FROM pragma_table_info('room_agents') WHERE name='joined_at'")
    )
    row = result.first()

    if row and row.count == 0:
        logger.info("  Adding joined_at column to room_agents table...")
        await conn.execute(text("ALTER TABLE room_agents ADD COLUMN joined_at DATETIME"))
        logger.info("  ✓ Added joined_at column")


async def _add_image_data_to_messages(conn):
    """Add image_data column to messages table for image attachments."""
    # Check if image_data column exists
    result = await conn.execute(
        text("SELECT COUNT(*) as count FROM pragma_table_info('messages') WHERE name='image_data'")
    )
    row = result.first()

    if row and row.count == 0:
        logger.info("  Adding image_data column to messages table...")
        await conn.execute(text("ALTER TABLE messages ADD COLUMN image_data TEXT"))
        logger.info("  ✓ Added image_data column for image attachments")
