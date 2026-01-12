"""
Database migration utilities for ChitChats (PostgreSQL and SQLite).

This module provides automatic schema migration functionality to handle
database upgrades without requiring manual deletion of the database.
"""

import logging

from database import is_sqlite
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


async def run_migrations(engine: AsyncEngine):
    """
    Run all database migrations to ensure schema is up-to-date.

    This function checks for missing columns and adds them with appropriate
    defaults, allowing seamless upgrades from older database versions.
    """
    logger.info("🔄 Running database migrations...")

    async with engine.begin() as conn:
        # Schema migrations - add missing columns/indexes
        await _migrate_agents_table(conn)
        await _migrate_messages_table(conn)
        await _migrate_rooms_table(conn)
        await _migrate_room_agents_table(conn)
        await _migrate_room_agent_sessions_table(conn)
        await _add_indexes(conn)

        # Data migrations - sync data from filesystem
        await _sync_agents_from_filesystem(conn)

    logger.info("✅ Database migrations completed")


# =============================================================================
# Schema Migrations
# =============================================================================


async def _column_exists(conn, table: str, column: str) -> bool:
    """Check if a column exists in a table (PostgreSQL and SQLite compatible)."""
    if is_sqlite():
        # SQLite: Use PRAGMA table_info
        result = await conn.execute(text(f"PRAGMA table_info({table})"))
        columns = [row[1] for row in result.fetchall()]  # Column name is at index 1
        return column in columns
    else:
        # PostgreSQL: Use information_schema
        result = await conn.execute(
            text("""
                SELECT COUNT(*) as count
                FROM information_schema.columns
                WHERE table_name = :table AND column_name = :column
            """),
            {"table": table, "column": column},
        )
        return result.first().count > 0


async def _index_exists(conn, index_name: str) -> bool:
    """Check if an index exists (PostgreSQL and SQLite compatible)."""
    if is_sqlite():
        # SQLite: Query sqlite_master
        result = await conn.execute(
            text("""
                SELECT COUNT(*) as count
                FROM sqlite_master
                WHERE type = 'index' AND name = :index_name
            """),
            {"index_name": index_name},
        )
        return result.first().count > 0
    else:
        # PostgreSQL: Use pg_indexes
        result = await conn.execute(
            text("""
                SELECT COUNT(*) as count
                FROM pg_indexes
                WHERE indexname = :index_name
            """),
            {"index_name": index_name},
        )
        return result.first().count > 0


async def _migrate_agents_table(conn):
    """Add/remove columns in agents table."""
    # Columns to add: (name, type, default)
    columns_to_add = [
        ("is_critic", "BOOLEAN", "FALSE"),
        ("group", "VARCHAR", None),  # Note: quoted in SQL due to reserved word
        ("interrupt_every_turn", "BOOLEAN", "FALSE"),
        ("priority", "INTEGER", "0"),
        ("transparent", "BOOLEAN", "FALSE"),
    ]

    # Columns to remove (deprecated)
    columns_to_remove = ["anti_pattern", "backgrounds", "memory"]

    # Add missing columns
    for col_name, col_type, default in columns_to_add:
        if not await _column_exists(conn, "agents", col_name):
            quoted_name = f'"{col_name}"' if col_name == "group" else col_name
            default_clause = f" DEFAULT {default}" if default else ""
            logger.info(f"  Adding {col_name} column to agents table...")
            await conn.execute(text(f"ALTER TABLE agents ADD COLUMN {quoted_name} {col_type}{default_clause}"))
            if col_name == "group":
                await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_agents_group ON agents("group")'))
            logger.info(f"  ✓ Added {col_name} column")

    # Remove deprecated columns (PostgreSQL only - SQLite doesn't support DROP COLUMN in older versions)
    if not is_sqlite():
        for col_name in columns_to_remove:
            if await _column_exists(conn, "agents", col_name):
                try:
                    await conn.execute(text(f"ALTER TABLE agents DROP COLUMN {col_name}"))
                    logger.info(f"  ✓ Removed deprecated {col_name} column")
                except Exception:
                    pass


