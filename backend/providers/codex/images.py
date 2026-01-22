"""
Image handling for Codex App Server.

Codex App Server supports images via:
- {"type": "image", "url": "https://..."} - remote URL
- {"type": "image", "url": "data:image/png;base64,..."} - data URL
- {"type": "localImage", "path": "/tmp/..."} - local file (currently broken)

We use data URLs since localImage stopped working.

Note: Images are stored as PNG at message creation time for Codex rooms
(see infrastructure/images.py for provider-aware compression).

See: https://developers.openai.com/codex/app-server
"""

import logging
from dataclasses import dataclass
from typing import Dict, List

logger = logging.getLogger("CodexImages")


@dataclass
class CodexImageManager:
    """Converts content blocks to Codex input items.

    Usage:
        manager = CodexImageManager()
        input_items = manager.process_content_blocks(content_blocks)
        # ... send to Codex ...
    """

    def process_content_blocks(self, content_blocks: List[Dict]) -> List[Dict]:
        """Convert content blocks with base64 images to Codex input items.

        Takes Claude-style content blocks and converts them to Codex input items:
        - Text blocks: {"type": "text", "text": "..."}
        - Image blocks: {"type": "image", "url": "data:..."}

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

                    # Use data URL with image type (Codex docs: {"type": "image", "url": "..."})
                    data_url = f"data:{media_type};base64,{data}"
                    input_items.append({"type": "image", "url": data_url})
                    logger.debug(f"Added image: {media_type}, {len(data)} chars base64")

        return input_items

    def cleanup(self) -> int:
        """No-op for backwards compatibility. Returns 0."""
        return 0

    @property
    def temp_file_count(self) -> int:
        """Returns 0 for backwards compatibility."""
        return 0
