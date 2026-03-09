from app.core.file_validation import (
    get_image_type_from_magic,
    is_valid_image,
    validate_image_magic_bytes,
)


def test_get_image_type_from_magic_detects_common_image_formats():
    jpeg = b"\xff\xd8\xff" + b"0" * 20
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
    webp = b"RIFF" + b"1234" + b"WEBP" + b"0" * 20
    gif = b"GIF89a" + b"0" * 20

    assert get_image_type_from_magic(jpeg) == "image/jpeg"
    assert get_image_type_from_magic(png) == "image/png"
    assert get_image_type_from_magic(webp) == "image/webp"
    assert get_image_type_from_magic(gif) == "image/gif"


def test_get_image_type_from_magic_returns_none_for_unknown_or_short_files():
    assert get_image_type_from_magic(b"\x89PNG") is None
    assert get_image_type_from_magic(b"NOT_AN_IMAGE_FILE") is None


def test_validate_image_magic_bytes_handles_validation_errors_and_jpg_alias():
    ok, detected = validate_image_magic_bytes(b"short", "image/jpeg")
    assert ok is False
    assert "pequeno" in detected

    ok, message = validate_image_magic_bytes(b"INVALID_CONTENT_123456", "image/png")
    assert ok is False
    assert "no reconocido" in message

    jpeg = b"\xff\xd8\xff" + b"0" * 20
    ok, message = validate_image_magic_bytes(jpeg, "image/png")
    assert ok is False
    assert "no coincide" in message

    ok, detected = validate_image_magic_bytes(jpeg, "image/jpg")
    assert ok is True
    assert detected == "image/jpeg"


def test_is_valid_image_checks_allowed_types_and_detected_type_feedback():
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 20

    assert is_valid_image(png, {"image/png", "image/jpeg"}) == (True, "image/png")
    assert is_valid_image(png, {"image/jpeg"}) == (False, "image/png")
    assert is_valid_image(b"NOT_IMAGE_CONTENT", {"image/png"}) == (False, None)
