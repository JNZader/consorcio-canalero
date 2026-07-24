"""Failure-path coverage for durable denuncia photo replacement and deletion."""

from __future__ import annotations

import importlib
import io
import os
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image
from starlette.datastructures import Headers

from app.auth.cleanup_tasks import (
    ORPHANED_DENUNCIA_PHOTO_GRACE,
    reconcile_orphaned_denuncia_photos,
)
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
    old_path = storage.root / old_url.removeprefix("/uploads/")
    return old_url, old_path.read_bytes()


class _ReferenceResult:
    def __init__(self, urls: list[str]) -> None:
        self._urls = urls

    def scalars(self):
        return self

    def all(self) -> list[str]:
        return self._urls


class _ReferenceDB:
    def __init__(self, urls: list[str]) -> None:
        self.urls = urls
        self.execute_calls = 0

    async def execute(self, _statement) -> _ReferenceResult:
        self.execute_calls += 1
        return _ReferenceResult(self.urls)


@pytest.mark.asyncio
async def test_delete_fsyncs_parent_after_unlink_and_absent_retry(tmp_path, monkeypatch) -> None:
    storage = LocalPhotoStorage(root=str(tmp_path), public_base="/uploads")
    photo_dir = tmp_path / "denuncias"
    photo_dir.mkdir()
    key = f"denuncias/{uuid.uuid4()}-{uuid.uuid4().hex}"
    photo_path = tmp_path / f"{key}.jpg"
    photo_path.write_bytes(b"photo")

    real_fsync = os.fsync
    fsync_spy = MagicMock(side_effect=real_fsync)
    monkeypatch.setattr("app.shared.storage.os.fsync", fsync_spy)

    await storage.delete(key)
    await storage.delete(key)

    assert not photo_path.exists()
    assert fsync_spy.call_count == 2


@pytest.mark.asyncio
async def test_partial_multi_extension_delete_fsyncs_before_raising(tmp_path, monkeypatch) -> None:
    storage = LocalPhotoStorage(root=str(tmp_path), public_base="/uploads")
    photo_dir = tmp_path / "denuncias"
    photo_dir.mkdir()
    key = f"denuncias/{uuid.uuid4()}-{uuid.uuid4().hex}"
    jpg_path = tmp_path / f"{key}.jpg"
    png_path = tmp_path / f"{key}.png"
    jpg_path.write_bytes(b"jpg")
    png_path.write_bytes(b"png")

    real_unlink = os.unlink
    real_fsync = os.fsync
    fsync_spy = MagicMock(side_effect=real_fsync)

    def fail_png(path, *, dir_fd=None):
        if str(path).endswith(".png"):
            raise OSError("permission denied")
        return real_unlink(path, dir_fd=dir_fd)

    monkeypatch.setattr("app.shared.storage.os.unlink", fail_png)
    monkeypatch.setattr("app.shared.storage.os.fsync", fsync_spy)

    with pytest.raises(OSError, match="permission denied"):
        await storage.delete(key)

    assert not jpg_path.exists()
    assert png_path.exists()
    fsync_spy.assert_called_once()


@pytest.mark.asyncio
async def test_directory_fsync_failure_propagates_and_absent_retry_fsyncs(
    tmp_path, monkeypatch
) -> None:
    storage = LocalPhotoStorage(root=str(tmp_path), public_base="/uploads")
    photo_dir = tmp_path / "denuncias"
    photo_dir.mkdir()
    key = f"denuncias/{uuid.uuid4()}-{uuid.uuid4().hex}"
    photo_path = tmp_path / f"{key}.webp"
    photo_path.write_bytes(b"photo")

    real_fsync = os.fsync
    fsync_calls = 0

    def fail_once(directory_fd: int) -> None:
        nonlocal fsync_calls
        fsync_calls += 1
        if fsync_calls == 1:
            raise OSError("directory sync failed")
        real_fsync(directory_fd)

    monkeypatch.setattr("app.shared.storage.os.fsync", fail_once)

    with pytest.raises(OSError, match="directory sync failed"):
        await storage.delete(key)

    assert not photo_path.exists()
    await storage.delete(key)
    assert fsync_calls == 2


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
async def test_post_commit_old_delete_failure_returns_committed_new_pointer(
    monkeypatch,
) -> None:
    denuncia_id = uuid.uuid4()
    user_id = uuid.uuid4()
    old_url = f"/uploads/denuncias/{denuncia_id}-{uuid.uuid4().hex}.png"
    new_url = f"/uploads/denuncias/{denuncia_id}-{uuid.uuid4().hex}.png"
    denuncia = SimpleNamespace(user_id=user_id, foto_url=old_url)
    db = _UploadDB(denuncia)
    storage = SimpleNamespace(
        save=AsyncMock(return_value=new_url),
        delete=AsyncMock(side_effect=OSError("directory sync failed")),
    )
    logger = MagicMock()
    router_module = importlib.import_module("app.domains.denuncias.router")
    monkeypatch.setattr(router_module, "logger", logger)

    response = await upload_denuncia_photo(
        denuncia_id,
        _upload(b"storage validates in production"),
        db,
        storage,
        SimpleNamespace(id=user_id),
    )

    assert response.photo_url == new_url
    assert denuncia.foto_url == new_url
    assert db.commit_calls == 1
    assert db.rollback_calls == 0
    storage.delete.assert_awaited_once()
    logger.exception.assert_called_once()


