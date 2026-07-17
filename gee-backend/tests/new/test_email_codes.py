"""Phase 5 / F5-E — tests for the SMTP-body code substrate.

The contract:
  - ``create_code_for_token`` returns a unique 8-char uppercase
    alphanumeric code, persists the mapping with a 15-min TTL.
  - ``exchange_code_for_token`` returns the token ONLY on the
    happy path (valid + matching purpose + not expired + not
    consumed), ``None`` everywhere else.
  - Failure paths return ``None`` consistently — no leak between
    "never existed" and "already used" so enumeration is blind.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.auth.email_codes import (
    CODE_ALPHABET,
    CODE_LENGTH,
    EmailCode,
    RESET_PURPOSE,
    VERIFY_PURPOSE,
    create_code_for_token,
    exchange_code_for_token,
    generate_short_code,
)
from app.auth.models import User, UserRole


# ---------------------------------------------------------------------------
# generate_short_code
# ---------------------------------------------------------------------------


def test_generate_short_code_default_length():
    code = generate_short_code()
    assert len(code) == CODE_LENGTH


def test_generate_short_code_only_uses_alphabet():
    for _ in range(100):
        code = generate_short_code()
        assert all(c in CODE_ALPHABET for c in code), (
            f"code {code!r} contains chars outside the documented alphabet"
        )


def test_generate_short_code_high_entropy():
    """Sanity: 100 calls produce 100 distinct codes — confirms we're
    not hitting a tiny PRNG cycle. Collisions in 2.8T-combo space
    are astronomically unlikely."""
    codes = {generate_short_code() for _ in range(100)}
    assert len(codes) == 100


# ---------------------------------------------------------------------------
# Integration tests with the DB (use ``db`` fixture from conftest)
# ---------------------------------------------------------------------------


async def _seed_user_async(SessionLocal) -> User:
    """Create a User via the async session so the DB row commits in
    the same transaction context the async test uses. Mixing sync
    + async sessions breaks because each one runs its own
    transaction and the FK to ``users.id`` isn't visible."""
    user = User(
        id=uuid.uuid4(),
        email=f"f5e-test-{uuid.uuid4().hex[:8]}@playwright.com",
        hashed_password="x" * 20,
        is_active=True,
        is_verified=False,
        is_superuser=False,
        role=UserRole.CIUDADANO,
    )
    async with SessionLocal() as session:
        session.add(user)
        await session.commit()
    return user


async def _cleanup_user_async(SessionLocal, user_id: uuid.UUID) -> None:
    """Counterpart to ``_seed_user_async`` — drop the user (cascade
    cleans email_codes rows)."""
    from sqlalchemy import delete as sa_delete

    async with SessionLocal() as session:
        await session.execute(sa_delete(User).where(User.id == user_id))
        await session.commit()


def _make_session_factory():
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    import os

    sync_url = os.environ["DATABASE_URL"]
    async_url = sync_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(async_url, echo=False)
    SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, SessionLocal


@pytest.mark.asyncio
async def test_create_code_persists_row(test_engine):
    _ = test_engine  # force schema creation before the async engine connects
    engine, SessionLocal = _make_session_factory()
    user = await _seed_user_async(SessionLocal)
    try:
        async with SessionLocal() as session:
            code = await create_code_for_token(
                session,
                user=user,
                purpose=VERIFY_PURPOSE,
                token="fake-jwt-token-payload",
            )
            await session.commit()

        assert len(code) == CODE_LENGTH

        async with SessionLocal() as session:
            row = (
                await session.execute(select(EmailCode).where(EmailCode.code == code))
            ).scalar_one()
            assert row.purpose == VERIFY_PURPOSE
            assert row.token == "fake-jwt-token-payload"
            assert row.user_id == user.id
            assert row.consumed_at is None
            assert row.expires_at > datetime.now(tz=timezone.utc)
    finally:
        await _cleanup_user_async(SessionLocal, user.id)
        await engine.dispose()


@pytest.mark.asyncio
async def test_exchange_happy_path_returns_token(test_engine):
    _ = test_engine
    engine, SessionLocal = _make_session_factory()
    user = await _seed_user_async(SessionLocal)
    try:
        async with SessionLocal() as session:
            code = await create_code_for_token(
                session,
                user=user,
                purpose=RESET_PURPOSE,
                token="real-reset-token-value",
            )
            await session.commit()

        async with SessionLocal() as session:
            result = await exchange_code_for_token(session, code=code, purpose=RESET_PURPOSE)
            await session.commit()
        assert result == "real-reset-token-value"

        # Second exchange must fail — one-shot semantics.
        async with SessionLocal() as session:
            again = await exchange_code_for_token(session, code=code, purpose=RESET_PURPOSE)
        assert again is None
    finally:
        await _cleanup_user_async(SessionLocal, user.id)
        await engine.dispose()


@pytest.mark.asyncio
async def test_exchange_wrong_purpose_returns_none(test_engine):
    """A verify code can NOT be used to satisfy a reset endpoint, even
    if the same string somehow leaks."""
    _ = test_engine
    engine, SessionLocal = _make_session_factory()
    user = await _seed_user_async(SessionLocal)
    try:
        async with SessionLocal() as session:
            code = await create_code_for_token(
                session,
                user=user,
                purpose=VERIFY_PURPOSE,
                token="verify-token-X",
            )
            await session.commit()

        async with SessionLocal() as session:
            result = await exchange_code_for_token(session, code=code, purpose=RESET_PURPOSE)
        assert result is None, (
            "Cross-purpose use of a code must fail — otherwise the "
            "verify code could be swapped into the reset flow."
        )
    finally:
        await _cleanup_user_async(SessionLocal, user.id)
        await engine.dispose()


@pytest.mark.asyncio
async def test_exchange_unknown_code_returns_none(test_engine):
    """Bogus code → ``None``, indistinguishable from an expired code."""
    _ = test_engine
    engine, SessionLocal = _make_session_factory()
    try:
        async with SessionLocal() as session:
            result = await exchange_code_for_token(session, code="NEVERWAS", purpose=VERIFY_PURPOSE)
        assert result is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_exchange_invalid_purpose_returns_none():
    """Defensive: a malformed ``purpose`` (typo / SQL inject attempt /
    URL-encoded junk) doesn't match the allow-list and returns None."""
    engine, SessionLocal = _make_session_factory()
    try:
        async with SessionLocal() as session:
            result = await exchange_code_for_token(
                session, code="ANYCODEZ", purpose="something-else"
            )
        assert result is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_create_code_rejects_invalid_purpose():
    """Library-layer: ``create_code_for_token`` raises ValueError on
    a bad purpose instead of writing junk to the DB. We don't even
    touch the DB to assert this — the validation runs before the SQL."""
    engine, SessionLocal = _make_session_factory()
    try:
        async with SessionLocal() as session:
            with pytest.raises(ValueError, match="purpose must be one of"):
                await create_code_for_token(
                    session,
                    user=User(
                        id=uuid.uuid4(),
                        email="x@playwright.com",
                        hashed_password="x",
                        is_active=True,
                        is_verified=False,
                        is_superuser=False,
                        role=UserRole.CIUDADANO,
                    ),
                    purpose="not-a-real-purpose",
                    token="anything",
                )
    finally:
        await engine.dispose()
