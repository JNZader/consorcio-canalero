from __future__ import annotations

import os
import uuid
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote

import pytest

# app.main creates the configured upload root during import. Keep that side
# effect in a writable test-only location for this unit-test module.
os.environ.setdefault("UPLOADS_ROOT", "/tmp/consorcio-codeql-photo-tests")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")
os.environ.setdefault("DEBUG", "true")

from app import main  # noqa: E402
from app.auth.models import UserRole  # noqa: E402


PHOTO_ID = uuid.UUID("abcdef12-3456-7890-abcd-ef1234567890")
PHOTO_SUFFIX = "ABCDEF0123456789ABCDEF0123456789"
CANONICAL_SUFFIX = f"-{int(PHOTO_SUFFIX, 16):032x}"


@pytest.mark.parametrize(
    "filename",
    [
        f"../{PHOTO_ID}.jpg",
        f"..\\{PHOTO_ID}.jpg",
        f"%2e%2e%2f{PHOTO_ID}.jpg",
        unquote(f"%2e%2e%2f{PHOTO_ID}.jpg"),
        f"{PHOTO_ID}.jpg\n",
        f"{PHOTO_ID}-{'a' * 31}.jpg",
        f"{PHOTO_ID}-{'a' * 33}.jpg",
        f"{PHOTO_ID}-{'g' * 32}.jpg",
    ],
)
def test_filename_parser_rejects_traversal_encoded_and_final_lf(filename: str):
    assert main._parse_denuncia_photo_filename(filename) is None


def test_filename_parser_canonicalizes_uuid_suffix_and_extension():
    without_suffix = main._parse_denuncia_photo_filename(f"{str(PHOTO_ID).upper()}.JPEG")
    with_suffix = main._parse_denuncia_photo_filename(
        f"{str(PHOTO_ID).upper()}-{PHOTO_SUFFIX}.WEBP"
    )

    assert without_suffix == (PHOTO_ID, "", "jpeg")
    assert with_suffix == (PHOTO_ID, CANONICAL_SUFFIX, "webp")


def test_confined_reader_accepts_a_canonical_regular_file(tmp_path: Path):
    uploads_root = tmp_path / "uploads"
    photo_root = uploads_root / "denuncias"
    photo_root.mkdir(parents=True)
    canonical_filename = f"{PHOTO_ID}{CANONICAL_SUFFIX}.jpg"
    expected = b"canonical-photo"
    (photo_root / canonical_filename).write_bytes(expected)

    assert main._read_denuncia_photo_bytes(str(uploads_root), canonical_filename) == expected


def test_confined_reader_rejects_a_symlink_even_when_target_stays_inside_root(tmp_path: Path):
    uploads_root = tmp_path / "uploads"
    photo_root = uploads_root / "denuncias"
    photo_root.mkdir(parents=True)
    target = photo_root / f"{uuid.uuid4()}.jpg"
    target.write_bytes(b"different-photo")
    link = photo_root / f"{PHOTO_ID}.jpg"
    try:
        link.symlink_to(target.name)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlinks are not available on this platform: {exc}")

    assert main._read_denuncia_photo_bytes(str(uploads_root), link.name) is None


def _install_fake_db(monkeypatch: pytest.MonkeyPatch, denuncia: SimpleNamespace) -> None:
    class FakeDb:
        def get(self, _model, denuncia_id):
            assert denuncia_id == denuncia.id
            return denuncia

    def fake_get_db():
        yield FakeDb()

    monkeypatch.setattr("app.db.session.get_db", fake_get_db)


@pytest.mark.asyncio
async def test_owner_reads_current_canonical_file_from_uppercase_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    uploads_root = tmp_path / "uploads"
    photo_root = uploads_root / "denuncias"
    photo_root.mkdir(parents=True)
    canonical_filename = f"{PHOTO_ID}{CANONICAL_SUFFIX}.jpeg"
    (photo_root / canonical_filename).write_bytes(b"canonical-photo")
    owner_id = uuid.uuid4()
    denuncia = SimpleNamespace(
        id=PHOTO_ID,
        user_id=owner_id,
        foto_url=f"/uploads/denuncias/{canonical_filename}",
        deleted_at=None,
    )
    _install_fake_db(monkeypatch, denuncia)
    monkeypatch.setattr(main.settings, "uploads_root", str(uploads_root))
    user = SimpleNamespace(id=owner_id, role=UserRole.CIUDADANO)

    response = await main.get_denuncia_photo(
        f"{str(PHOTO_ID).upper()}-{PHOTO_SUFFIX}.JPEG",
        request=None,
        user=user,
    )

    assert response.status_code == 200
    assert response.body == b"canonical-photo"
    assert response.media_type == "image/jpeg"


@pytest.mark.asyncio
async def test_authorization_happens_before_filesystem_io(
    monkeypatch: pytest.MonkeyPatch,
):
    owner_id = uuid.uuid4()
    denuncia = SimpleNamespace(
        id=PHOTO_ID,
        user_id=owner_id,
        foto_url=f"/uploads/denuncias/{PHOTO_ID}.jpg",
        deleted_at=None,
    )
    _install_fake_db(monkeypatch, denuncia)
    user = SimpleNamespace(id=uuid.uuid4(), role=UserRole.CIUDADANO)
    filesystem_called = False

    def fail_if_called(_uploads_root: str, _canonical_filename: str):
        nonlocal filesystem_called
        filesystem_called = True
        raise AssertionError("filesystem access must happen only after authorization")

    monkeypatch.setattr(main, "_read_denuncia_photo_bytes", fail_if_called)

    response = await main.get_denuncia_photo(
        f"{PHOTO_ID}.jpg",
        request=None,
        user=user,
    )

    assert response.status_code == 404
    assert filesystem_called is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("requested_filename", "deleted_at"),
    [
        (f"{PHOTO_ID}-{'1' * 32}.jpg", None),
        (f"{PHOTO_ID}{CANONICAL_SUFFIX}.jpg", "2026-07-18T12:00:00Z"),
    ],
)
async def test_stale_or_deleted_photo_is_rejected_before_filesystem_io(
    requested_filename: str,
    deleted_at: str | None,
    monkeypatch: pytest.MonkeyPatch,
):
    current_filename = f"{PHOTO_ID}{CANONICAL_SUFFIX}.jpg"
    owner_id = uuid.uuid4()
    denuncia = SimpleNamespace(
        id=PHOTO_ID,
        user_id=owner_id,
        foto_url=f"/uploads/denuncias/{current_filename}",
        deleted_at=deleted_at,
    )
    _install_fake_db(monkeypatch, denuncia)
    user = SimpleNamespace(id=owner_id, role=UserRole.CIUDADANO)
    filesystem_called = False

    def fail_if_called(_uploads_root: str, _canonical_filename: str):
        nonlocal filesystem_called
        filesystem_called = True
        raise AssertionError("stale or deleted photos must not reach storage")

    monkeypatch.setattr(main, "_read_denuncia_photo_bytes", fail_if_called)

    response = await main.get_denuncia_photo(
        requested_filename,
        request=None,
        user=user,
    )

    assert response.status_code == 404
    assert filesystem_called is False