def _delete_db(denuncia):
    result = MagicMock()
    result.scalar_one_or_none.return_value = denuncia
    db = MagicMock()
    db.execute.return_value = result
    return db


@pytest.mark.asyncio
async def test_replacement_never_deletes_a_cross_report_photo_pointer() -> None:
    denuncia_id = uuid.uuid4()
    other_denuncia_id = uuid.uuid4()
    user_id = uuid.uuid4()
    old_url = f"/uploads/denuncias/{other_denuncia_id}-{uuid.uuid4().hex}.png"
    new_url = f"/uploads/denuncias/{denuncia_id}-{uuid.uuid4().hex}.png"
    denuncia = SimpleNamespace(user_id=user_id, foto_url=old_url, deleted_at=None)
    storage = SimpleNamespace(
        save=AsyncMock(return_value=new_url),
        delete=AsyncMock(),
    )

    response = await upload_denuncia_photo(
        denuncia_id,
        _upload(b"storage validates in production"),
        _UploadDB(denuncia),
        storage,
        SimpleNamespace(id=user_id),
    )

    assert response.photo_url == new_url
    storage.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancellation_commits_before_deleting_its_scoped_photo() -> None:
    denuncia_id = uuid.uuid4()
    user_id = uuid.uuid4()
    photo_key = f"denuncias/{denuncia_id}-{uuid.uuid4().hex}"
    denuncia = SimpleNamespace(
        id=denuncia_id,
        user_id=user_id,
        foto_url=f"/uploads/{photo_key}.png",
        deleted_at=None,
    )
    events: list[str] = []
    db = _delete_db(denuncia)
    db.commit.side_effect = lambda: events.append("commit")
    storage = SimpleNamespace(delete=AsyncMock(side_effect=lambda _key: events.append("delete")))

    await delete_my_denuncia(denuncia_id, db, storage, SimpleNamespace(id=user_id))

    assert events == ["commit", "delete"]
    storage.delete.assert_awaited_once_with(photo_key)
    assert denuncia.foto_url is None
    assert denuncia.deleted_at is not None


@pytest.mark.asyncio
async def test_cancellation_commit_failure_preserves_pointer_and_bytes() -> None:
    denuncia_id = uuid.uuid4()
    user_id = uuid.uuid4()
    old_url = f"/uploads/denuncias/{denuncia_id}-{uuid.uuid4().hex}.png"
    denuncia = SimpleNamespace(
        id=denuncia_id,
        user_id=user_id,
        foto_url=old_url,
        deleted_at=None,
    )
    db = _delete_db(denuncia)
    db.commit.side_effect = RuntimeError("database commit failed")
    storage = SimpleNamespace(delete=AsyncMock())

    with pytest.raises(HTTPException) as exc_info:
        await delete_my_denuncia(denuncia_id, db, storage, SimpleNamespace(id=user_id))

    assert exc_info.value.status_code == 503
    assert denuncia.foto_url == old_url
    assert denuncia.deleted_at is None
    db.rollback.assert_called_once()
    storage.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancellation_never_deletes_a_cross_report_photo_pointer() -> None:
    denuncia_id = uuid.uuid4()
    other_denuncia_id = uuid.uuid4()
    user_id = uuid.uuid4()
    denuncia = SimpleNamespace(
        id=denuncia_id,
        user_id=user_id,
        foto_url=f"/uploads/denuncias/{other_denuncia_id}-{uuid.uuid4().hex}.png",
        deleted_at=None,
    )
    db = _delete_db(denuncia)
    storage = SimpleNamespace(delete=AsyncMock())

    await delete_my_denuncia(denuncia_id, db, storage, SimpleNamespace(id=user_id))

    db.commit.assert_called_once()
    storage.delete.assert_not_awaited()
    assert denuncia.foto_url is None
    assert denuncia.deleted_at is not None


