"""
Image handling for Codex App Server.

Codex App Server supports images via:
- Remote URL: {"type": "image", "url": "https://..."}
- Local file: {"type": "localImage", "path": "/tmp/screenshot.png"}

Since ChitChats receives images as base64 data, we need to:
1. Save base64 images to temporary files
2. Pass file paths to Codex using localImage type
3. Clean up temp files after the turn completes

Note: Images are saved as PNG at message creation time for Codex rooms
(see infrastructure/images.py for provider-aware compression).

See: https://developers.openai.com/codex/app-server
"""

import base64
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("CodexImages")

# Map media types to file extensions
MEDIA_TYPE_TO_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
}


@dataclass
class CodexImageManager:
    """Manages temporary image files for Codex App Server.

    Creates temp files from base64 image data and tracks them for cleanup.
    Each turn should use a separate manager instance for proper cleanup.

    Usage:
        manager = CodexImageManager()
        input_items = manager.process_content_blocks(content_blocks)
        # ... send to Codex ...
        manager.cleanup()  # Remove temp files
    """

    temp_dir: Optional[str] = None
    _temp_files: List[Path] = field(default_factory=list)

    def __post_init__(self):
        """Initialize temp directory."""
        if self.temp_dir is None:
            self.temp_dir = tempfile.gettempdir()

    def save_base64_image(self, data: str, media_type: str) -> Optional[str]:
        """Save base64 image data to a temporary file.

        Args:
            data: Base64-encoded image data (without data URL prefix)
            media_type: MIME type (e.g., "image/png", "image/jpeg")

        Returns:
            Path to the temporary file, or None if failed
        """
        ext = MEDIA_TYPE_TO_EXT.get(media_type, ".png")

        try:
            # Decode base64 data
            image_bytes = base64.b64decode(data)

            # Create temp file
            fd, path = tempfile.mkstemp(suffix=ext, prefix="codex_img_", dir=self.temp_dir)

            try:
                os.write(fd, image_bytes)
            finally:
                os.close(fd)

            temp_path = Path(path)
            self._temp_files.append(temp_path)

            logger.debug(f"Saved image to temp file: {path} ({len(image_bytes)} bytes)")
            # Use as_posix() for cross-platform compatibility (Windows accepts forward slashes)
            return temp_path.as_posix()

        except Exception as e:
            logger.error(f"Failed to save image to temp file: {e}")
            return None

    def process_content_blocks(self, content_blocks: List[Dict]) -> List[Dict]:
        """Convert content blocks with base64 images to Codex input items.

        Takes Claude-style content blocks and converts them to Codex input items:
        - Text blocks: {"type": "text", "text": "..."}
        - Image blocks: {"type": "localImage", "path": "/tmp/..."}

        Args:
            content_blocks: List of content blocks from conversation context
                [{"type": "text", "text": "..."},
                 {"type": "image", "source": {"type": "base64", "data": "...", "media_type": "..."}}]

        Returns:
            List of Codex input items
        """
        input_items: List[Dict] = []

        for block in content_blocks:
            block_type = block.get("type")

            if block_type == "text":
                text = block.get("text", "")
                if text:
                    input_items.append({"type": "text", "text": text})

            elif block_type == "image":
                source = block.get("source", {})
                if source.get("type") == "base64":
                    data = source.get("data", "")
                    media_type = source.get("media_type", "image/png")

                    path = self.save_base64_image(data, media_type)
                    if path:
                        input_items.append({"type": "localImage", "path": path})
                    else:
                        logger.warning("Failed to save image, skipping")

        return input_items

    def cleanup(self) -> int:
        """Remove all temporary files created by this manager.

        Returns:
            Number of files successfully removed
        """
        removed = 0
        for path in self._temp_files:
            try:
                if path.exists():
                    path.unlink()
                    logger.debug(f"Removed temp file: {path}")
                    removed += 1
            except Exception as e:
                logger.warning(f"Failed to remove temp file {path}: {e}")

        self._temp_files.clear()
        return removed

    @property
    def temp_file_count(self) -> int:
        """Get the number of temp files being tracked."""
        return len(self._temp_files)

    def __del__(self):
        """Cleanup on deletion (fallback)."""
        if self._temp_files:
            logger.warning(f"CodexImageManager destroyed with {len(self._temp_files)} temp files - cleaning up")
            self.cleanup()
