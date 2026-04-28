"""
Photo storage abstraction for citizen-facing uploads (denuncias).

The `PhotoStorage` Protocol lets us swap the concrete backend without
touching the router code. Today we ship `LocalPhotoStorage` — files land
on a Docker-mounted volume and are served by `app.mount("/uploads", StaticFiles(...))`.
Tomorrow, when traffic justifies it, drop in `MinIOPhotoStorage` (or S3,
R2, Spaces, …) by replacing the binding in `dependencies.py`. Migration of
existing files is one `mc mirror /app/uploads minio/denuncias-photos`.

Why local-disk first:
- The Hetzner CX33 has 80 GB → ~30k photos at ~3 MB each is plenty.
- Zero new services to run, zero new credentials to manage.
- Snapshots of the VPS already include the volume, so backups are free.
- The interface below means swapping later is a one-file change.

What we DO NOT do here:
- Resize / re-encode images. Citizens upload phone photos; we keep them.
- Generate thumbnails. Add later if the InfoPanel needs them.
- Anti-virus scanning. Out of scope for v1; revisit if abuse appears.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException, UploadFile

from app.config import settings

# ─────────────────────────────────────────────────────────────────────────
# Validation constants — applied by the router before calling storage.save
# (storage stays "dumb" so it can be reused by any caller policy).
# ─────────────────────────────────────────────────────────────────────────

ALLOWED_PHOTO_MIME_TYPES = frozenset(
    {
        "image/jpeg",
        "image/jpg",  # Some clients send this non-standard variant.
        "image/png",
        "image/webp",
    }
)

MIME_TO_EXTENSION = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

MAX_PHOTO_BYTES = 10 * 1024 * 1024  # 10 MB


# ─────────────────────────────────────────────────────────────────────────
# Protocol — the public contract every storage backend must satisfy.
# ─────────────────────────────────────────────────────────────────────────


class PhotoStorage(Protocol):
    """Abstract photo storage. Implementations decide WHERE bytes land."""

    async def save(self, file: UploadFile, key: str) -> str:
        """
        Persist `file` under the logical `key` (e.g. `denuncias/<uuid>`).

        Returns the publicly resolvable URL/path to retrieve it later.
        Raises HTTPException(400) on invalid input or HTTPException(413)
        when the file exceeds the size limit.
        """
        ...

    async def delete(self, key: str) -> None:
        """Best-effort delete. Silently no-ops if the file is gone."""
        ...


# ─────────────────────────────────────────────────────────────────────────
# Local filesystem implementation — default for the Docker Compose deploy.
# ─────────────────────────────────────────────────────────────────────────


class LocalPhotoStorage:
    """
    Writes photos to a directory on a Docker-mounted volume. The directory
    is configured by `settings.uploads_root`; the public URL prefix by
    `settings.uploads_public_base`. Both are read once at construction —
    callers should request a fresh instance per request via the FastAPI
    dependency, not memoize a module-level singleton (the dependency
    machinery already caches per-request).
    """

    def __init__(
        self,
        root: str | None = None,
        public_base: str | None = None,
    ) -> None:
        self._root = Path(root or settings.uploads_root)
        self._public_base = (public_base or settings.uploads_public_base).rstrip("/")
        # Create lazily — production volume already exists; in tests the
        # tmp_path fixture makes it cheap to create per-test.
        self._root.mkdir(parents=True, exist_ok=True)

    async def save(self, file: UploadFile, key: str) -> str:
        # Caller (router) is expected to have validated MIME + size already,
        # but we re-validate here so misuse from a future caller fails loud.
        content_type = (file.content_type or "").lower()
        if content_type not in ALLOWED_PHOTO_MIME_TYPES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Tipo de archivo no permitido: {content_type or 'desconocido'}. "
                    "Use JPG, PNG o WebP."
                ),
            )

        extension = MIME_TO_EXTENSION[content_type]
        # `key` is the logical path WITHOUT extension (e.g. "denuncias/<uuid>").
        # We append the extension so the file on disk has a useful suffix
        # and the StaticFiles handler can infer the right content-type.
        rel_path = f"{key}.{extension}"
        full_path = self._root / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Stream the upload to disk in chunks so we never hold the whole
        # file in memory. Enforce the size limit incrementally — important
        # because `UploadFile.read()` would happily allocate hundreds of MB
        # before any check fired.
        bytes_written = 0
        chunk_size = 1024 * 1024  # 1 MB
        with full_path.open("wb") as out:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > MAX_PHOTO_BYTES:
                    out.close()
                    full_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"La foto supera el límite de {MAX_PHOTO_BYTES // (1024 * 1024)} MB.",
                    )
                out.write(chunk)

        # Public URL: relative path under the StaticFiles mount. We persist
        # the relative form (`/uploads/denuncias/<uuid>.jpg`) so swapping
        # the public host (frontend domain change, CDN in front, etc.)
        # doesn't require a DB rewrite.
        return f"{self._public_base}/{rel_path}"

    async def delete(self, key: str) -> None:
        # We do not know the extension at delete time (the DB stores the
        # full URL, not the bare key). Try all known extensions; ignore
        # FileNotFoundError because the consumer doesn't care if it's
        # already gone.
        for ext in set(MIME_TO_EXTENSION.values()):
            candidate = self._root / f"{key}.{ext}"
            try:
                candidate.unlink()
            except FileNotFoundError:
                continue
            except OSError:
                # Permissions / disk error — log via the caller; storage
                # stays best-effort.
                continue


# ─────────────────────────────────────────────────────────────────────────
# Helpers — used by routers so they don't recreate IDs ad-hoc.
# ─────────────────────────────────────────────────────────────────────────


def make_denuncia_photo_key(denuncia_id: uuid.UUID | str) -> str:
    """Canonical storage key for a denuncia photo. Stable across backends."""
    return f"denuncias/{denuncia_id}"


# ─────────────────────────────────────────────────────────────────────────
# FastAPI dependency — the single point where backend selection happens.
# Swap to `MinIOPhotoStorage(...)` here when the time comes; the rest of
# the codebase stays untouched.
# ─────────────────────────────────────────────────────────────────────────


_storage_singleton: PhotoStorage | None = None


def get_photo_storage() -> PhotoStorage:
    """Return the process-wide PhotoStorage instance (lazy init)."""
    global _storage_singleton
    if _storage_singleton is None:
        _storage_singleton = LocalPhotoStorage()
    return _storage_singleton


# Convenience for tests: lets a fixture set the global without monkey-patching.
def override_photo_storage(storage: PhotoStorage | None) -> None:
    """Replace the global storage. Pass `None` to reset to default."""
    global _storage_singleton
    _storage_singleton = storage


__all__ = [
    "ALLOWED_PHOTO_MIME_TYPES",
    "LocalPhotoStorage",
    "MAX_PHOTO_BYTES",
    "MIME_TO_EXTENSION",
    "PhotoStorage",
    "get_photo_storage",
    "make_denuncia_photo_key",
    "override_photo_storage",
]


# Suppress unused-import warning when the module is imported only for its
# side-effect of registering settings. `os` is referenced lazily by some
# environments via env vars resolved inside Settings.
_ = os