@pytest.mark.asyncio
async def test_post_commit_delete_failure_keeps_cancellation_and_logs(
    monkeypatch,
) -> None:
    denuncia_id = uuid.uuid4()
    user_id = uuid.uuid4()
    denuncia = SimpleNamespace(
        id=denuncia_id,
        user_id=user_id,
        foto_url=f"/uploads/denuncias/{denuncia_id}-{uuid.uuid4().hex}.png",
        deleted_at=None,
    )
    db = _delete_db(denuncia)
    storage = SimpleNamespace(delete=AsyncMock(side_effect=OSError("permission denied")))
    logger = MagicMock()
    router_module = importlib.import_module("app.domains.denuncias.router")
    monkeypatch.setattr(router_module, "logger", logger)

    await delete_my_denuncia(denuncia_id, db, storage, SimpleNamespace(id=user_id))

    assert denuncia.foto_url is None
    assert denuncia.deleted_at is not None
    db.commit.assert_called_once()
    db.rollback.assert_not_called()
    logger.exception.assert_called_once()


@pytest.mark.asyncio
async def test_orphan_reconciler_is_bounded_idempotent_and_conservative(tmp_path) -> None:
    storage = LocalPhotoStorage(root=str(tmp_path), public_base="/uploads")
    photo_dir = tmp_path / "denuncias"
    photo_dir.mkdir()
    now = datetime(2026, 7, 19, 12, tzinfo=timezone.utc)
    old_timestamp = (now - ORPHANED_DENUNCIA_PHOTO_GRACE - timedelta(hours=1)).timestamp()

    denuncia_id = uuid.UUID(int=1)

    def version_stem(version: int) -> str:
        return f"{denuncia_id}-{version:032x}"

    def create_old(stem: str, extension: str = "jpg"):
        path = photo_dir / f"{stem}.{extension}"
        path.write_bytes(b"photo")
        os.utime(path, (old_timestamp, old_timestamp))
        return path

    eligible = [create_old(version_stem(version)) for version in (1, 2, 3)]
    referenced = create_old(version_stem(4))
    recent = photo_dir / f"{version_stem(5)}.jpg"
    recent.write_bytes(b"recent")

    legacy = create_old(str(denuncia_id))
    ambiguous = create_old(f"{denuncia_id}-not-a-version")

    outside_file = tmp_path / "outside-photo"
    outside_file.write_bytes(b"outside")
    unsafe_symlink = photo_dir / f"{version_stem(6)}.jpg"
    unsafe_symlink.symlink_to(outside_file)

    mixed_old = create_old(version_stem(7), "jpg")
    mixed_recent = photo_dir / f"{version_stem(7)}.png"
    mixed_recent.write_bytes(b"recent")

    # Current pointers remain authoritative even when their persisted base
    # predates the currently configured /uploads prefix.
    db = _ReferenceDB([f"https://old.example/legacy-uploads/denuncias/{version_stem(4)}.jpg"])

    assert (
        await reconcile_orphaned_denuncia_photos(
            db,
            storage,
            now=now,
            batch_size=2,
        )
        == 2
    )
    assert not eligible[0].exists()
    assert not eligible[1].exists()
    assert eligible[2].exists()

    assert referenced.exists()
    assert recent.exists()
    assert legacy.exists()
    assert ambiguous.exists()
    assert unsafe_symlink.is_symlink()
    assert outside_file.exists()
    assert mixed_old.exists()
    assert mixed_recent.exists()

    assert (
        await reconcile_orphaned_denuncia_photos(
            db,
            storage,
            now=now,
            batch_size=2,
        )
        == 1
    )
    assert not eligible[2].exists()
    assert (
        await reconcile_orphaned_denuncia_photos(
            db,
            storage,
            now=now,
            batch_size=2,
        )
        == 0
    )
    assert db.execute_calls == 3


@pytest.mark.asyncio
async def test_orphan_reconciler_never_follows_managed_directory_symlink(tmp_path) -> None:
    root = tmp_path / "uploads"
    storage = LocalPhotoStorage(root=str(root), public_base="/uploads")
    outside = tmp_path / "outside"
    outside.mkdir()
    stem = f"{uuid.UUID(int=2)}-{1:032x}"
    outside_photo = outside / f"{stem}.jpg"
    outside_photo.write_bytes(b"outside")
    (root / "denuncias").symlink_to(outside, target_is_directory=True)

    reconciled = await reconcile_orphaned_denuncia_photos(
        _ReferenceDB([]),
        storage,
        now=datetime(2026, 7, 19, 12, tzinfo=timezone.utc),
    )

    assert reconciled == 0
    assert outside_photo.read_bytes() == b"outside"
