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

import io
import os
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from typing import Protocol

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from app.config import settings


# EXIF tag id for GPSInfo. Strip this and `_GPS_RELATED_TAGS` below
# before writing the photo to disk — the user's geo coordinates ride
# the photo otherwise, which is PII the consorcio has no business
# holding (we already record the denuncia's reported coordinates on
# the row itself).
_EXIF_GPS_INFO_TAG = 0x8825
# Tags that some camera apps stash GPS data under as a fallback.
_GPS_RELATED_TAGS = {
    _EXIF_GPS_INFO_TAG,
    0x0001,  # GPSLatitudeRef (some Android camera apps)
    0x0002,  # GPSLatitude
    0x0003,  # GPSLongitudeRef
    0x0004,  # GPSLongitude
    0x0006,  # GPSAltitude
}

# Maps the MIME type we accept to the Pillow format string we expect
# ``Image.format`` to report when the bytes are really that type.
_MIME_TO_PIL_FORMAT = {
    "image/jpeg": "JPEG",
    "image/jpg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}


def _validate_and_strip_exif(content: bytes, declared_mime: str) -> bytes:
    """Verify the magic bytes match ``declared_mime`` and drop EXIF GPS.

    Returns the re-encoded image bytes (without EXIF GPS tags). Raises
    ``HTTPException(400)`` when the file isn't a real image of the
    declared type — protects against the polyglot/disguise vector
    where a client sets ``Content-Type: image/jpeg`` on a PHP script
    or a zip bomb.

    EXIF cleanup keeps non-GPS metadata (camera model, capture date,
    orientation) so the photo still renders correctly. We only remove
    the GPS block — the user already gives consent to the denuncia's
    own coordinates on the form, but the EXIF GPS leaks where the
    PHOTO was taken (which could be the user's home address, hours
    before the denuncia was filed).
    """
    expected_format = _MIME_TO_PIL_FORMAT.get(declared_mime)
    if expected_format is None:
        # Caller's MIME check already filtered the allow-list; defensive.
        raise HTTPException(
            status_code=400,
            detail=f"Tipo MIME no permitido: {declared_mime or 'desconocido'}.",
        )

    try:
        image = Image.open(io.BytesIO(content))
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(
            status_code=400,
            detail="El archivo no es una imagen válida.",
        ) from exc

    if image.format != expected_format:
        raise HTTPException(
            status_code=400,
            detail=(
                f"El archivo declara MIME {declared_mime} pero el contenido "
                f"es {image.format or 'desconocido'}."
            ),
        )

    # ``verify()`` does NOT decode the full pixel buffer — it walks the
    # parser to ensure the file isn't truncated/corrupt and re-raises
    # the original parse error if so. After ``verify()`` the image
    # object is unusable, so we re-open from the same bytes for the
    # actual re-encode.
    image.verify()
    image = Image.open(io.BytesIO(content))

    # Strip EXIF GPS. ``getexif()`` returns the parsed IFD; setting an
    # empty IFD on GPSInfo (or dropping its keys) achieves the goal.
    exif = image.getexif()
    if exif is not None:
        for tag in list(exif.keys()):
            if tag in _GPS_RELATED_TAGS:
                del exif[tag]
        # Recurse into the nested GPSInfo IFD if present (Pillow 10+).
        try:
            gps_ifd = exif.get_ifd(_EXIF_GPS_INFO_TAG)
            if gps_ifd:
                for tag in list(gps_ifd.keys()):
                    del gps_ifd[tag]
        except KeyError:
            pass

    # Re-encode preserving the original format. ``optimize=True`` on
    # JPEG/PNG trims the file slightly without quality loss; WebP gets
    # a near-lossless re-encode.
    buffer = io.BytesIO()
    # Pillow's typeshed declares the save kwargs as ``str | None``,
    # but in practice each format reads them differently (ints for
    # quality, bool for optimize). ``Any`` is the practical type here.
    save_kwargs: dict[str, object] = {}
    if exif is not None:
        save_kwargs["exif"] = exif.tobytes()
    if expected_format == "JPEG":
        save_kwargs["quality"] = 92
        save_kwargs["optimize"] = True
    elif expected_format == "PNG":
        save_kwargs["optimize"] = True
    elif expected_format == "WEBP":
        save_kwargs["quality"] = 92
    image.save(buffer, format=expected_format, **save_kwargs)
    return buffer.getvalue()


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

        # Read the upload into memory with an incremental cap so the
        # 10 MB max never balloons before the check fires. We need the
        # full bytes (not a stream) to run Pillow's magic-byte
        # validation + EXIF GPS strip below — at 10 MB the memory cost
        # is bounded and equivalent to what Pillow itself would buffer.
        buffer = bytearray()
        chunk_size = 1024 * 1024  # 1 MB
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            if len(buffer) + len(chunk) > MAX_PHOTO_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"La foto supera el límite de {MAX_PHOTO_BYTES // (1024 * 1024)} MB.",
                )
            buffer.extend(chunk)

        if not buffer:
            raise HTTPException(status_code=400, detail="Archivo vacío.")

        # Validate magic bytes match declared MIME + strip EXIF GPS.
        # Raises HTTPException(400) on disguised payloads or malformed
        # images. Returns the re-encoded bytes ready to write to disk.
        sanitized_bytes = _validate_and_strip_exif(bytes(buffer), content_type)

        # Write beside the destination so os.replace is atomic on the mounted
        # filesystem. fsync the file and parent directory before publishing the URL.
        temp_path = full_path.with_name(f".{full_path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temp_path.open("xb") as out:
                out.write(sanitized_bytes)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temp_path, full_path)
            directory_fd = os.open(full_path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass

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
                # Preserve the failure so callers do not erase the DB pointer
                # while sensitive bytes remain on disk.
                raise


# ─────────────────────────────────────────────────────────────────────────
# Helpers — used by routers so they don't recreate IDs ad-hoc.
# ─────────────────────────────────────────────────────────────────────────


def make_denuncia_photo_key(
    denuncia_id: uuid.UUID | str,
    version: str | None = None,
) -> str:
    """Build a photo key; replacements use immutable versioned filenames."""
    base = f"denuncias/{denuncia_id}"
    return f"{base}-{version}" if version else base


def photo_key_from_url(photo_url: str, public_base: str | None = None) -> str | None:
    """Recover the exact extension-less storage key from a persisted URL."""
    base = (public_base or settings.uploads_public_base).rstrip("/")
    path = urlsplit(photo_url).path
    prefix = f"{base}/"
    if not path.startswith(prefix):
        return None
    relative = path[len(prefix):]
    suffix = Path(relative).suffix.lower().lstrip(".")
    if suffix not in set(MIME_TO_EXTENSION.values()):
        return None
    key = relative[: -(len(suffix) + 1)]
    if not key.startswith("denuncias/") or ".." in Path(key).parts:
        return None
    return key


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
    "photo_key_from_url",
    "override_photo_storage",
]


# Suppress unused-import warning when the module is imported only for its
# side-effect of registering settings. `os` is referenced lazily by some
# environments via env vars resolved inside Settings.
_ = os
