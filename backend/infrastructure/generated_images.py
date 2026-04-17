"""
Disk persistence for AI-generated images.

Generated images are stored on disk (under work_dir/generated_images) rather
than inlined as base64 in the database because they are typically 1-2 MB each.
Messages reference them via relative URL served by the /generated_images
static mount.
"""

import base64
import logging
import uuid
from pathlib import Path
from typing import Optional, Tuple

from core import get_settings

logger = logging.getLogger("GeneratedImages")

# Subdir under work_dir where generated images live
SUBDIR = "generated_images"

# Static URL prefix (must match the mount in app_factory.py)
URL_PREFIX = "/generated_images"


def get_storage_dir() -> Path:
    """Return the directory where generated images are persisted.

    Creates it if it doesn't exist.
    """
    directory = get_settings().work_dir / SUBDIR
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def save_generated_image(
    result: str,
    media_type: str = "image/png",
) -> Optional[Tuple[str, str]]:
    """Persist a generated image to disk.

    Args:
        result: The `result` field from Codex's ImageGenerationThreadItem.
                Typically a base64-encoded PNG. May also be an http(s) URL
                pointing to the image.
        media_type: MIME type of the image (default: image/png).

    Returns:
        (url, media_type) tuple where url is a path under /generated_images,
        or None if persistence failed. If the input is already a remote URL,
        it is returned as-is without persisting to disk.
    """
    if not result:
        return None

    if result.startswith(("http://", "https://")):
        return result, media_type

    ext = _ext_for_media_type(media_type)
    filename = f"{uuid.uuid4().hex}{ext}"

    try:
        raw = base64.b64decode(result, validate=False)
    except Exception as e:
        logger.error(f"Failed to decode generated image base64: {e}")
        return None

    try:
        path = get_storage_dir() / filename
        path.write_bytes(raw)
    except Exception as e:
        logger.error(f"Failed to write generated image to disk: {e}")
        return None

    url = f"{URL_PREFIX}/{filename}"
    logger.info(f"Saved generated image: {url} ({len(raw)} bytes)")
    return url, media_type


def _ext_for_media_type(media_type: str) -> str:
    mapping = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    return mapping.get(media_type.lower(), ".png")
