"""Phase 5 / F5-F — tests for RevocableJWTStrategy + revocation_epoch.

The closure of the 15-min residual access-token window after a
``/auth/jwt/logout-all`` invocation is the load-bearing security
property here. We pin three invariants:

  1. A token issued AT epoch=N is accepted when the user is still
     at epoch=N. (Happy path — no regression on normal traffic.)

  2. A token issued AT epoch=N is REJECTED when the user has been
     bumped to epoch=N+1 (i.e. logout-all). The 15-min residual
     window is now zero.

  3. The token claim defaults to 0 when ``write_token`` runs against
     a user whose ``revocation_epoch`` is the schema default — so
     existing pre-migration tokens (no embedded epoch claim) are
     still treated as epoch=0 and pass against any user still at
     epoch=0. This is the backwards-compat hatch the F5-F migration
     relies on.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.auth.dependencies import RevocableJWTStrategy
from app.auth.models import User, UserRole


def _make_user(epoch: int = 0) -> User:
    """A minimal User instance. We do NOT touch the DB — the JWT
    strategy reads only ``id`` (through ``user_manager.get``) and
    ``revocation_epoch`` (directly via attribute access)."""
    user = User(
        id=uuid.uuid4(),
        email=f"epoch-{uuid.uuid4().hex[:8]}@playwright.com",
        hashed_password="x" * 20,
        is_active=True,
        is_verified=True,
        is_superuser=False,
        role=UserRole.OPERADOR,
        revocation_epoch=epoch,
    )
    return user


def _make_manager(user: User) -> MagicMock:
    """Stand-in for ``BaseUserManager`` — ``read_token`` only needs
    ``parse_id`` (return the UUID as-is) and ``get`` (return the
    user). Both await-able through AsyncMock."""
    mgr = MagicMock()
    mgr.parse_id = lambda raw: uuid.UUID(raw)
    mgr.get = AsyncMock(return_value=user)
    return mgr


@pytest.mark.asyncio
async def test_token_with_matching_epoch_is_accepted():
    user = _make_user(epoch=0)
    mgr = _make_manager(user)
    strategy = RevocableJWTStrategy(secret="test-secret-32-chars-min", lifetime_seconds=60)

    token = await strategy.write_token(user)
    result = await strategy.read_token(token, mgr)

    assert result is not None
    assert result.id == user.id


@pytest.mark.asyncio
async def test_token_issued_before_logout_all_is_rejected():
    """Core property: token at epoch=0 against user now at epoch=1
    must be rejected even though the JWT signature + expiry are valid.
    This is what closes the 15-min residual window."""
    user = _make_user(epoch=0)
    strategy = RevocableJWTStrategy(secret="test-secret-32-chars-min", lifetime_seconds=60)

    # Issue at epoch=0, then bump the user (simulates logout-all).
    token = await strategy.write_token(user)
    user.revocation_epoch = 1
    mgr = _make_manager(user)

    result = await strategy.read_token(token, mgr)
    assert result is None, (
        "Token issued before logout-all must be rejected once the "
        "user's revocation_epoch advances past the embedded claim."
    )


@pytest.mark.asyncio
async def test_user_bumped_then_new_token_works():
    """The NEW token issued AFTER the bump must be accepted — the
    rejection only applies to stale tokens, not the user."""
    user = _make_user(epoch=0)
    strategy = RevocableJWTStrategy(secret="test-secret-32-chars-min", lifetime_seconds=60)

    user.revocation_epoch = 7  # Some accumulated history of logout-alls.
    token = await strategy.write_token(user)
    mgr = _make_manager(user)

    result = await strategy.read_token(token, mgr)
    assert result is not None
    assert result.id == user.id


@pytest.mark.asyncio
async def test_token_without_epoch_claim_treated_as_zero():
    """Backwards-compat: a token issued BEFORE F5-F landed has no
    ``epoch`` claim. The strategy defaults the missing claim to 0,
    so against a user still at epoch=0 (the schema default) it must
    pass. Otherwise every existing user gets logged out on F5-F
    deploy day. This test forges such a legacy token by hand."""
    from fastapi_users.jwt import generate_jwt

    user = _make_user(epoch=0)
    mgr = _make_manager(user)
    strategy = RevocableJWTStrategy(secret="test-secret-32-chars-min", lifetime_seconds=60)

    # Same shape as the pre-F5-F payload — sub + aud, no epoch.
    legacy_token = generate_jwt(
        {"sub": str(user.id), "aud": strategy.token_audience},
        strategy.encode_key,
        strategy.lifetime_seconds,
        algorithm=strategy.algorithm,
    )

    result = await strategy.read_token(legacy_token, mgr)
    assert result is not None, (
        "Legacy tokens (no ``epoch`` claim) must keep working until "
        "their natural expiry on a fresh F5-F deploy."
    )


@pytest.mark.asyncio
async def test_get_jwt_strategy_dependency_returns_revocable_subclass():
    """3vr Opus-alt HIGH fix-forward: the unit tests above instantiate
    ``RevocableJWTStrategy`` directly. A future bug where
    ``get_jwt_strategy()`` accidentally returns the base ``JWTStrategy``
    would not be caught — the unit tests would still pass against the
    detached subclass. Lock the DI wiring so a regression in
    ``app/auth/dependencies.py:get_jwt_strategy`` fails this test."""
    from app.auth.dependencies import get_jwt_strategy

    strat = get_jwt_strategy()
    assert isinstance(strat, RevocableJWTStrategy), (
        "get_jwt_strategy() must return the F5-F-aware subclass — "
        "otherwise the epoch claim is never written/read and the "
        "15-min residual window is back."
    )

    # Issue a token and verify the ``epoch`` claim is actually in the
    # payload. Catches the parallel bug shape where ``write_token``
    # forgets to embed the claim.
    from fastapi_users.jwt import decode_jwt

    user = _make_user(epoch=3)
    token = await strat.write_token(user)
    payload = decode_jwt(
        token, strat.decode_key, strat.token_audience, algorithms=[strat.algorithm]
    )
    assert "epoch" in payload, "Issued JWT must carry the ``epoch`` claim."
    assert payload["epoch"] == 3, (
        f"epoch claim should match user.revocation_epoch at issue time, got {payload['epoch']!r}"
    )


@pytest.mark.asyncio
async def test_invalid_token_still_rejected_normally():
    """The new epoch check must not weaken the existing JWT validation
    — a tampered token still fails on signature, not on epoch."""
    user = _make_user(epoch=0)
    mgr = _make_manager(user)
    strategy = RevocableJWTStrategy(secret="test-secret-32-chars-min", lifetime_seconds=60)

    # Token signed with a DIFFERENT secret.
    other_strategy = RevocableJWTStrategy(
        secret="some-other-secret-32+chars-X", lifetime_seconds=60
    )
    bad_token = await other_strategy.write_token(user)

    result = await strategy.read_token(bad_token, mgr)
    assert result is None