async def _migrate_messages_table(conn):
    """Add columns to messages table."""
    columns = [
        ("participant_type", "VARCHAR", None),
        ("participant_name", "VARCHAR", None),
        ("image_data", "TEXT", None),
        ("image_media_type", "VARCHAR", None),
        ("anthropic_calls", "TEXT", None),
        ("provider", "VARCHAR", None),  # AI provider: 'claude' or 'codex'
    ]

    for col_name, col_type, default in columns:
        if not await _column_exists(conn, "messages", col_name):
            default_clause = f" DEFAULT {default}" if default else ""
            logger.info(f"  Adding {col_name} column to messages table...")
            await conn.execute(text(f"ALTER TABLE messages ADD COLUMN {col_name} {col_type}{default_clause}"))
            logger.info(f"  ✓ Added {col_name} column")


async def _migrate_rooms_table(conn):
    """Add columns and constraints to rooms table."""
    # Check if owner_id exists
    has_owner = await _column_exists(conn, "rooms", "owner_id")

    if not has_owner:
        logger.info("  Adding owner_id column to rooms table...")
        await conn.execute(text("ALTER TABLE rooms ADD COLUMN owner_id VARCHAR"))
        await conn.execute(text("UPDATE rooms SET owner_id = 'admin' WHERE owner_id IS NULL"))
        logger.info("  ✓ Added owner_id column")

    # Check for unique constraint
    if not await _index_exists(conn, "ux_rooms_owner_name"):
        logger.info("  Adding unique constraint on (owner_id, name)...")
        try:
            await conn.execute(text("CREATE UNIQUE INDEX ux_rooms_owner_name ON rooms(owner_id, name)"))
            logger.info("  ✓ Added unique constraint")
        except Exception as e:
            logger.warning(f"  Could not add unique constraint (may have duplicates): {e}")

    # Simple column additions
    simple_columns = [
        ("last_read_at", "TIMESTAMP", None),
        ("is_finished", "BOOLEAN", "FALSE"),
        ("default_provider", "VARCHAR", "'claude'"),  # Default AI provider for room
    ]

    for col_name, col_type, default in simple_columns:
        if not await _column_exists(conn, "rooms", col_name):
            default_clause = f" DEFAULT {default}" if default else ""
            logger.info(f"  Adding {col_name} column to rooms table...")
            await conn.execute(text(f"ALTER TABLE rooms ADD COLUMN {col_name} {col_type}{default_clause}"))
            logger.info(f"  ✓ Added {col_name} column")


async def _migrate_room_agents_table(conn):
    """Add columns to room_agents table."""
    if not await _column_exists(conn, "room_agents", "joined_at"):
        logger.info("  Adding joined_at column to room_agents table...")
        await conn.execute(text("ALTER TABLE room_agents ADD COLUMN joined_at TIMESTAMP"))
        logger.info("  ✓ Added joined_at column")


async def _migrate_room_agent_sessions_table(conn):
    """Add provider-specific session columns to room_agent_sessions table."""
    columns = [
        ("claude_session_id", "VARCHAR", None),  # Claude Agent SDK session ID
        ("codex_thread_id", "VARCHAR", None),  # Codex thread ID for conversation resume
    ]

    # Check if table exists first
    if is_sqlite():
        result = await conn.execute(
            text("SELECT COUNT(*) as count FROM sqlite_master WHERE type='table' AND name='room_agent_sessions'")
        )
    else:
        result = await conn.execute(
            text("""
                SELECT COUNT(*) as count
                FROM information_schema.tables
                WHERE table_name = 'room_agent_sessions'
            """)
        )
    if result.first().count == 0:
        return  # Table doesn't exist yet

    for col_name, col_type, default in columns:
        if not await _column_exists(conn, "room_agent_sessions", col_name):
            default_clause = f" DEFAULT {default}" if default else ""
            logger.info(f"  Adding {col_name} column to room_agent_sessions table...")
            await conn.execute(
                text(f"ALTER TABLE room_agent_sessions ADD COLUMN {col_name} {col_type}{default_clause}")
            )
            logger.info(f"  ✓ Added {col_name} column")

    # Migrate existing session_id to claude_session_id if not already migrated
    if await _column_exists(conn, "room_agent_sessions", "session_id"):
        # Copy session_id to claude_session_id where claude_session_id is NULL
        await conn.execute(
            text("""
                UPDATE room_agent_sessions
                SET claude_session_id = session_id
                WHERE claude_session_id IS NULL AND session_id IS NOT NULL
            """)
        )
        logger.info("  ✓ Migrated existing session_id values to claude_session_id")


