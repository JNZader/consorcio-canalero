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

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import RefreshToken


EXPIRED_GRACE = timedelta(days=7)
REVOKED_GRACE = timedelta(days=30)


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
