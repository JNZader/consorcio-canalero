"""Phase 5 / F5-F follow-up — tests for admin force-revoke endpoint.

The endpoint is the admin-side counterpart to ``/auth/jwt/logout-all``:
admin revokes ALL sessions + refresh tokens for a target user, with
an audit_log entry tying the action back to the admin who did it.

Contract being pinned:
  - Target user's ``revocation_epoch`` increments by exactly 1.
  - Every non-revoked refresh token for the target is marked revoked.
  - An ``audit_log`` row is written with action=``user.force-revoke``,
    resource=``user_id=<target>``, user_id=acting admin.
  - Self-revoke is refused (admin must use /auth/jwt/logout-all).
  - 404 if the target user doesn't exist (we DON'T mask to 400 here
    because admins are trusted callers, not anonymous).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.auth.models import User, UserRole
from app.auth.refresh_tokens import RefreshToken
from app.shared.audit_log import AuditLog


def _make_session_factory():
    import os

    sync_url = os.environ["DATABASE_URL"]
    async_url = sync_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(async_url, echo=False)
    SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, SessionLocal


async def _seed_user(SessionLocal, role: UserRole) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"f5fr-{role.value}-{uuid.uuid4().hex[:8]}@playwright.com",
        hashed_password="x" * 20,
        is_active=True,
        is_verified=True,
        is_superuser=False,
        role=role,
    )
    async with SessionLocal() as session:
        session.add(user)
        await session.commit()
    return user


async def _seed_refresh_token(SessionLocal, user_id: uuid.UUID) -> uuid.UUID:
    """Plant one non-revoked refresh token for the target user so the
    "tokens revoked" branch has something to act on."""
    import hashlib

    raw = uuid.uuid4().hex
    digest = hashlib.sha256(raw.encode()).hexdigest()
    row = RefreshToken(
        id=uuid.uuid4(),
        user_id=user_id,
        family_id=uuid.uuid4(),
        token_hash=digest,
        expires_at=datetime.now(tz=timezone.utc) + timedelta(days=30),
        revoked=False,
    )
    async with SessionLocal() as session:
        session.add(row)
        await session.commit()
    return row.id


async def _cleanup_users(SessionLocal, ids: list[uuid.UUID]) -> None:
    """Cascade-clean — refresh_tokens has ON DELETE CASCADE,
    audit_log has ON DELETE SET NULL, so user delete sweeps both."""
    from sqlalchemy import delete as sa_delete

    async with SessionLocal() as session:
        await session.execute(sa_delete(User).where(User.id.in_(ids)))
        await session.commit()


@pytest.mark.asyncio
async def test_force_revoke_happy_path(test_engine):
    """Admin revokes target. Verify: epoch bumped, refresh token
    marked revoked, audit_log row written."""
    _ = test_engine
    from app.api.v2.admin import force_revoke_user

    engine, SessionLocal = _make_session_factory()
    admin = await _seed_user(SessionLocal, UserRole.ADMIN)
    target = await _seed_user(SessionLocal, UserRole.OPERADOR)
    token_id = await _seed_refresh_token(SessionLocal, target.id)

    try:
        async with SessionLocal() as session:
            # Stub Request: only ``client.host`` is read by the
            # endpoint. ``None`` is fine — the audit row simply
            # stores NULL for client_ip.
            class _StubRequest:
                client = None

            response = await force_revoke_user(
                user_id=target.id,
                request=_StubRequest(),  # type: ignore[arg-type]
                admin=admin,
                db=session,
            )

        assert response.user_id == target.id
        assert response.revoked_sessions == 1
        assert response.new_revocation_epoch == 1

        # Verify the target's revocation_epoch incremented.
        async with SessionLocal() as session:
            row = (
                await session.execute(
                    select(User.revocation_epoch).where(User.id == target.id)
                )
            ).scalar_one()
            assert row == 1

        # Verify the refresh token is now revoked.
        async with SessionLocal() as session:
            rt = (
                await session.execute(
                    select(RefreshToken).where(RefreshToken.id == token_id)
                )
            ).scalar_one()
            assert rt.revoked is True

        # Verify the audit_log row exists with the right shape.
        async with SessionLocal() as session:
            entry = (
                await session.execute(
                    select(AuditLog)
                    .where(AuditLog.user_id == admin.id)
                    .where(AuditLog.action == "user.force-revoke")
                )
            ).scalar_one()
            assert entry.resource == f"user_id={target.id}"
    finally:
        await _cleanup_users(SessionLocal, [admin.id, target.id])
        await engine.dispose()


@pytest.mark.asyncio
async def test_force_revoke_self_rejected_400(test_engine):
    """Admin force-revoking THEMSELVES is almost certainly a mistake
    (they'd lock themselves out mid-incident). Block at the endpoint
    with HTTP 400 and a hint pointing at the correct self path."""
    _ = test_engine
    from app.api.v2.admin import force_revoke_user
    from fastapi import HTTPException

    engine, SessionLocal = _make_session_factory()
    admin = await _seed_user(SessionLocal, UserRole.ADMIN)

    try:
        async with SessionLocal() as session:
            class _StubRequest:
                client = None

            with pytest.raises(HTTPException) as exc:
                await force_revoke_user(
                    user_id=admin.id,
                    request=_StubRequest(),  # type: ignore[arg-type]
                    admin=admin,
                    db=session,
                )
        assert exc.value.status_code == 400
        assert "logout-all" in exc.value.detail.lower()
    finally:
        await _cleanup_users(SessionLocal, [admin.id])
        await engine.dispose()


@pytest.mark.asyncio
async def test_force_revoke_unknown_user_404(test_engine):
    """Target UUID that doesn't exist → 404 (admins are trusted
    callers; enumeration mitigation doesn't apply here)."""
    _ = test_engine
    from app.api.v2.admin import force_revoke_user
    from fastapi import HTTPException

    engine, SessionLocal = _make_session_factory()
    admin = await _seed_user(SessionLocal, UserRole.ADMIN)

    try:
        async with SessionLocal() as session:
            class _StubRequest:
                client = None

            with pytest.raises(HTTPException) as exc:
                await force_revoke_user(
                    user_id=uuid.uuid4(),  # never seeded
                    request=_StubRequest(),  # type: ignore[arg-type]
                    admin=admin,
                    db=session,
                )
        assert exc.value.status_code == 404
    finally:
        await _cleanup_users(SessionLocal, [admin.id])
        await engine.dispose()
