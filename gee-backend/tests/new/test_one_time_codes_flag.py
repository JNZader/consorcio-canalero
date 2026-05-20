"""Phase 5 / F5-E — integration tests for the USE_ONE_TIME_CODES flag.

Existing ``test_email_codes.py`` covers the substrate functions in
isolation (``generate_short_code``, ``create_code_for_token``,
``exchange_code_for_token``). What was missing — and is the reason
this file exists — is a test that exercises the actual UserManager
hooks (``on_after_forgot_password`` / ``on_after_request_verify``)
with the flag flipped ON, end-to-end against the real DB.

Without this guard, a refactor of the hook bodies could silently
break the SMTP-hardening contract while the unit tests keep passing.

The contract being pinned:
  - When ``settings.use_one_time_codes`` is True, the SMTP body
    sent to the user contains the 8-char ``code``, NEVER the JWT.
  - An ``email_codes`` row is persisted with the JWT mapped to the
    code, so the SPA's ``/auth/exchange-code`` round-trip works.
  - When the flag is False, behaviour is the legacy token-in-body
    path — regression guard so flipping the flag stays opt-in.
"""

from __future__ import annotations

import os
import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.auth.email_codes import EmailCode, RESET_PURPOSE, VERIFY_PURPOSE
from app.auth.models import User, UserRole


def _make_session_factory():
    sync_url = os.environ["DATABASE_URL"]
    async_url = sync_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(async_url, echo=False)
    SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, SessionLocal


async def _seed_user_async(SessionLocal) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"f5e-flag-{uuid.uuid4().hex[:8]}@playwright.com",
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
    async with SessionLocal() as session:
        await session.execute(sa_delete(User).where(User.id == user_id))
        await session.commit()


async def _invoke_hook_with_captured_email(
    SessionLocal,
    user: User,
    *,
    hook_name: str,
    token: str,
) -> dict[str, Any]:
    """Run one UserManager hook against a real DB session and capture
    the email kwargs that would have been shipped. Returns the captured
    kwargs dict so callers can assert on body_text / body_html.

    The hook code does ``from app.shared.email import send_email``
    inside the function body — patching at the module attribute level
    catches that late import because the import returns the current
    module attribute value at call time.
    """
    from app.auth.dependencies import UserManager

    captured: list[dict[str, Any]] = []

    async def _capture(**kwargs: Any) -> None:
        captured.append(kwargs)

    async with SessionLocal() as session:
        user_db = SQLAlchemyUserDatabase(session, User)
        manager = UserManager(user_db)
        with patch(
            "app.shared.email.send_email", new=AsyncMock(side_effect=_capture)
        ):
            hook = getattr(manager, hook_name)
            await hook(user, token, request=None)

    assert len(captured) == 1, (
        f"expected exactly one email send, got {len(captured)} "
        f"(hook={hook_name}, flag_state=settings.use_one_time_codes)"
    )
    return captured[0]


# ---------------------------------------------------------------------------
# Flag ON — the F5-E mitigation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_forgot_password_flag_on_emails_code_not_token(
    test_engine, monkeypatch
):
    """USE_ONE_TIME_CODES=True → the email body carries the 8-char
    code, the JWT reset token NEVER appears in the body, and an
    ``email_codes`` row maps the code back to the original token."""
    _ = test_engine
    from app.config import settings

    monkeypatch.setattr(settings, "use_one_time_codes", True)

    engine, SessionLocal = _make_session_factory()
    user = await _seed_user_async(SessionLocal)
    jwt_token = "FAKE.JWT.RESET-TOKEN-SHOULD-NEVER-LEAK-INTO-SMTP-BODY"

    try:
        email = await _invoke_hook_with_captured_email(
            SessionLocal,
            user,
            hook_name="on_after_forgot_password",
            token=jwt_token,
        )

        body_text = email["body_text"]
        body_html = email.get("body_html") or ""
        assert jwt_token not in body_text, (
            "JWT reset token leaked into email body_text — the WHOLE "
            "point of F5-E is to keep it out of SMTP-retained logs."
        )
        assert jwt_token not in body_html, (
            "JWT reset token leaked into email body_html."
        )

        async with SessionLocal() as session:
            row = (
                await session.execute(
                    select(EmailCode)
                    .where(EmailCode.user_id == user.id)
                    .where(EmailCode.purpose == RESET_PURPOSE)
                )
            ).scalar_one()
            assert row.token == jwt_token, (
                "email_codes.token must hold the original JWT so the "
                "SPA's exchange-code round-trip can recover it."
            )
            assert row.consumed_at is None
            assert len(row.code) == 8
            assert row.code in body_text, (
                f"the 8-char code {row.code!r} should appear in the "
                f"email body so the user can paste it into the SPA."
            )
    finally:
        await _cleanup_user_async(SessionLocal, user.id)
        await engine.dispose()


