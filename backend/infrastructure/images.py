"""
Image utilities for compression.

Converts images to efficient formats for better compression.
- WebP: 25-35% smaller than JPEG/PNG (used for Claude provider)
- PNG: Lossless compression (used for Codex provider which doesn't support WebP)
"""

import base64
import io
import os
from typing import Literal, Tuple

from PIL import Image

# WebP quality (1-100)
WEBP_QUALITY = int(os.getenv("IMAGE_WEBP_QUALITY", "95"))

# Target format based on provider support
TargetFormat = Literal["webp", "png"]


def compress_image_base64(
    base64_data: str,
    media_type: str,
    target_format: TargetFormat = "webp",
) -> Tuple[str, str]:
    """
    Convert a base64-encoded image to target format.

    Args:
        base64_data: Base64-encoded image data (without data URL prefix)
        media_type: MIME type of the image (e.g., 'image/png', 'image/jpeg')
        target_format: Target format - 'webp' (default) or 'png'
                       Use 'png' for providers that don't support webp (e.g., Codex)

    Returns:
        Tuple of (compressed_base64_data, media_type)

    Note:
        If conversion fails, returns original data unchanged.
    """
    target_media_type = f"image/{target_format}"

    # Skip if already in target format
    if media_type == target_media_type:
        return base64_data, media_type

    try:
        # Decode base64 to bytes
        image_bytes = base64.b64decode(base64_data)

        # Open image with Pillow
        image = Image.open(io.BytesIO(image_bytes))

        # Handle palette mode (P) for transparency
        if image.mode == "P":
            image = image.convert("RGBA")

        # Convert to target format
        output_buffer = io.BytesIO()

        if target_format == "webp":
            image.save(
                output_buffer,
                format="WEBP",
                quality=WEBP_QUALITY,
                method=6,  # Better compression
            )
        else:  # png
            image.save(
                output_buffer,
                format="PNG",
                optimize=True,
            )

        compressed_bytes = output_buffer.getvalue()

        # Encode back to base64
        compressed_base64 = base64.b64encode(compressed_bytes).decode("utf-8")

        return compressed_base64, target_media_type

    except Exception as e:
        # If conversion fails, return original
        print(f"Image conversion to {target_format} failed: {e}")
        return base64_data, media_type


def get_target_format_for_provider(provider: str) -> TargetFormat:
    """
    Get the appropriate target image format for a provider.

    Args:
        provider: Provider name ('claude', 'codex', etc.)

    Returns:
        Target format ('webp' or 'png')
    """
    # Codex doesn't support webp
    if provider == "codex":
        return "png"
    # Default to webp for better compression
    return "webp"


def resize_image(image_bytes: bytes, target_size: int) -> bytes:
    """
    Resize an image to a target size while maintaining aspect ratio.

    The image is scaled down to fit within a target_size x target_size box.
    If the image is smaller than target_size, it is returned unchanged.

    Args:
        image_bytes: Raw image bytes
        target_size: Target size in pixels (width or height, whichever is larger)

    Returns:
        Resized image bytes in the same format
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        original_format = image.format or "PNG"

        # Get current dimensions
        width, height = image.size

        # Calculate new dimensions maintaining aspect ratio
        max_dim = max(width, height)
        if max_dim <= target_size:
            # Image is already smaller than target
            return image_bytes

        # Scale factor to fit in target_size box
        scale = target_size / max_dim
        new_width = int(width * scale)
        new_height = int(height * scale)

        # Resize with high-quality resampling
        resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Save to bytes
        output_buffer = io.BytesIO()
        save_kwargs = {}
        if original_format.upper() in ("JPEG", "JPG"):
            save_kwargs["quality"] = 95
        elif original_format.upper() == "PNG":
            save_kwargs["optimize"] = True
        elif original_format.upper() == "WEBP":
            save_kwargs["quality"] = WEBP_QUALITY

        resized.save(output_buffer, format=original_format, **save_kwargs)
        return output_buffer.getvalue()

    except Exception as e:
        print(f"Image resize failed: {e}")
        return image_bytes
