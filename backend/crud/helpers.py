"""
Helper functions shared across CRUD operations.
"""

import base64
import logging
import re
from typing import Optional

import models
from core.paths import get_agents_dir
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

logger = logging.getLogger("CRUD")


async def get_room_with_relationships(db: AsyncSession, room_id: int) -> Optional[models.Room]:
    """
    Helper to fetch a room with all relationships (agents and messages).
    Consolidates common query pattern used across multiple CRUD operations.
    """
    result = await db.execute(
        select(models.Room)
        .options(
            selectinload(models.Room.agents), selectinload(models.Room.messages).selectinload(models.Message.agent)
        )
        .where(models.Room.id == room_id)
    )
    return result.scalar_one_or_none()


def merge_agent_configs(provided_config, file_config):
    """
    Merge provided config values with file config values.
    Provided values take precedence over file values.

    Args:
        provided_config: AgentConfigData with user-provided values
        file_config: AgentConfigData from config file (or None)

    Returns:
        AgentConfigData with merged values
    """
    from domain.agent_config import AgentConfigData

    # Convert to dicts for merging
    provided_dict = {
        "in_a_nutshell": provided_config.in_a_nutshell or "",
        "characteristics": provided_config.characteristics or "",
        "recent_events": provided_config.recent_events or "",
        "profile_pic": provided_config.profile_pic or "",
    }

    file_dict = {}
    if file_config:
        file_dict = {
            "in_a_nutshell": file_config.in_a_nutshell or "",
            "characteristics": file_config.characteristics or "",
            "recent_events": file_config.recent_events or "",
            "profile_pic": file_config.profile_pic or "",
        }

    # Use the better merging logic: strip whitespace and prefer non-empty values
    merged = {}
    for field in provided_dict.keys():
        provided_val = provided_dict.get(field, "").strip()
        file_val = file_dict.get(field, "").strip()
        merged[field] = provided_val if provided_val else file_val

    return AgentConfigData(**merged)


def bool_to_sqlite(value: bool) -> int:
    """
    Convert Python boolean to SQLite integer (0 or 1).
    SQLite doesn't have a native boolean type, so booleans are stored as integers.

    Args:
        value: Boolean value to convert

    Returns:
        1 if True, 0 if False
    """
    return 1 if value else 0


def save_base64_profile_pic(agent_name: str, base64_data: str) -> bool:
    """
    Save a base64-encoded profile picture to the filesystem.

    Args:
        agent_name: The agent's name
        base64_data: Base64 data URL (e.g., "data:image/png;base64,...")

    Returns:
        True if saved successfully, False otherwise
    """
    # Match data URL format: data:image/{type};base64,{data}
    match = re.match(r"data:image/(\w+);base64,(.+)", base64_data)
    if not match:
        logger.warning(f"Invalid base64 data URL format for agent {agent_name}")
        return False

    image_type = match.group(1).lower()
    encoded_data = match.group(2)

    # Map common MIME types to file extensions
    ext_map = {
        "png": ".png",
        "jpg": ".jpg",
        "jpeg": ".jpg",
        "gif": ".gif",
        "webp": ".webp",
        "svg+xml": ".svg",
        "svg": ".svg",
    }

    file_ext = ext_map.get(image_type, ".png")

    try:
        # Decode base64 data
        image_data = base64.b64decode(encoded_data)

        # Determine file path (handles both dev and frozen exe modes)
        agents_dir = get_agents_dir()
        agent_folder = agents_dir / agent_name

        # Create agent folder if it doesn't exist
        agent_folder.mkdir(parents=True, exist_ok=True)

        # Save to profile.{ext}
        profile_path = agent_folder / f"profile{file_ext}"

        # Remove any existing profile pictures with different extensions
        for old_file in agent_folder.glob("profile.*"):
            if old_file != profile_path:
                old_file.unlink()

        # Write the new profile picture
        profile_path.write_bytes(image_data)
        logger.info(f"Saved profile picture for {agent_name} to {profile_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to save profile picture for {agent_name}: {e}")
        return False