@pytest.mark.asyncio
async def test_request_verify_flag_on_emails_code_not_token(
    test_engine, monkeypatch
):
    """Same hardening on the email-verification path. The verify hook
    runs the same flag check, so a refactor of one without the other
    would slip past tests that only cover reset."""
    _ = test_engine
    from app.config import settings

    monkeypatch.setattr(settings, "use_one_time_codes", True)

    engine, SessionLocal = _make_session_factory()
    user = await _seed_user_async(SessionLocal)
    jwt_token = "FAKE.JWT.VERIFY-TOKEN-SHOULD-NEVER-LEAK-INTO-SMTP-BODY"

    try:
        email = await _invoke_hook_with_captured_email(
            SessionLocal,
            user,
            hook_name="on_after_request_verify",
            token=jwt_token,
        )

        body_text = email["body_text"]
        body_html = email.get("body_html") or ""
        assert jwt_token not in body_text
        assert jwt_token not in body_html

        async with SessionLocal() as session:
            row = (
                await session.execute(
                    select(EmailCode)
                    .where(EmailCode.user_id == user.id)
                    .where(EmailCode.purpose == VERIFY_PURPOSE)
                )
            ).scalar_one()
            assert row.token == jwt_token
            assert row.consumed_at is None
            assert row.code in body_text
    finally:
        await _cleanup_user_async(SessionLocal, user.id)
        await engine.dispose()


# ---------------------------------------------------------------------------
# Flag OFF — regression guard for the legacy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_forgot_password_flag_off_uses_legacy_token_in_body(
    test_engine, monkeypatch
):
    """USE_ONE_TIME_CODES=False (default) → the legacy path runs: the
    email body carries the JWT directly, no email_codes row exists.
    This is the regression guard that prevents an accidental flip of
    the default from going unnoticed."""
    _ = test_engine
    from app.config import settings

    monkeypatch.setattr(settings, "use_one_time_codes", False)

    engine, SessionLocal = _make_session_factory()
    user = await _seed_user_async(SessionLocal)
    jwt_token = "LEGACY.JWT.RESET-TOKEN-EXPECTED-IN-BODY"

    try:
        email = await _invoke_hook_with_captured_email(
            SessionLocal,
            user,
            hook_name="on_after_forgot_password",
            token=jwt_token,
        )

        body_text = email["body_text"]
        assert jwt_token in body_text, (
            "Legacy path must keep the JWT in the body so SPA versions "
            "that don't know about ``?code=`` continue to work."
        )

        async with SessionLocal() as session:
            rows = (
                await session.execute(
                    select(EmailCode).where(EmailCode.user_id == user.id)
                )
            ).scalars().all()
            assert rows == [], (
                "Flag is OFF — no email_codes row should be created. "
                f"Found {len(rows)} row(s) which leaks one-time-code "
                f"infrastructure into the legacy path."
            )
    finally:
        await _cleanup_user_async(SessionLocal, user.id)
        await engine.dispose()
