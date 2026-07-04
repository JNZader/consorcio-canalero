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

from sqlalchemy import false, func, text, true, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.auth.models import RefreshToken, User
from app.shared.audit_log import write_audit_entry_async


# 30-day lifetime — long enough that a daily-active user never sees a
# re-login, short enough that a stolen cookie has bounded value.
REFRESH_TOKEN_LIFETIME = timedelta(days=30)


# Defense-in-depth (T1): bound how long any family-mutating path waits on the
# per-family advisory lock. Without a cap, a slow ``revoke_all_for_user``
# (logout-all / force-revoke) holding a family's XACT lock could block a
# concurrent ``rotate`` on that family indefinitely. 5 s is far beyond the
# sub-second two-tab race window, so a legitimate contender never trips it;
# anything longer is pathological and better failed than hung. Applied via
# ``SET LOCAL`` (transaction-scoped) so the GLOBAL ``lock_timeout`` config —
# and every other query's behaviour — is left untouched.
_LOCK_TIMEOUT_MS = 5000

# PostgreSQL SQLSTATE raised when ``lock_timeout`` fires on a lock wait
# (``lock_not_available``). VERIFIED EMPIRICALLY (not guessed): SQLAlchemy
# surfaces it as ``sqlalchemy.exc.DBAPIError`` — NOT ``OperationalError`` —
# whose ``.orig`` (the asyncpg dialect adapter ``Error``) carries
# ``.sqlstate == "55P03"``; the underlying asyncpg cause is
# ``asyncpg.exceptions.LockNotAvailableError``. Matching on the CLASS
# ``OperationalError`` would silently miss it, so we match on sqlstate.
_LOCK_NOT_AVAILABLE_SQLSTATE = "55P03"

# T3: defensive cap on the lock→re-SELECT loop in ``revoke_all_for_user``.
# Bounds the (adversarial) case where an attacker spams concurrent logins to
# keep minting fresh families between iterations. On hitting the cap we fall
# back to the user-wide UPDATE without having locked the very last batch of
# families — i.e. the pre-fix READ COMMITTED behaviour for those families
# only. Documented and accepted (see ``revoke_all_for_user``).
_REVOKE_ALL_LOCK_MAX_ITERS = 10


