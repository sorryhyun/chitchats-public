"""Agent management routes for updates, configuration, and profile pictures."""

import hashlib
import re
from pathlib import Path
from typing import Optional

import crud
import schemas
from config import list_available_configs
from core import require_admin
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from infrastructure.database import get_db
from infrastructure.images import resize_image
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

# In-memory cache for resized images: (path, size) -> (bytes, etag)
_resize_cache: dict[tuple[str, int], tuple[bytes, str]] = {}

# Pattern for valid agent names: alphanumeric, underscores, hyphens, and common unicode chars
VALID_AGENT_NAME_PATTERN = re.compile(r"^[\w\-\.\s\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]+$")


@router.patch("/{agent_id}", response_model=schemas.Agent, dependencies=[Depends(require_admin)])
async def update_agent(agent_id: int, agent_update: schemas.AgentUpdate, db: AsyncSession = Depends(get_db)):
    """Update an agent's persona, memory, or recent events. (Admin only)"""
    agent = await crud.update_agent(db, agent_id, agent_update)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/{agent_id}/reload", response_model=schemas.Agent, dependencies=[Depends(require_admin)])
async def reload_agent(agent_id: int, db: AsyncSession = Depends(get_db)):
    """Reload an agent's data from its config file. (Admin only)"""
    try:
        agent = await crud.reload_agent_from_config(db, agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        return agent
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/configs")
async def list_agent_configs():
    """List all available agent configuration files."""
    return {"configs": list_available_configs()}


@router.get("/{agent_name}/profile-pic")
async def get_agent_profile_pic(
    agent_name: str,
    size: Optional[int] = Query(None, ge=16, le=1024, description="Target size in pixels"),
):
    """
    Serve the profile picture for an agent from the filesystem.

    Args:
        agent_name: Name of the agent
        size: Optional target size in pixels (16-1024). Image will be resized to fit.

    Looks for profile pictures in the agent's config folder:
    - agents/{agent_name}/profile.{png,jpg,jpeg,gif,webp,svg}
    - agents/group_*/agent_name}/profile.{png,jpg,jpeg,gif,webp,svg}
    - agents/{agent_name}/avatar.{png,jpg,jpeg,gif,webp,svg}
    - agents/{agent_name}/*.{png,jpg,jpeg,gif,webp,svg}

    For legacy single-file configs:
    - agents/{agent_name}.{png,jpg,jpeg,gif,webp,svg}
    """
    import sys

    # Validate agent name to prevent path traversal attacks
    if not VALID_AGENT_NAME_PATTERN.match(agent_name) or ".." in agent_name:
        raise HTTPException(status_code=400, detail="Invalid agent name")

    # Get the agents directory
    if getattr(sys, "frozen", False):
        # Bundled mode: agents are in working directory (copied from bundle on first run)
        agents_dir = Path.cwd() / "agents"
        # Also try the bundled location as fallback
        bundled_agents_dir = Path(sys._MEIPASS) / "agents"
    else:
        # Development mode: agents are in project root
        backend_dir = Path(__file__).parent.parent
        project_root = backend_dir.parent
        agents_dir = project_root / "agents"
        bundled_agents_dir = None

    # Common image extensions
    image_extensions = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"]

    def find_profile_pic_in_folder(folder: Path):
        """Helper function to find profile picture in a folder."""
        if not folder.is_dir():
            return None

        # Try common profile pic names
        common_names = ["profile", "avatar", "picture", "photo"]
        for name in common_names:
            for ext in image_extensions:
                pic_path = folder / f"{name}{ext}"
                if pic_path.exists():
                    return pic_path

        # If no common name found, look for any image file
        for ext in image_extensions:
            for file in folder.glob(f"*{ext}"):
                return file

        return None

    # Cache headers for static profile pictures (1 hour cache, revalidate after)
    cache_headers = {
        "Cache-Control": "public, max-age=3600, must-revalidate",
    }

    def serve_image(pic_path: Path):
        """Helper to serve an image, optionally resized."""
        if size is None:
            return FileResponse(pic_path, headers=cache_headers)

        # Check in-memory cache first
        cache_key = (str(pic_path), size)
        if cache_key in _resize_cache:
            cached_bytes, etag = _resize_cache[cache_key]
            # Determine media type from extension
            suffix = pic_path.suffix.lower()
            media_types = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".webp": "image/webp",
                ".svg": "image/svg+xml",
            }
            media_type = media_types.get(suffix, "application/octet-stream")
            return Response(
                content=cached_bytes,
                media_type=media_type,
                headers={**cache_headers, "ETag": etag},
            )

        # Read and resize the image
        image_bytes = pic_path.read_bytes()
        resized_bytes = resize_image(image_bytes, size)

        # Generate ETag from content hash
        etag = hashlib.md5(resized_bytes).hexdigest()

        # Cache the resized image (limit cache size by clearing if too large)
        if len(_resize_cache) > 1000:
            _resize_cache.clear()
        _resize_cache[cache_key] = (resized_bytes, etag)

        # Determine media type from extension
        suffix = pic_path.suffix.lower()
        media_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
        }
        media_type = media_types.get(suffix, "application/octet-stream")

        return Response(
            content=resized_bytes,
            media_type=media_type,
            headers={**cache_headers, "ETag": etag},
        )

    # First, try direct agent folder
    agent_folder = agents_dir / agent_name
    pic_path = find_profile_pic_in_folder(agent_folder)
    if pic_path:
        return serve_image(pic_path)

    # Try group folders (group_*/)
    for group_folder in agents_dir.glob("group_*"):
        if group_folder.is_dir():
            agent_in_group = group_folder / agent_name
            pic_path = find_profile_pic_in_folder(agent_in_group)
            if pic_path:
                return serve_image(pic_path)

    # Try legacy format (agent_name.{ext} in agents/ directory)
    for ext in image_extensions:
        pic_path = agents_dir / f"{agent_name}{ext}"
        if pic_path.exists():
            return serve_image(pic_path)

    # In bundled mode, also check the bundled agents directory as fallback
    if bundled_agents_dir and bundled_agents_dir.exists():
        # Try direct agent folder in bundled location
        agent_folder = bundled_agents_dir / agent_name
        pic_path = find_profile_pic_in_folder(agent_folder)
        if pic_path:
            return serve_image(pic_path)

        # Try group folders in bundled location
        for group_folder in bundled_agents_dir.glob("group_*"):
            if group_folder.is_dir():
                agent_in_group = group_folder / agent_name
                pic_path = find_profile_pic_in_folder(agent_in_group)
                if pic_path:
                    return serve_image(pic_path)

    # No profile picture found
    raise HTTPException(status_code=404, detail="Profile picture not found")
