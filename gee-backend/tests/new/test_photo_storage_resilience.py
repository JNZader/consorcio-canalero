"""Failure-path coverage for durable denuncia photo replacement and deletion."""

from __future__ import annotations

import io
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image
from starlette.datastructures import Headers

from app.domains.denuncias.router import delete_my_denuncia, upload_denuncia_photo
from app.shared.storage import LocalPhotoStorage, make_denuncia_photo_key


def _png_bytes(color: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color=color).save(buffer, format="PNG")
    return buffer.getvalue()


def _upload(data: bytes, content_type: str = "image/png") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(data),
        filename="photo.png",
        headers=Headers({"content-type": content_type}),
    )


class _UploadDB:
    def __init__(
        self,
        denuncia,
        *,
        fail_commit: bool = False,
        fail_refresh: bool = False,
    ) -> None:
        self.denuncia = denuncia
        self.fail_commit = fail_commit
        self.fail_refresh = fail_refresh
        self.commit_calls = 0
        self.rollback_calls = 0

    def get(self, _model, _id):
        return self.denuncia

    def commit(self) -> None:
        self.commit_calls += 1
        if self.fail_commit:
            raise RuntimeError("database commit failed")

    def rollback(self) -> None:
        self.rollback_calls += 1

    def refresh(self, _obj) -> None:
        if self.fail_refresh:
            raise RuntimeError("refresh failed after durable commit")


async def _seed_old_photo(storage: LocalPhotoStorage, denuncia_id: uuid.UUID) -> tuple[str, bytes]:
    old_url = await storage.save(_upload(_png_bytes("red")), make_denuncia_photo_key(denuncia_id))
    old_path = storage._root / old_url.removeprefix("/uploads/")
    return old_url, old_path.read_bytes()


@pytest.mark.asyncio
async def test_invalid_replacement_bytes_leave_old_photo_untouched(tmp_path) -> None:
    storage = LocalPhotoStorage(root=str(tmp_path), public_base="/uploads")
    denuncia_id = uuid.uuid4()
    user_id = uuid.uuid4()
    old_url, old_bytes = await _seed_old_photo(storage, denuncia_id)
    denuncia = SimpleNamespace(user_id=user_id, foto_url=old_url)

    with pytest.raises(HTTPException) as exc_info:
        await upload_denuncia_photo(
            denuncia_id,
            _upload(b"not-an-image"),
            _UploadDB(denuncia),
            storage,
            SimpleNamespace(id=user_id),
        )

    assert exc_info.value.status_code == 400
    old_path = tmp_path / old_url.removeprefix("/uploads/")
    assert old_path.read_bytes() == old_bytes


@pytest.mark.asyncio
async def test_atomic_write_failure_leaves_old_photo_untouched(tmp_path, monkeypatch) -> None:
    storage = LocalPhotoStorage(root=str(tmp_path), public_base="/uploads")
    denuncia_id = uuid.uuid4()
    user_id = uuid.uuid4()
    old_url, old_bytes = await _seed_old_photo(storage, denuncia_id)
    denuncia = SimpleNamespace(user_id=user_id, foto_url=old_url)
    monkeypatch.setattr(
        "app.shared.storage.os.replace", MagicMock(side_effect=OSError("disk full"))
    )

    with pytest.raises(HTTPException) as exc_info:
        await upload_denuncia_photo(
            denuncia_id,
            _upload(_png_bytes("blue")),
            _UploadDB(denuncia),
            storage,
            SimpleNamespace(id=user_id),
        )

    assert exc_info.value.status_code == 503
    old_path = tmp_path / old_url.removeprefix("/uploads/")
    assert old_path.read_bytes() == old_bytes


@pytest.mark.asyncio
async def test_ambiguous_commit_failure_preserves_new_file_and_old_photo(tmp_path) -> None:
    storage = LocalPhotoStorage(root=str(tmp_path), public_base="/uploads")
    denuncia_id = uuid.uuid4()
    user_id = uuid.uuid4()
    old_url, old_bytes = await _seed_old_photo(storage, denuncia_id)
    denuncia = SimpleNamespace(user_id=user_id, foto_url=old_url)
    db = _UploadDB(denuncia, fail_commit=True)

    with pytest.raises(HTTPException) as exc_info:
        await upload_denuncia_photo(
            denuncia_id,
            _upload(_png_bytes("green")),
            db,
            storage,
            SimpleNamespace(id=user_id),
        )

    assert exc_info.value.status_code == 503
    assert db.rollback_calls == 1
    assert denuncia.foto_url == old_url
    old_path = tmp_path / old_url.removeprefix("/uploads/")
    assert old_path.read_bytes() == old_bytes
    # A commit exception can occur after PostgreSQL made the new pointer durable.
    # Keep the new file as an orphan rather than risk a durable pointer to nothing.
    assert len(list((tmp_path / "denuncias").glob(f"{denuncia_id}-*"))) == 1


@pytest.mark.asyncio
async def test_refresh_failure_after_commit_never_deletes_committed_photo(tmp_path) -> None:
    storage = LocalPhotoStorage(root=str(tmp_path), public_base="/uploads")
    denuncia_id = uuid.uuid4()
    user_id = uuid.uuid4()
    old_url, old_bytes = await _seed_old_photo(storage, denuncia_id)
    denuncia = SimpleNamespace(user_id=user_id, foto_url=old_url)
    db = _UploadDB(denuncia, fail_refresh=True)

    with pytest.raises(HTTPException) as exc_info:
        await upload_denuncia_photo(
            denuncia_id,
            _upload(_png_bytes("blue")),
            db,
            storage,
            SimpleNamespace(id=user_id),
        )

    assert exc_info.value.status_code == 503
    assert db.commit_calls == 1
    assert db.rollback_calls == 0
    new_files = list((tmp_path / "denuncias").glob(f"{denuncia_id}-*"))
    assert len(new_files) == 1
    assert new_files[0].is_file()
    old_path = tmp_path / old_url.removeprefix("/uploads/")
    assert old_path.read_bytes() == old_bytes


@pytest.mark.asyncio
async def test_delete_failure_preserves_photo_pointer_and_soft_delete_state() -> None:
    denuncia_id = uuid.uuid4()
    user_id = uuid.uuid4()
    denuncia = SimpleNamespace(
        id=denuncia_id,
        user_id=user_id,
        foto_url=f"/uploads/denuncias/{denuncia_id}.png",
        deleted_at=None,
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = denuncia
    db = MagicMock()
    db.execute.return_value = result
    storage = SimpleNamespace(delete=AsyncMock(side_effect=OSError("permission denied")))

    with pytest.raises(HTTPException) as exc_info:
        await delete_my_denuncia(
            denuncia_id,
            db,
            storage,
            SimpleNamespace(id=user_id),
        )

    assert exc_info.value.status_code == 503
    assert denuncia.foto_url is not None
    assert denuncia.deleted_at is None
    db.commit.assert_not_called()