def _is_lock_timeout(exc: DBAPIError) -> bool:
    """True when ``exc`` is ``lock_timeout`` firing on an advisory-lock wait.

    Matches on SQLSTATE (``55P03``) rather than the exception class: SQLAlchemy
    raises the base ``DBAPIError`` here, NOT ``OperationalError``, so an
    ``isinstance(exc, OperationalError)`` guard would silently miss it (verified
    empirically). ``.orig`` is the asyncpg adapter ``Error`` exposing
    ``.sqlstate``.
    """
    return (
        getattr(getattr(exc, "orig", None), "sqlstate", None)
        == _LOCK_NOT_AVAILABLE_SQLSTATE
    )


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

    T1 (defense-in-depth): bound the wait with ``SET LOCAL lock_timeout``
    BEFORE acquiring the lock. ``SET LOCAL`` is transaction-scoped (reverts at
    commit/rollback) so it never leaks into the global config or other queries;
    it must run in the SAME transaction as the lock to take effect — verified:
    ``SET LOCAL lock_timeout`` followed by ``pg_advisory_xact_lock`` in one tx
    makes the lock honour the timeout (SQLSTATE 55P03 on expiry). Re-running it
    on each acquisition (e.g. the ``revoke_all_for_user`` loop) is idempotent.
    """
    await session.execute(text(f"SET LOCAL lock_timeout = '{_LOCK_TIMEOUT_MS}'"))
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

    T1 note: ``_lock_family`` sets a bounded ``lock_timeout``. If the family
    lock cannot be taken in time, the resulting ``DBAPIError`` (SQLSTATE
    55P03) is deliberately NOT caught here — a family kill-switch that could
    not take its lock MUST fail loudly rather than silently leave tokens
    alive. The caller sees the error and can retry.
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
    try:
        await _lock_family(session, family_id)
    except DBAPIError as exc:
        if _is_lock_timeout(exc):
            # T1: could not take the family lock within _LOCK_TIMEOUT_MS (a
            # slow logout-all / force-revoke likely holds it). Fail SAFE:
            # roll back the now-aborted transaction and return None so the
            # caller emits 401 and the client re-authenticates. Forcing a
            # re-login under contention is the correct fail-secure posture —
            # far better than hanging the request on an unbounded lock wait.
            await session.rollback()
            return None
        raise

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
        .returning(
            RefreshToken.id,
            RefreshToken.family_id,
            # T2: pull the OLD row's client fingerprint so the winner path can
            # compare it against THIS request's UA/IP (log-only anomaly check).
            RefreshToken.user_agent,
            RefreshToken.client_ip,
        )
    )
    winner = cas_result.first()
    if winner is not None:
        # T2 (observability, log-only — NEVER auto-revoke): if the client
        # fingerprint on THIS legitimate rotation differs from the one
        # persisted on the token being rotated, record an audit event. This
        # deliberately does NOT revoke or alter the flow: auto-revoking on
        # UA/IP drift causes false-positive logouts on mobile / rural / CGNAT
        # networks (roaming IPs, UA changes on app upgrade) — the user's
        # explicit decision. The audit row rides the SAME rotate transaction
        # (write_audit_entry_async only ``session.add``s it; the commit below
        # persists it atomically), so it neither breaks rotate's atomicity nor
        # adds more than one buffered INSERT. Normalise the incoming values
        # with issue_token's own rule ((x or "")[:len] or None) so an empty ""
        # header does not read as a change against a stored NULL.
        new_ua = (user_agent or "")[:255] or None
        new_ip = (client_ip or "")[:64] or None
        ua_changed = new_ua != winner.user_agent
        ip_changed = new_ip != winner.client_ip
        if ua_changed or ip_changed:
            changed = "+".join(
                part
                for part, flag in (("ua", ua_changed), ("ip", ip_changed))
                if flag
            )
            # Resource records user (via user_id), family, what changed, and
            # old vs new UA/IP. NEVER the raw token or its hash. Bounded to
            # 512 chars by the helper.
            await write_audit_entry_async(
                session,
                user_id=user.id,
                action="refresh.rotate.client-change",
                resource=(
                    f"family_id={family_id} changed={changed} "
                    f"old_ua={winner.user_agent!r} new_ua={new_ua!r} "
                    f"old_ip={winner.client_ip} new_ip={new_ip}"
                ),
                client_ip=new_ip,
            )

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

    Advisory locking (multi-family, T3 loop): this is a user-wide sweep
    spanning EVERY active family. The UPDATE is intentionally user-wide
    (``WHERE user_id AND revoked=False``) — NOT narrowed to a pre-computed
    family set — so it cannot miss a family. But to close the residual where a
    family born (via a concurrent login) AFTER a single family SELECT would be
    revoked WITHOUT its advisory lock held — reopening the READ COMMITTED
    rotate-in-flight miss for THAT family — we lock in a LOOP:

      1. SELECT DISTINCT active families (``ORDER BY family_id``).
      2. Lock the ones we do not already hold, in ascending ``family_id``.
      3. Re-SELECT; if new families appeared, go back to (2).
      4. Stop when a SELECT surfaces no new (unlocked) family — RECIÉN THEN
         run the user-wide UPDATE, with EVERY active family locked, so no
         concurrent rotate can mint an invisible successor in any of them.

    Because the caller owns the commit, the XACT locks are held until the
    CALLER commits — covering the whole logout-all / force-revoke unit
    (including the ``revocation_epoch`` bump).

    Termination: rotate never creates NEW families (only ``login`` with
    ``family_id=None`` does) and, once a family is locked, no concurrent rotate
    can mint a fresh successor in it. So the ONLY source of new families across
    iterations is concurrent logins — bounded under any honest client, so the
    loop converges in 1-2 passes. An adversary spamming logins is bounded by
    ``_REVOKE_ALL_LOCK_MAX_ITERS``: on hitting the cap we proceed to the
    user-wide UPDATE anyway; the last batch of families may be revoked without
    their lock (the pre-fix behaviour for those few families only). Accepted.

    Deadlock analysis: within a single pass we acquire in ascending
    ``family_id`` order and never release (advisory XACT locks are re-entrant
    per session; we skip already-held ones only to avoid inflating the lock
    counter). ``rotate`` and ``revoke_family`` take EXACTLY ONE lock, so they
    can never close a cycle against this sweep.

    KNOWN, ACCEPTED residual (PoC-confirmed, LOW): the re-SELECT loop CAN
    invert the global lock order ACROSS passes. If a family is born late with a
    ``family_id`` smaller than one this session already holds, and a SECOND
    same-user sweep (e.g. user logout-all racing an admin force-revoke) holds
    that smaller family and wants ours, the two form a cycle. When this rare
    interleave happens, PostgreSQL's deadlock detector (``deadlock_timeout``,
    ~1s, fires BEFORE T1's 5s ``lock_timeout``) aborts one side with SQLSTATE
    ``40P01``. There is NO retry: that ``40P01`` propagates as a ``DBAPIError``
    → HTTP 500 for the losing caller (note ``_is_lock_timeout`` matches 55P03
    only, NOT 40P01 — this is deliberate: a kill-switch deadlock must surface,
    not be swallowed). This is a COSMETIC availability blemish, not a security
    hole: the final UPDATE is user-wide (revokes every non-revoked row for the
    user regardless of which families got locked), so the WINNING sweep still
    kills every token — the loser's 500 leaves no token alive. Closing the 500
    would require a per-user serialization lock (serialize same-user sweeps
    before taking per-family locks); deferred as not worth the added protocol
    for a fails-safe, ~1s-bounded, rare edge.

    TOCTOU note: a login concurrent with this sweep that mints a brand-new
    family AFTER the loop's final SELECT is a legitimately new session, out of
    scope for logout-all (which revokes what existed at call time).
    """
    locked: set[uuid.UUID] = set()
    for _ in range(_REVOKE_ALL_LOCK_MAX_ITERS):
        family_rows = await session.execute(
            select(RefreshToken.family_id)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
            .distinct()
            .order_by(RefreshToken.family_id)
        )
        new_families = [fid for (fid,) in family_rows.all() if fid not in locked]
        if not new_families:
            break
        # Ascending order preserves global lock ordering for deadlock-freedom
        # (see docstring). Skip already-held families to avoid re-locking.
        for family_id in sorted(new_families):
            await _lock_family(session, family_id)
            locked.add(family_id)

    result = await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
        .values(revoked=True, revoked_at=datetime.now(tz=timezone.utc))
    )
    # ``rowcount`` is only on UPDATE/DELETE Results; mypy types the base
    # Result without it. The driver guarantees the attribute for the
    # statement shape we're using here, so the cast is safe.
    return int(getattr(result, "rowcount", 0) or 0)
