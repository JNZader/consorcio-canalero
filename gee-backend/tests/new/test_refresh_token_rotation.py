"""Tests for the rotating refresh-token service (``app.auth.refresh_tokens``).

Covers the security-critical service layer that had ZERO coverage:
  - ``issue_token``  — mints a family / chains into one
  - ``rotate``       — happy path: old row revoked, new row same family
  - replay detection — presenting an already-revoked token past the
    RACE_WINDOW burns the WHOLE family
  - concurrency grace window — a two-tab race (second presentation of
    the just-rotated token within RACE_WINDOW) fails auth but does
    NOT burn the family

Same style as ``test_force_revoke.py``: real async PostgreSQL session
against the testcontainers/TEST_DATABASE_URL engine, committed rows,
explicit cleanup (refresh_tokens cascade on user delete).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.auth.models import RefreshToken, User, UserRole
from app.auth.refresh_tokens import (
    RACE_WINDOW,
    find_active,
    issue_token,
    revoke_family,
    rotate,
)


def _make_session_factory():
    import os

    sync_url = os.environ["DATABASE_URL"]
    async_url = sync_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(async_url, echo=False)
    SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, SessionLocal


async def _seed_user(SessionLocal) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"rt-{uuid.uuid4().hex[:8]}@playwright.com",
        hashed_password="x" * 20,
        is_active=True,
        is_verified=True,
        is_superuser=False,
        role=UserRole.OPERADOR,
    )
    async with SessionLocal() as session:
        session.add(user)
        await session.commit()
    return user


async def _cleanup_users(SessionLocal, ids: list[uuid.UUID]) -> None:
    """refresh_tokens has ON DELETE CASCADE — deleting the user sweeps
    every token row the tests created."""
    from sqlalchemy import delete as sa_delete

    async with SessionLocal() as session:
        await session.execute(sa_delete(User).where(User.id.in_(ids)))
        await session.commit()


async def _get_row(SessionLocal, row_id: uuid.UUID) -> RefreshToken:
    async with SessionLocal() as session:
        return (
            await session.execute(
                select(RefreshToken).where(RefreshToken.id == row_id)
            )
        ).scalar_one()


async def _backdate(
    SessionLocal,
    *,
    revoked_row_id: uuid.UUID,
    active_row_id: uuid.UUID,
    delta: timedelta,
) -> None:
    """Simulate the passage of time after a legit rotation.

    Shifts the revoked row's ``revoked_at`` AND the successor row's
    ``created_at`` back by ``delta`` — both move together because in
    real life they were stamped at (almost) the same instant. This is
    what lets the replay test cross RACE_WINDOW without sleeping, and
    it keeps the successor INSIDE the family-burn sweep (the sweep
    filters ``created_at <= revoked_at`` of the replayed row).
    """
    async with SessionLocal() as session:
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.id == revoked_row_id)
            .values(revoked_at=RefreshToken.revoked_at - delta)
        )
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.id == active_row_id)
            .values(created_at=RefreshToken.created_at - delta)
        )
        await session.commit()


# ---------------------------------------------------------------------------
# issue_token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_issue_token_creates_active_family(test_engine):
    """Login path: fresh family, raw token resolvable via find_active,
    only the hash (never the raw value) is stored."""
    _ = test_engine
    engine, SessionLocal = _make_session_factory()
    user = await _seed_user(SessionLocal)

    try:
        async with SessionLocal() as session:
            raw, row = await issue_token(session, user=user)

        assert row.revoked is False
        assert row.family_id is not None
        assert row.user_id == user.id
        assert raw not in (row.token_hash or ""), "raw token must NOT be stored"
        assert row.expires_at > datetime.now(tz=timezone.utc)

        async with SessionLocal() as session:
            found = await find_active(session, raw)
            assert found is not None
            assert found.id == row.id
    finally:
        await _cleanup_users(SessionLocal, [user.id])
        await engine.dispose()


# ---------------------------------------------------------------------------
# rotate — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rotate_valid_token_revokes_old_and_issues_new(test_engine):
    """(a) rotate() with a valid token → old row revoked, new token
    minted in the SAME family, and only the new raw value works."""
    _ = test_engine
    engine, SessionLocal = _make_session_factory()
    user = await _seed_user(SessionLocal)

    try:
        async with SessionLocal() as session:
            raw1, row1 = await issue_token(session, user=user)

        async with SessionLocal() as session:
            rotated = await rotate(session, raw_token=raw1, user=user)

        assert rotated is not None, "valid token must rotate successfully"
        raw2, row2 = rotated
        assert raw2 != raw1
        assert row2.family_id == row1.family_id, "rotation chains the family"
        assert row2.revoked is False

        # Old row is now revoked with a revocation timestamp.
        old = await _get_row(SessionLocal, row1.id)
        assert old.revoked is True
        assert old.revoked_at is not None

        # The new raw value authenticates; find_active surfaces the
        # old one as revoked (the replay signal for the caller).
        async with SessionLocal() as session:
            assert (await find_active(session, raw2)) is not None
            stale = await find_active(session, raw1)
            assert stale is not None and stale.revoked is True
    finally:
        await _cleanup_users(SessionLocal, [user.id])
        await engine.dispose()


@pytest.mark.asyncio
async def test_rotate_unknown_token_returns_none_without_side_effects(test_engine):
    """A token that never existed → None, and nothing gets revoked."""
    _ = test_engine
    engine, SessionLocal = _make_session_factory()
    user = await _seed_user(SessionLocal)

    try:
        async with SessionLocal() as session:
            raw1, row1 = await issue_token(session, user=user)

        async with SessionLocal() as session:
            result = await rotate(session, raw_token="never-issued-token", user=user)
        assert result is None

        # The legit token is untouched.
        fresh = await _get_row(SessionLocal, row1.id)
        assert fresh.revoked is False
        _ = raw1
    finally:
        await _cleanup_users(SessionLocal, [user.id])
        await engine.dispose()


# ---------------------------------------------------------------------------
# rotate — replay detection (family burn)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replay_after_race_window_burns_family_siblings(test_engine):
    """(b) Presenting a token that was ALREADY rotated, past the
    RACE_WINDOW, is a replay (stolen cookie) → rotate() returns None
    and the family-burn sweep revokes EVERY still-active token in the
    family — pre-rotation siblings AND the rotation successor.

    Security posture (fixed): a confirmed replay means the family is
    compromised and we cannot tell attacker from victim, so we nuke the
    whole family and force re-authentication. There is NO ``created_at``
    filter — the successor of the winning rotation (which, in a
    stolen-cookie chain where the attacker rotated first, is the
    attacker's LIVE token) MUST be burned too. See
    ``test_replay_burns_attacker_active_token_linear_chain``.
    """
    _ = test_engine
    engine, SessionLocal = _make_session_factory()
    user = await _seed_user(SessionLocal)

    try:
        # Legit lifecycle: login → an extra active token in the SAME
        # family (pre-rotation sibling) → rotation.
        async with SessionLocal() as session:
            raw1, row1 = await issue_token(session, user=user)
        async with SessionLocal() as session:
            _raw_sib, sibling = await issue_token(
                session, user=user, family_id=row1.family_id
            )
        async with SessionLocal() as session:
            rotated = await rotate(session, raw_token=raw1, user=user)
        assert rotated is not None
        _raw2, row2 = rotated

        # Simulate time passing well beyond the grace window: shift
        # the replayed row's revoked_at back, and push the sibling's
        # created_at earlier still so it sits inside the sweep window.
        await _backdate(
            SessionLocal,
            revoked_row_id=row1.id,
            active_row_id=row2.id,
            delta=RACE_WINDOW + timedelta(seconds=30),
        )
        async with SessionLocal() as session:
            await session.execute(
                update(RefreshToken)
                .where(RefreshToken.id == sibling.id)
                .values(
                    created_at=RefreshToken.created_at
                    - (RACE_WINDOW + timedelta(seconds=60))
                )
            )
            await session.commit()

        # Attacker replays the OLD raw token.
        async with SessionLocal() as session:
            replay = await rotate(session, raw_token=raw1, user=user)
        assert replay is None, "replayed token must never mint a new one"

        # The active sibling that existed before the rotation is burnt.
        swept = await _get_row(SessionLocal, sibling.id)
        assert swept.revoked is True, (
            "family burn must revoke active tokens created before the "
            "replayed token's revocation"
        )

        # The post-rotation successor is ALSO burned: a confirmed replay
        # nukes the whole family regardless of created_at (see docstring).
        successor = await _get_row(SessionLocal, row2.id)
        assert successor.revoked is True
    finally:
        await _cleanup_users(SessionLocal, [user.id])
        await engine.dispose()


@pytest.mark.asyncio
async def test_replay_burns_attacker_active_token_linear_chain(test_engine):
    """THEFT SCENARIO (anti-replay must revoke the attacker's live token).

    Canonical stolen-cookie chain:
      1. Victim holds T0 (raw1). Attacker steals the T0 cookie.
      2. Attacker rotates T0 FIRST → T0 revoked (revoked_at=rA), attacker
         receives T1 (row2) with created_at=cA a few ms AFTER rA (issue_token
         stamps its own ``now`` post-CAS). T1 is the attacker's LIVE token.
      3. Time passes past RACE_WINDOW.
      4. Victim's browser (still holding T0) hits /refresh → replay detected,
         should_burn=True → family burn MUST kill T1.

    If the family burn spares T1 (because cA > burn_threshold), the attacker's
    live token survives and anti-replay is a no-op on a linear chain.
    """
    _ = test_engine
    engine, SessionLocal = _make_session_factory()
    user = await _seed_user(SessionLocal)

    try:
        # Victim logs in → T0.
        async with SessionLocal() as session:
            raw1, row1 = await issue_token(session, user=user)

        # Attacker rotates the stolen T0 FIRST → attacker holds T1 (row2).
        async with SessionLocal() as session:
            rotated = await rotate(session, raw_token=raw1, user=user)
        assert rotated is not None
        _raw2_attacker, row2 = rotated  # attacker's LIVE token

        # Time passes beyond the grace window. Shift revoked_at (rA) and the
        # successor's created_at (cA) back together — realistic: they were
        # stamped ~simultaneously, so cA stays a few ms AFTER rA.
        await _backdate(
            SessionLocal,
            revoked_row_id=row1.id,
            active_row_id=row2.id,
            delta=RACE_WINDOW + timedelta(seconds=30),
        )

        # Victim presents the still-held T0 → replay.
        async with SessionLocal() as session:
            replay = await rotate(session, raw_token=raw1, user=user)
        assert replay is None, "replayed token must never mint a new one"

        # SECURITY ASSERTION: the attacker's live token must be revoked.
        attacker_token = await _get_row(SessionLocal, row2.id)
        assert attacker_token.revoked is True, (
            "family burn on a confirmed replay must revoke the attacker's "
            "live token (the rotation successor), not spare it"
        )
    finally:
        await _cleanup_users(SessionLocal, [user.id])
        await engine.dispose()


# ---------------------------------------------------------------------------
# rotate — concurrent grace window (two-tab race)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_second_presentation_within_race_window_does_not_burn(test_engine):
    """(c) Two-tab race: the SAME raw token presented again immediately
    after a successful rotation (revoked_at within RACE_WINDOW) loses
    auth (None) but must NOT burn the family — the tab that won keeps
    its fresh token."""
    _ = test_engine
    engine, SessionLocal = _make_session_factory()
    user = await _seed_user(SessionLocal)

    try:
        async with SessionLocal() as session:
            raw1, _row1 = await issue_token(session, user=user)

        # Tab A wins the rotation.
        async with SessionLocal() as session:
            rotated = await rotate(session, raw_token=raw1, user=user)
        assert rotated is not None
        raw2, row2 = rotated

        # Tab B presents the same (now-revoked) token right away —
        # revoked_at is fresh, well inside the 5 s RACE_WINDOW.
        async with SessionLocal() as session:
            loser = await rotate(session, raw_token=raw1, user=user)
        assert loser is None, "race loser must not get a token"

        # The family survived: tab A's token is still active and
        # still authenticates.
        winner_row = await _get_row(SessionLocal, row2.id)
        assert winner_row.revoked is False, (
            "race-loss within RACE_WINDOW must NOT burn the family"
        )
        async with SessionLocal() as session:
            still_valid = await find_active(session, raw2)
            assert still_valid is not None and still_valid.revoked is False
    finally:
        await _cleanup_users(SessionLocal, [user.id])
        await engine.dispose()


# ---------------------------------------------------------------------------
# revoke_family
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_family_revokes_every_active_row(test_engine):
    """Direct family kill-switch: every non-revoked row in the family
    flips to revoked; rows of OTHER families are untouched."""
    _ = test_engine
    engine, SessionLocal = _make_session_factory()
    user = await _seed_user(SessionLocal)

    try:
        family = uuid.uuid4()
        async with SessionLocal() as session:
            _rawA, rowA = await issue_token(session, user=user, family_id=family)
        async with SessionLocal() as session:
            _rawB, rowB = await issue_token(session, user=user, family_id=family)
        async with SessionLocal() as session:
            _rawC, rowC = await issue_token(session, user=user)  # other family

        async with SessionLocal() as session:
            count = await revoke_family(session, family)
        assert count == 2

        assert (await _get_row(SessionLocal, rowA.id)).revoked is True
        assert (await _get_row(SessionLocal, rowB.id)).revoked is True
        assert (await _get_row(SessionLocal, rowC.id)).revoked is False
    finally:
        await _cleanup_users(SessionLocal, [user.id])
        await engine.dispose()