async def _add_indexes(conn):
    """Add performance indexes."""
    indexes = [
        ("idx_message_room_timestamp", "messages", "(room_id, timestamp)"),
        ("ix_rooms_last_activity_at", "rooms", "(last_activity_at)"),
    ]

    for idx_name, table, columns in indexes:
        if not await _index_exists(conn, idx_name):
            logger.info(f"  Adding {idx_name} index...")
            await conn.execute(text(f"CREATE INDEX {idx_name} ON {table} {columns}"))
            logger.info(f"  ✓ Added {idx_name} index")


# =============================================================================
# Data Migrations
# =============================================================================


async def _sync_agents_from_filesystem(conn):
    """Sync agent data from filesystem (paths, groups, profile pics, system prompts)."""
    import sys
    from pathlib import Path

    from config import get_base_system_prompt, list_available_configs, parse_agent_config
    from core import get_settings
    from domain.agent_config import AgentConfigData
    from i18n.korean import format_with_particles

    logger.info("  Syncing agents from filesystem...")

    available_configs = list_available_configs()
    if not available_configs:
        return

    result = await conn.execute(text('SELECT id, name, config_file, "group", profile_pic FROM agents'))
    agents = result.fetchall()
    if not agents:
        return

    settings = get_settings()
    system_prompt_template = get_base_system_prompt()
    agents_dir = settings.agents_dir
    bundled_agents_dir = settings.bundled_agents_dir
    project_root = settings.project_root
    image_extensions = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"]
    common_names = ["profile", "avatar", "picture", "photo"]

    def resolve_agent_folder(config_file: str | None, agent_name: str) -> Path | None:
        """Resolve agent folder path, checking both user and bundled directories."""
        # Try user agents directory first
        if config_file:
            folder = project_root / config_file
            if folder.exists():
                return folder
        folder = agents_dir / agent_name
        if folder.exists():
            return folder

        # In bundled mode, try bundled agents as fallback
        if bundled_agents_dir and bundled_agents_dir.exists():
            if config_file:
                base_path = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else project_root  # type: ignore[attr-defined]
                folder = base_path / config_file
                if folder.exists():
                    return folder
            folder = bundled_agents_dir / agent_name
            if folder.exists():
                return folder

        return None

    for agent in agents:
        updates = {}

        # Sync path and group from filesystem
        if agent.name in available_configs:
            fs_config = available_configs[agent.name]
            if agent.config_file != fs_config["path"]:
                updates["config_file"] = fs_config["path"]
            if agent.group != fs_config["group"]:
                updates['"group"'] = fs_config["group"]

        # Sync profile pic - use config_file path to find agent folder (supports group folders)
        if not (agent.profile_pic and agent.profile_pic.startswith("data:")):
            agent_folder = resolve_agent_folder(agent.config_file, agent.name)

            found_pic = None
            if agent_folder and agent_folder.exists() and agent_folder.is_dir():
                # First try common profile pic names
                for name in common_names:
                    for ext in image_extensions:
                        if (agent_folder / f"{name}{ext}").exists():
                            found_pic = f"{name}{ext}"
                            break
                    if found_pic:
                        break
                # Fallback: find any image file in the folder
                if not found_pic:
                    for ext in image_extensions:
                        for file in agent_folder.glob(f"*{ext}"):
                            found_pic = file.name
                            break
                        if found_pic:
                            break
            if found_pic and found_pic != agent.profile_pic:
                updates["profile_pic"] = found_pic

        # Update system prompt
        formatted_prompt = format_with_particles(system_prompt_template, agent_name=agent.name)
        if agent.config_file:
            file_config = parse_agent_config(agent.config_file)
            if file_config:
                agent_config = AgentConfigData(
                    in_a_nutshell=file_config.in_a_nutshell,
                    characteristics=file_config.characteristics,
                    recent_events=file_config.recent_events,
                    long_term_memory_subtitles=file_config.long_term_memory_subtitles,
                )
                config_markdown = agent_config.to_system_prompt_markdown(agent.name)
                if config_markdown:
                    formatted_prompt += config_markdown
        updates["system_prompt"] = formatted_prompt

        # Fix critic agents
        if agent.name.lower() == "critic":
            updates["is_critic"] = True

        # Apply updates
        if updates:
            set_parts = []
            params = {"id": agent.id}
            for k, v in updates.items():
                param_name = k.replace('"', "")
                set_parts.append(f"{k} = :{param_name}")
                params[param_name] = v
            set_clause = ", ".join(set_parts)
            await conn.execute(text(f"UPDATE agents SET {set_clause} WHERE id = :id"), params)

    logger.info("  ✓ Agents synced from filesystem")
