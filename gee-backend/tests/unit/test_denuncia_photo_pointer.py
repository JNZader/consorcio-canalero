from types import SimpleNamespace

from app.main import _is_current_live_denuncia_photo, _parse_denuncia_photo_filename


DENUNCIA_ID = "11111111-1111-4111-8111-111111111111"
CURRENT_FILENAME = f"{DENUNCIA_ID}-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg"
OLD_FILENAME = f"{DENUNCIA_ID}-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.jpg"


def _denuncia(*, foto_url: str | None, deleted_at=None):
    return SimpleNamespace(foto_url=foto_url, deleted_at=deleted_at)


def test_current_live_denuncia_photo_matches_its_exact_pointer() -> None:
    row = _denuncia(foto_url=f"/uploads/denuncias/{CURRENT_FILENAME}")

    assert _is_current_live_denuncia_photo(row, CURRENT_FILENAME) is True


def test_previous_immutable_version_is_rejected() -> None:
    row = _denuncia(foto_url=f"/uploads/denuncias/{CURRENT_FILENAME}")

    assert _is_current_live_denuncia_photo(row, OLD_FILENAME) is False


def test_same_storage_key_with_wrong_extension_is_rejected() -> None:
    row = _denuncia(foto_url=f"/uploads/denuncias/{CURRENT_FILENAME}")
    wrong_extension = CURRENT_FILENAME.removesuffix(".jpg") + ".png"

    assert _is_current_live_denuncia_photo(row, wrong_extension) is False


def test_soft_deleted_denuncia_is_rejected_even_for_current_filename() -> None:
    row = _denuncia(
        foto_url=f"/uploads/denuncias/{CURRENT_FILENAME}",
        deleted_at="2026-07-18T12:00:00Z",
    )

    assert _is_current_live_denuncia_photo(row, CURRENT_FILENAME) is False


def test_missing_pointer_and_traversal_are_rejected() -> None:
    assert _is_current_live_denuncia_photo(_denuncia(foto_url=None), CURRENT_FILENAME) is False
    assert _parse_denuncia_photo_filename(f"../{CURRENT_FILENAME}") is None
