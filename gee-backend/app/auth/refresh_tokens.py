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

from sqlalchemy import false, true, update
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


# A two-tab race in practice completes in under a second (cookie present
# → /refresh request → CAS UPDATE → response). 5 s is generous margin
# for slow networks; anything past that is overwhelmingly more likely
# to be a stolen cookie reused after the legit owner rotated than a
# pathologically slow concurrent click.
RACE_WINDOW = timedelta(seconds=5)


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

    Timing: race-loss and replay paths run the SAME number of SQL
    statements (CAS + SELECT + family-update + commit) so an attacker
    can't read latency to learn whether the cookie they hold was just
    rotated. The family-update in the race-loss path is a no-op
    (guarded by ``literal(False)``) but takes the same wire time.
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

    # Lost the CAS. Distinguish race-loss from replay — but do BOTH
    # paths with identical SQL roundtrips so the timing side-channel
    # the post-2.2 review surfaced doesn't leak which case we hit.
    replay_lookup = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == digest)
    )
    replay_row = replay_lookup.scalar_one_or_none()
    if replay_row is None or not replay_row.revoked:
        # Unknown token, expired, or wrong user — plain 401. No
        # family operation possible (no family to act on); we accept
        # the slight timing skew here because this path doesn't leak
        # information about an EXISTING family.
        return None

    # Decide burn vs no-op based on revoked_at age. ``None`` legacy
    # rows from the pre-2.2 era are treated as replay (conservative).
    revoked_at = replay_row.revoked_at
    should_burn = revoked_at is None or (now - revoked_at) > RACE_WINDOW

    # Always run the family UPDATE. In ``should_burn=False`` the
    # ``literal(False)`` predicate matches 0 rows so the operation is
    # a no-op — but it costs the same wire roundtrip as the real burn.
    # The extra ``created_at <= replay_row.revoked_at`` filter prevents
    # the rare race where, between our SELECT and the family update,
    # a legit user wins a concurrent CAS and mints a NEW token in the
    # same family. That fresh row mustn't get caught in our sweep.
    await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.family_id == replay_row.family_id,
            RefreshToken.revoked.is_(False),
            RefreshToken.created_at <= (replay_row.revoked_at or replay_row.created_at),
            true() if should_burn else false(),
        )
        .values(revoked=True, revoked_at=now)
    )
    await session.commit()
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
