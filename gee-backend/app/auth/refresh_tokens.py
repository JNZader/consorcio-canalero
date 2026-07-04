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

from sqlalchemy import false, func, true, update
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
    commit: bool = True,
) -> tuple[str, RefreshToken]:
    """Issue a new refresh token.

    Pass ``family_id`` to chain into an existing family (rotation);
    omit to start a fresh family (login).

    ``commit`` controls transaction ownership:
      - ``commit=True`` (default, login path): this function commits AND
        refreshes the new row before returning, so the caller
        (``login_with_refresh``) gets a fully-persisted, key-populated
        row without owning a transaction.
      - ``commit=False`` (rotate path): this function only ``flush``es
        (assigns the PK / server-side defaults WITHOUT ending the
        transaction) and leaves the commit to the caller, so the CAS and
        the mint land in ONE transaction (see ``rotate`` for why that
        atomicity is load-bearing).
    """
    raw = _new_raw_token()
    # Use Python ``now`` for both ``created_at`` and ``expires_at`` so
    # the new token's ``created_at`` shares a clock with the OLD
    # token's ``revoked_at`` (also Python ``now`` in the CAS UPDATE).
    # Without this, ``created_at`` falls to PostgreSQL ``NOW()``
    # (server_default) and a few ms of inter-clock skew could let the
    # replay-detection sweep catch a token that was actually minted
    # AFTER the legit rotation.
    now = datetime.now(tz=timezone.utc)
    token_row = RefreshToken(
        user_id=user.id,
        token_hash=_hash_token(raw),
        family_id=family_id or uuid.uuid4(),
        created_at=now,
        expires_at=now + REFRESH_TOKEN_LIFETIME,
        revoked=False,
        user_agent=(user_agent or "")[:255] or None,
        client_ip=(client_ip or "")[:64] or None,
    )
    session.add(token_row)
    if commit:
        await session.commit()
        await session.refresh(token_row)
    else:
        # Assign the PK / server-side defaults without ending the
        # transaction — the caller owns the commit.
        await session.flush()
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


async def _lock_family(session: AsyncSession, family_id: uuid.UUID) -> None:
    """Take the per-family PostgreSQL advisory transaction lock.

    ``pg_advisory_xact_lock`` is held until the transaction that took it
    commits/rolls back. EVERY path that mutates a family's rows
    (``rotate``, ``revoke_family``, ``revoke_all_for_user``) takes THIS
    lock BEFORE its UPDATE, so they serialize against each other end to
    end. This closes the READ COMMITTED interleave where one path's
    snapshot misses a row another path is minting/revoking in a
    not-yet-committed transaction (e.g. a ``logout-all`` sweep running
    ``UPDATE ... WHERE revoked=False`` cannot see a ``rotate`` successor
    that is minted-but-not-committed, so that successor would survive the
    revocation and silently restore the session logout-all had to kill).

    ``hashtext(uuid::text)`` yields an int4 key, widened to the bigint
    the single-arg lock function takes. Contention is per-family only, so
    throughput is unaffected in the common case.
    """
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(str(family_id))))
    )


