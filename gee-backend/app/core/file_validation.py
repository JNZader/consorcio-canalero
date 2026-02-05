"""
File validation utilities.
Validates uploaded files using magic bytes to prevent spoofing.
"""

from typing import Dict, Optional, Tuple


# Magic bytes signatures for common image formats
# Format: (magic_bytes, offset, mime_type)
MAGIC_SIGNATURES: Dict[str, Tuple[bytes, int, str]] = {
    "jpeg": (b"\xFF\xD8\xFF", 0, "image/jpeg"),
    "png": (b"\x89PNG\r\n\x1a\n", 0, "image/png"),
    "webp": (b"WEBP", 8, "image/webp"),  # RIFF header + 4 bytes size, then WEBP
    "gif": (b"GIF8", 0, "image/gif"),
    "pdf": (b"%PDF", 0, "application/pdf"),
}

# Additional check for RIFF container (WebP is a RIFF format)
RIFF_HEADER = b"RIFF"


def get_image_type_from_magic(content: bytes) -> Optional[str]:
    """
    Detect image type from magic bytes.

    Args:
        content: File content as bytes

    Returns:
        MIME type if recognized, None otherwise
    """
    if len(content) < 12:
        return None

    # Check JPEG
    if content[:3] == MAGIC_SIGNATURES["jpeg"][0]:
        return "image/jpeg"

    # Check PNG
    if content[:8] == MAGIC_SIGNATURES["png"][0]:
        return "image/png"

    # Check WebP (RIFF container with WEBP format)
    if content[:4] == RIFF_HEADER and content[8:12] == MAGIC_SIGNATURES["webp"][0]:
        return "image/webp"

    # Check GIF
    if content[:4] == MAGIC_SIGNATURES["gif"][0]:
        return "image/gif"

    return None


def validate_image_magic_bytes(content: bytes, claimed_type: str) -> Tuple[bool, str]:
    """
    Validate that file content matches the claimed MIME type.

    Args:
        content: File content as bytes
        claimed_type: The claimed MIME type (from Content-Type header)

    Returns:
        Tuple of (is_valid, actual_type_or_error_message)
    """
    if len(content) < 12:
        return False, "Archivo muy pequeno para validar"

    actual_type = get_image_type_from_magic(content)

    if actual_type is None:
        return False, "Tipo de archivo no reconocido o invalido"

    # Normalize JPEG type
    normalized_claimed = claimed_type.lower().replace("image/jpg", "image/jpeg")

    if actual_type != normalized_claimed:
        return False, f"El contenido del archivo no coincide con el tipo declarado"

    return True, actual_type


def is_valid_image(content: bytes, allowed_types: set) -> Tuple[bool, Optional[str]]:
    """
    Check if file content is a valid image of an allowed type.

    Args:
        content: File content as bytes
        allowed_types: Set of allowed MIME types

    Returns:
        Tuple of (is_valid, detected_mime_type_or_none)
    """
    detected_type = get_image_type_from_magic(content)

    if detected_type is None:
        return False, None

    if detected_type not in allowed_types:
        return False, detected_type

    return True, detected_type
