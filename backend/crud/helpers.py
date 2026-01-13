"""
Helper functions shared across CRUD operations.
"""

import base64
import logging
import re
from typing import Optional

from infrastructure.database import Message, Room
from core.settings import get_settings
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

logger = logging.getLogger("CRUD")


async def get_room_with_relationships(db: AsyncSession, room_id: int) -> Optional[Room]:
    """
    Helper to fetch a room with all relationships (agents and messages).
    Consolidates common query pattern used across multiple CRUD operations.
    """
    result = await db.execute(
        select(Room)
        .options(
            selectinload(Room.agents), selectinload(Room.messages).selectinload(Message.agent)
        )
        .where(Room.id == room_id)
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
        agents_dir = get_settings().agents_dir
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


def persist_agent_to_filesystem(
    agent_name: str,
    group: Optional[str],
    in_a_nutshell: str,
    characteristics: str,
    recent_events: Optional[str] = None,
    profile_pic_base64: Optional[str] = None,
) -> Optional[str]:
    """
    Persist a new agent's configuration to the filesystem.

    Creates the agent folder structure with required markdown files.
    If group is specified, creates under agents/group_{group}/.

    Args:
        agent_name: The agent's name (used as folder name)
        group: Optional group name (e.g., "슈타게" -> agents/group_슈타게/agent_name/)
        in_a_nutshell: Brief identity summary (required)
        characteristics: Personality traits (required)
        recent_events: Short-term recent context (optional)
        profile_pic_base64: Base64 data URL for profile picture (optional)

    Returns:
        The config_file path (relative to project root) if successful, None otherwise
    """
    settings = get_settings()
    agents_dir = settings.agents_dir

    # Determine the agent folder path
    if group:
        group_folder = agents_dir / f"group_{group}"
        agent_folder = group_folder / agent_name
    else:
        agent_folder = agents_dir / agent_name

    try:
        # Create agent folder (and parent group folder if needed)
        agent_folder.mkdir(parents=True, exist_ok=True)

        # Write in_a_nutshell.md (required)
        (agent_folder / "in_a_nutshell.md").write_text(
            in_a_nutshell.strip() if in_a_nutshell else "", encoding="utf-8"
        )

        # Write characteristics.md (required)
        (agent_folder / "characteristics.md").write_text(
            characteristics.strip() if characteristics else "", encoding="utf-8"
        )

        # Write recent_events.md (optional, create empty if not provided)
        (agent_folder / "recent_events.md").write_text(
            recent_events.strip() if recent_events else "", encoding="utf-8"
        )

        # Handle profile picture if provided
        if profile_pic_base64 and profile_pic_base64.startswith("data:image/"):
            save_base64_profile_pic(agent_name, profile_pic_base64)

        # Calculate relative path from project root
        relative_path = agent_folder.relative_to(settings.project_root)
        config_path = str(relative_path)

        logger.info(f"Created agent config folder: {config_path}")
        return config_path

    except Exception as e:
        logger.error(f"Failed to persist agent {agent_name} to filesystem: {e}")
        return None
