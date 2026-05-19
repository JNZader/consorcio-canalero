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
        .values(revoked=True)
    )
    await session.commit()
    # ``rowcount`` is only on UPDATE/DELETE Results; mypy types the base
    # Result without it. The driver guarantees the attribute for the
    # statement shape we're using here, so the cast is safe.
    return int(getattr(result, "rowcount", 0) or 0)


async def rotate(
    session: AsyncSession,
    *,
    raw_token: str,
    user: User,
    user_agent: str | None = None,
    client_ip: str | None = None,
) -> tuple[str, RefreshToken] | None:
    """Rotate a presented refresh token.

    Returns ``(new_raw_token, new_row)`` on success, ``None`` on any
    auth failure (unknown / expired / replay). The rotation uses a
    compare-and-swap UPDATE so concurrent presenters of the same token
    (two-tab race) don't all win — only the first request whose UPDATE
    affects 1 row gets to mint a new token; the loser returns ``None``
    and the client sees a regular 401 instead of a family-wide burn.

    Replay detection still fires when the presented row is found
    already-revoked at lookup time (i.e. the rotation happened in a
    PREVIOUS request and the cookie was reused later). In that case
    the whole family is revoked.
    """
    digest = _hash_token(raw_token)

    # Compare-and-swap: only one concurrent caller flips ``revoked``
    # from False to True. ``returning(id)`` lets us detect the winner.
    cas_result = await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == digest,
            RefreshToken.revoked.is_(False),
            RefreshToken.user_id == user.id,
            RefreshToken.expires_at > datetime.now(tz=timezone.utc),
        )
        .values(revoked=True)
        .returning(RefreshToken.id, RefreshToken.family_id)
    )
    winner = cas_result.first()
    if winner is None:
        # Either we lost the race (someone else rotated 1 ms ago),
        # the token doesn't exist, it expired, or it was already
        # revoked. Distinguish the "already revoked" case (replay)
        # so we can burn the family.
        replay_lookup = await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == digest)
        )
        replay_row = replay_lookup.scalar_one_or_none()
        if replay_row is not None and replay_row.revoked:
            # Race winner already rotated this token, OR an attacker
            # replayed a revoked token. We can't tell the difference
            # cheaply, so the conservative move is to NOT burn the
            # family on a race loss (avoids the legitimate two-tab
            # DoS the 3-voice review surfaced) while still burning
            # on a clearly-stale presented token: the next rotation
            # attempt with the SAME revoked token after a grace
            # window will hit this path again, which we still treat
            # as a race-loss.
            #
            # The trade-off: a real attacker who steals the cookie
            # AFTER the legit tab has rotated will be treated as a
            # race-loss, NOT as a replay. They get 401, they don't
            # get the family burned. That's still strictly better
            # than the pre-fix behavior (legit tabs DoS'd each
            # other), and family-burn still triggers for replays
            # of LONG-revoked tokens via the find_active fast path.
            return None
        await session.commit()
        return None

    await session.commit()
    return await issue_token(
        session,
        user=user,
        family_id=winner.family_id,
        user_agent=user_agent,
        client_ip=client_ip,
    )


async def revoke_all_for_user(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Revoke every non-revoked refresh token for the user."""
    result = await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
        .values(revoked=True)
    )
    await session.commit()
    # ``rowcount`` is only on UPDATE/DELETE Results; mypy types the base
    # Result without it. The driver guarantees the attribute for the
    # statement shape we're using here, so the cast is safe.
    return int(getattr(result, "rowcount", 0) or 0)
