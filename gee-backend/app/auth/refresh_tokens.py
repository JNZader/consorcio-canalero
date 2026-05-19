"""Rotating refresh-token service (Phase 2 / F2-K).

Issues, rotates, and revokes refresh tokens. The raw token is a 256-bit
URL-safe nonce; we store ``sha256(token)`` in ``refresh_tokens.token_hash``
so a DB read can't be turned into impersonation. Every rotation marks
the old row ``revoked`` and inserts a new row inheriting the same
``family_id`` — re-using a revoked token kills the whole family (replay
detection).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.auth.models import RefreshToken, User


# 30-day lifetime — long enough that a daily-active user never sees a
# re-login, short enough that a stolen cookie has bounded value.
REFRESH_TOKEN_LIFETIME = timedelta(days=30)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _new_raw_token() -> str:
    # 256 bits ≈ 43 URL-safe chars. The cookie carries the raw value;
    # the DB only ever sees the hash.
    return secrets.token_urlsafe(32)


async def issue_token(
    session: AsyncSession,
    *,
    user: User,
    family_id: uuid.UUID | None = None,
    user_agent: str | None = None,
    client_ip: str | None = None,
) -> tuple[str, RefreshToken]:
    """Issue a new refresh token.

    Pass ``family_id`` to chain into an existing family (rotation);
    omit to start a fresh family (login).
    """
    raw = _new_raw_token()
    token_row = RefreshToken(
        user_id=user.id,
        token_hash=_hash_token(raw),
        family_id=family_id or uuid.uuid4(),
        expires_at=datetime.now(tz=timezone.utc) + REFRESH_TOKEN_LIFETIME,
        revoked=False,
        user_agent=(user_agent or "")[:255] or None,
        client_ip=(client_ip or "")[:64] or None,
    )
    session.add(token_row)
    await session.commit()
    await session.refresh(token_row)
    return raw, token_row


async def find_active(session: AsyncSession, raw_token: str) -> RefreshToken | None:
    """Look up a refresh-token row by the raw value. Returns None when
    the value is unknown, expired, or already revoked.

    The lookup is constant-time relative to the hash — same hashing
    cost regardless of whether the token exists.
    """
    digest = _hash_token(raw_token)
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == digest)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    if row.revoked:
        return row  # caller must handle "revoked" as the replay signal
    if row.expires_at <= datetime.now(tz=timezone.utc):
        return None
    return row


async def revoke_family(session: AsyncSession, family_id: uuid.UUID) -> int:
    """Revoke every token in the family. Returns the row count.

    Called when a replayed (already-revoked) refresh token is presented:
    the attacker likely stole the cookie, so the whole session is
    burnt down even if individual rows looked valid.
    """
    result = await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked.is_(False))
        .values(revoked=True, revoked_at=datetime.now(tz=timezone.utc))
    )
    await session.commit()
    # ``rowcount`` is only on UPDATE/DELETE Results; mypy types the base
    # Result without it. The driver guarantees the attribute for the
    # statement shape we're using here, so the cast is safe.
    return int(getattr(result, "rowcount", 0) or 0)


RACE_WINDOW = timedelta(seconds=30)


async def rotate(
    session: AsyncSession,
    *,
    raw_token: str,
    user: User,
    user_agent: str | None = None,
    client_ip: str | None = None,
) -> tuple[str, RefreshToken] | None:
    """Rotate a presented refresh token.

    Returns ``(new_raw_token, new_row)`` on success, ``None`` on auth
    failure (unknown / expired / replay).

    Concurrency model:
      - First call wins the CAS UPDATE, stamps ``revoked_at = now()``,
        and mints a new token in the same family.
      - Second call within ``RACE_WINDOW`` (two-tab race) loses the
        CAS, sees the row already revoked but with ``revoked_at`` very
        recent, and returns ``None`` WITHOUT burning the family.
      - Third call past ``RACE_WINDOW`` (real replay — attacker stole
        the cookie after the legit user rotated) loses the CAS, sees
        the row revoked with ``revoked_at`` old, and DOES burn the
        family.
    """
    digest = _hash_token(raw_token)
    now = datetime.now(tz=timezone.utc)

    # Compare-and-swap: only one concurrent caller flips ``revoked``
    # False→True. Stamp ``revoked_at`` in the same statement so the
    # race-vs-replay decision below is unambiguous.
    cas_result = await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == digest,
            RefreshToken.revoked.is_(False),
            RefreshToken.user_id == user.id,
            RefreshToken.expires_at > now,
        )
        .values(revoked=True, revoked_at=now)
        .returning(RefreshToken.id, RefreshToken.family_id)
    )
    winner = cas_result.first()
    if winner is not None:
        await session.commit()
        return await issue_token(
            session,
            user=user,
            family_id=winner.family_id,
            user_agent=user_agent,
            client_ip=client_ip,
        )

    # Lost the CAS. Distinguish race-loss from replay.
    replay_lookup = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == digest)
    )
    replay_row = replay_lookup.scalar_one_or_none()
    if replay_row is None or not replay_row.revoked:
        # Unknown token, expired, or wrong user — plain 401.
        return None

    # Row IS revoked. If the revocation is very recent, it's the
    # winner of a concurrent rotate; if it's older than RACE_WINDOW,
    # the cookie was reused long after rotation → replay.
    revoked_at = replay_row.revoked_at
    if revoked_at is None:
        # Legacy row revoked before the column existed — be
        # conservative and treat as replay (the row's ``updated_at``
        # is the proxy used by the migration backfill, so any
        # non-backfilled NULL means the revocation is OLD).
        await revoke_family(session, replay_row.family_id)
        return None
    if now - revoked_at > RACE_WINDOW:
        # Real replay. Burn the family.
        await revoke_family(session, replay_row.family_id)
        return None

    # Race-loss within the grace window — return None without burn.
    return None


async def revoke_all_for_user(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Revoke every non-revoked refresh token for the user."""
    result = await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
        .values(revoked=True, revoked_at=datetime.now(tz=timezone.utc))
    )
    await session.commit()
    # ``rowcount`` is only on UPDATE/DELETE Results; mypy types the base
    # Result without it. The driver guarantees the attribute for the
    # statement shape we're using here, so the cast is safe.
    return int(getattr(result, "rowcount", 0) or 0)
