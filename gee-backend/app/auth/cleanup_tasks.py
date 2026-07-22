"""Periodic cleanup of expired/revoked refresh tokens (Phase 2.1).

Without this the ``refresh_tokens`` table grows unbounded — every login
creates a new family, every refresh adds a row to it. A daily cron
keeps the table at a healthy size and makes the
``ix_refresh_tokens_token_hash`` index small enough to stay hot in
memory.

Retention policy (defensive defaults — tune via env if needed):
  - Expired tokens: delete after expiry + 7 days. The window gives
    operators a chance to audit "why did Juan get logged out" via
    the row before it disappears.
  - Revoked tokens: delete after revocation + 30 days. The window
    keeps replay-detection forensics available.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import RefreshToken
from app.shared.storage import LocalPhotoStorage, MIME_TO_EXTENSION


EXPIRED_GRACE = timedelta(days=7)
REVOKED_GRACE = timedelta(days=30)
# Phase 4 / F4-K: ARCO soft-delete audit window. A user-requested
# deletion keeps the row for 1 year so the consorcio can demonstrate
# that the operator handled their request (audit trail) before the
# row is finally purged.
DELETED_DENUNCIA_GRACE = timedelta(days=365)

# Replacement uploads use immutable keys shaped as
# denuncias/<uuid>-<32 hex version>.<extension>. A commit/response
# ambiguity deliberately preserves the new bytes, and a post-commit cleanup
# failure deliberately preserves the old bytes. The daily reconciler below
# reclaims only files that are old enough for those races to have settled.
ORPHANED_DENUNCIA_PHOTO_GRACE = timedelta(hours=24)
ORPHANED_DENUNCIA_PHOTO_BATCH_SIZE = 100
_PHOTO_EXTENSION_PATTERN = "|".join(sorted(set(MIME_TO_EXTENSION.values())))
_VERSIONED_DENUNCIA_PHOTO_RE = re.compile(
    rf"^(?P<stem>[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-"
    rf"[0-9a-f]{{4}}-[0-9a-f]{{12}}-[0-9a-f]{{32}})"
    rf"\.(?:{_PHOTO_EXTENSION_PATTERN})$"
)


async def purge_stale_refresh_tokens(session: AsyncSession) -> int:
    """Delete refresh-token rows older than the retention grace.

    Returns the number of rows removed. Safe to call concurrently;
    the WHERE clause is set-based so two workers running this at the
    same time just compete on the same DELETE.
    """
    now = datetime.now(tz=timezone.utc)
    result = await session.execute(
        delete(RefreshToken).where(
            or_(
                RefreshToken.expires_at < now - EXPIRED_GRACE,
                # Phase 2.2: real ``revoked_at`` lets us purge tokens
                # exactly REVOKED_GRACE days after the revocation.
                # The legacy backfill (zz_refresh_tokens_revoked_at
                # migration) copied ``updated_at`` into ``revoked_at``
                # for any pre-existing revoked rows.
                (RefreshToken.revoked.is_(True))
                & (RefreshToken.revoked_at.is_not(None))
                & (RefreshToken.revoked_at < now - REVOKED_GRACE),
            )
        )
    )
    await session.commit()
    return int(getattr(result, "rowcount", 0) or 0)


async def purge_soft_deleted_denuncias(session: AsyncSession) -> int:
    """Hard-delete denuncia rows soft-deleted more than 1 year ago.

    Phase 4 / F4-K. Mirrors the refresh-token cleanup. Returns the
    number of rows removed.
    """
    from app.domains.denuncias.models import Denuncia

    now = datetime.now(tz=timezone.utc)
    result = await session.execute(
        delete(Denuncia).where(
            Denuncia.deleted_at.is_not(None),
            Denuncia.deleted_at < now - DELETED_DENUNCIA_GRACE,
        )
    )
    await session.commit()
    return int(getattr(result, "rowcount", 0) or 0)


async def reconcile_orphaned_denuncia_photos(
    session: AsyncSession,
    storage: LocalPhotoStorage | None = None,
    *,
    now: datetime | None = None,
    grace: timedelta = ORPHANED_DENUNCIA_PHOTO_GRACE,
    batch_size: int = ORPHANED_DENUNCIA_PHOTO_BATCH_SIZE,
) -> int:
    """Durably delete a bounded batch of old, unreferenced photo versions.

    The scan is intentionally conservative:

    * only canonical immutable version names produced by the upload route;
    * every current Denuncia.foto_url pointer is preserved, including
      soft-deleted rows;
    * recent files, symlinks, non-regular entries, ambiguous names, and any
      directory outside the managed local-storage root are untouched;
    * all extensions sharing a version stem must be old and safe before the
      stem is deleted.

    Returns the number of version stems reconciled. Repeated calls are
    idempotent, and LocalPhotoStorage.delete supplies the directory fsync
    that makes each successful batch durable.
    """
    from app.domains.denuncias.models import Denuncia

    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if grace < timedelta(0):
        raise ValueError("grace must not be negative")

    photo_storage = storage if storage is not None else LocalPhotoStorage()
    effective_now = now if now is not None else datetime.now(tz=timezone.utc)
    if effective_now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    cutoff_timestamp = (effective_now - grace).timestamp()

    # Query first and fail closed: if the DB cannot provide the complete
    # pointer set, no filesystem entry is considered safe to delete.
    result = await session.execute(select(Denuncia.foto_url).where(Denuncia.foto_url.is_not(None)))
    referenced_stems: set[str] = set()
    for photo_url in result.scalars().all():
        if not photo_url:
            continue
        # Preserve canonical pointer filenames regardless of the currently
        # configured public URL prefix. A deployment may change that prefix
        # while old rows still contain the previous relative or absolute URL.
        pointer_name = Path(urlsplit(photo_url).path).name
        pointer_match = _VERSIONED_DENUNCIA_PHOTO_RE.fullmatch(pointer_name)
        if pointer_match is not None:
            referenced_stems.add(pointer_match.group("stem"))

    root = photo_storage.root.resolve()
    photo_directory = photo_storage.root / "denuncias"
    try:
        if photo_directory.is_symlink():
            return 0
        resolved_photo_directory = photo_directory.resolve()
        resolved_photo_directory.relative_to(root)
    except (OSError, ValueError):
        return 0
    if not resolved_photo_directory.is_dir():
        return 0

    mtimes_by_stem: dict[str, list[float]] = {}
    unsafe_stems: set[str] = set()
    try:
        with os.scandir(resolved_photo_directory) as entries:
            for entry in entries:
                match = _VERSIONED_DENUNCIA_PHOTO_RE.fullmatch(entry.name)
                if match is None:
                    continue
                stem = match.group("stem")
                try:
                    if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                        unsafe_stems.add(stem)
                        continue
                    stat_result = entry.stat(follow_symlinks=False)
                except OSError:
                    unsafe_stems.add(stem)
                    continue
                mtimes_by_stem.setdefault(stem, []).append(stat_result.st_mtime)
    except FileNotFoundError:
        return 0

    eligible_stems = sorted(
        stem
        for stem, mtimes in mtimes_by_stem.items()
        if stem not in referenced_stems
        and stem not in unsafe_stems
        and mtimes
        and all(mtime < cutoff_timestamp for mtime in mtimes)
    )

    reconciled = 0
    for stem in eligible_stems[:batch_size]:
        await photo_storage.delete(f"denuncias/{stem}")
        reconciled += 1
    return reconciled