async def revoke_family(session: AsyncSession, family_id: uuid.UUID) -> int:
    """Revoke every token in the family. Returns the row count.

    Called when a replayed (already-revoked) refresh token is presented,
    or when the presenting user was deleted/deactivated: the attacker
    likely stole the cookie, so the whole session is burnt down even if
    individual rows looked valid.

    Takes the per-family advisory lock BEFORE the UPDATE (same lock
    ``rotate`` uses) so a concurrent rotate on this family cannot mint a
    successor invisible to this revocation's READ COMMITTED snapshot.
    This helper self-commits, so the lock is released here.
    """
    await _lock_family(session, family_id)
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

    Atomicity (post-3vr concurrency fix): the ENTIRE rotate runs in ONE
    transaction serialized by a per-family PostgreSQL advisory lock
    (``pg_advisory_xact_lock`` on ``hashtext(family_id)``). This closes
    an interleave the previous multi-commit shape left open under READ
    COMMITTED: a victim's replay-burn could scan the family for
    ``revoked=False`` rows while a concurrent attacker rotation was
    minting its successor in a not-yet-committed transaction; the
    freshly-minted token was invisible to the burn's snapshot and
    survived the sweep, defeating anti-replay. With every rotate on a
    family serialized end-to-end, the two operations can no longer
    overlap: whoever runs second sees the other's committed state (the
    burn sweeps the successor, or the successor's CAS finds the token
    already revoked and mints nothing). See
    ``test_concurrent_replay_burn_must_sweep_attacker_mint``.

    Timing: race-loss and replay paths run the SAME number of SQL
    statements (lookup + lock + CAS + SELECT + family-update + commit)
    so an attacker can't read latency to learn whether the cookie they
    hold was just rotated. The family-update in the race-loss path is a
    no-op (guarded by ``false()``) but takes the same wire time.
    """
    digest = _hash_token(raw_token)

    # Discover the presented token's family so we can take the per-family
    # advisory lock BEFORE any mutation. An unknown token has no family
    # to act on — return the same 401 as before without locking.
    presented = (
        await session.execute(
            select(RefreshToken.family_id).where(RefreshToken.token_hash == digest)
        )
    ).first()
    if presented is None:
        return None
    family_id = presented.family_id

    # Serialize every rotate() on this family, and against revoke_family /
    # revoke_all_for_user (they take the SAME lock). The lock is held until
    # THIS transaction commits/rolls back — which is why the CAS and the
    # mint below MUST share one transaction (no intermediate commit), and
    # why every return path past this point commits to release the lock
    # promptly. Deadlock is not possible: rotate takes EXACTLY ONE lock and
    # never requests a second while holding it, so it can never be a link
    # in a wait cycle (revoke_all takes N locks but in a globally sorted
    # order, and no path both holds this lock and waits on another lock
    # rotate could hold).
    await _lock_family(session, family_id)

    # Stamp ``now`` AFTER acquiring the advisory lock so ``revoked_at``
    # (CAS) and the should_burn age check reflect the post-serialization
    # instant, not the (possibly much earlier) pre-contention time. This
    # keeps the invariant that the successor's ``created_at`` (issue_token
    # stamps its OWN, even-later ``now`` post-CAS) is >= this ``revoked_at``
    # — so the replay sweep never mistakes a legit successor for a
    # pre-revocation row.
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
        # Mint the successor in the SAME transaction as the CAS
        # (``commit=False``), then commit both atomically. The advisory
        # lock is held across the whole unit, so a concurrent burn on
        # this family cannot interleave between the CAS and the mint.
        raw, token_row = await issue_token(
            session,
            user=user,
            family_id=winner.family_id,
            user_agent=user_agent,
            client_ip=client_ip,
            commit=False,
        )
        await session.commit()
        await session.refresh(token_row)
        return raw, token_row

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
        # information about an EXISTING family. Commit to release the
        # per-family advisory lock taken above.
        await session.commit()
        return None

    # Decide burn vs no-op based on revoked_at age. ``None`` legacy
    # rows from the pre-2.2 era are treated as replay (conservative).
    revoked_at = replay_row.revoked_at
    should_burn = revoked_at is None or (now - revoked_at) > RACE_WINDOW

    # Always run the family UPDATE. On a CONFIRMED replay (should_burn=True)
    # we burn EVERY still-active row in the family — no ``created_at`` filter.
    #
    # Why no ``created_at`` filter: a replay means the family is compromised
    # but we CANNOT tell attacker from victim. In the canonical stolen-cookie
    # chain the attacker rotates the stolen token FIRST, so the LIVE token is
    # the rotation successor whose ``created_at`` is stamped a few ms AFTER the
    # revocation (issue_token uses its own ``now`` post-CAS). A
    # ``created_at <= revoked_at`` filter would spare exactly that token,
    # leaving the attacker's session alive and making anti-replay a no-op on a
    # linear chain. The safe posture on a confirmed replay is: nuke the whole
    # family and force BOTH parties to re-authenticate. The prior filter only
    # ever mattered for should_burn=True, and its effect (sparing a concurrent
    # mint) is precisely the wrong call once a replay is confirmed.
    #
    # The should_burn=False branch (two-tab race within RACE_WINDOW) is
    # unchanged: the ``false()`` literal short-circuits the UPDATE to 0 rows,
    # so a legit race-loss still does NOT burn the family.
    #
    # KNOWN LIMITATION (documented by the 4th-layer review): when
    # ``should_burn=False`` the ``false()`` literal is constant-folded
    # by the PostgreSQL planner into a "One-Time Filter" that returns 0
    # rows without scanning the table — so the timing of the no-op
    # branch is measurably shorter than the burn branch in the same
    # datacenter. The attacker would need (a) co-location or thousands
    # of samples and (b) a stolen cookie already in hand to exploit
    # it, so the residual risk is below our threat model. Accepted.
    await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.family_id == replay_row.family_id,
            RefreshToken.revoked.is_(False),
            true() if should_burn else false(),
        )
        .values(revoked=True, revoked_at=now)
    )
    await session.commit()
    return None


async def revoke_all_for_user(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Revoke every non-revoked refresh token for the user.

    Caller commits or rolls back — the helper used to ``await
    session.commit()`` inside, but that broke atomicity when the
    caller needed to chain other writes (force-revoke endpoint bumps
    ``revocation_epoch`` + writes an ``audit_log`` row in the SAME
    transaction). 3vr Sonnet HIGH fix-forward on the F5-F follow-up:
    moved commit responsibility to the caller, so a failure in any
    chained step rolls back the whole operation, not just the steps
    after the implicit commit point.

    Advisory locking (multi-family): this is a user-wide sweep spanning
    EVERY active family. Before the UPDATE we SELECT DISTINCT the active
    families and take the per-family advisory lock on each, IN SORTED
    ORDER, so a concurrent ``rotate`` on any of those families cannot mint
    a successor invisible to this sweep's READ COMMITTED snapshot (the
    logout-all / force-revoke residual). Because the caller owns the
    commit, the XACT locks are held until the CALLER commits — covering
    the whole logout-all/force-revoke unit (including the
    ``revocation_epoch`` bump), so no rotate successor can slip through
    between this UPDATE and the epoch bump.

    Deadlock analysis: locks are acquired in a deterministic global order
    (``ORDER BY family_id``), so two concurrent ``revoke_all_for_user``
    calls acquire in the same order and cannot form a cycle. ``rotate``
    takes EXACTLY ONE lock and never waits on a second while holding it,
    so it can never close a wait cycle with this sweep either.

    TOCTOU note: ``rotate`` never creates NEW families (only ``login``
    with ``family_id=None`` does), so locking the user's EXISTING active
    families fully covers the rotate-in-flight threat. A login concurrent
    with this sweep that mints a brand-new family is a legitimately new
    session, out of scope for logout-all (which revokes what existed at
    call time).
    """
    family_rows = await session.execute(
        select(RefreshToken.family_id)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
        .distinct()
        .order_by(RefreshToken.family_id)
    )
    for (family_id,) in family_rows.all():
        await _lock_family(session, family_id)

    result = await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
        .values(revoked=True, revoked_at=datetime.now(tz=timezone.utc))
    )
    # ``rowcount`` is only on UPDATE/DELETE Results; mypy types the base
    # Result without it. The driver guarantees the attribute for the
    # statement shape we're using here, so the cast is safe.
    return int(getattr(result, "rowcount", 0) or 0)
