"""One-time codes for SMTP-body PII hardening (Phase 5 / F5-E).

Stand-in layer between the fastapi-users token machinery (which
generates long JWT tokens for password-reset and email-verify
flows) and the email body (which the SMTP provider retains for
30+ days). The flow now:

1. fastapi-users generates the real verify/reset token.
2. ``create_code_for_token`` stores an 8-char ``code`` mapped to
   the token in the ``email_codes`` table.
3. The email body carries ONLY the ``code`` — never the token.
4. The SPA exchanges the ``code`` for the original ``token`` via
   ``POST /auth/exchange-code``.
5. fastapi-users' existing verify / reset endpoints consume the
   token as before.

The provider can retain the email body for as long as it wants;
once the code is consumed (or expires after 15 min) it's
worthless.

Threat model
============

Brute force against the code space: 36^8 ≈ 2.8 × 10^12 combos.
At 100 req/s (well above the rate-limit middleware allows) it
takes ~900 years to enumerate. The exchange endpoint also
rate-limits per IP at the middleware layer.

The code is NOT a secret in the cryptographic sense (it's stored
plaintext in the DB so the exchange lookup is O(1) on the unique
index). Compromise of the DB grants the same codes the email
already carried; the substrate doesn't claim defense-in-depth
against DB read, only against SMTP-body exfiltration.
"""

from __future__ import annotations

import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.models import User
from app.db.base import Base, UUIDMixin


CODE_LENGTH = 8
CODE_ALPHABET = string.ascii_uppercase + string.digits  # 36 chars
CODE_TTL = timedelta(minutes=15)

VERIFY_PURPOSE = "verify"
RESET_PURPOSE = "reset"
_VALID_PURPOSES = {VERIFY_PURPOSE, RESET_PURPOSE}


class EmailCode(UUIDMixin, Base):
    """One-time code that stands in for a verify / reset token."""

    __tablename__ = "email_codes"

    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    token: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


def generate_short_code(length: int = CODE_LENGTH) -> str:
    """Cryptographically-secure random 8-char alphanumeric code.

    ``secrets.choice`` is the recommended source for tokens that
    must resist enumeration. Uppercase + digits keeps the code
    case-insensitive when typed.
    """
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


async def create_code_for_token(
    session: AsyncSession,
    *,
    user: User,
    purpose: str,
    token: str,
    ttl: timedelta = CODE_TTL,
) -> str:
    """Persist a new ``email_codes`` row and return the ``code``.

    Caller commits or rolls back. The code is unique-indexed so a
    collision raises ``IntegrityError`` — retry once at most before
    surfacing, matching the standard one-time-secret pattern.
    """
    if purpose not in _VALID_PURPOSES:
        raise ValueError(
            f"purpose must be one of {sorted(_VALID_PURPOSES)}, got {purpose!r}"
        )

    now = datetime.now(tz=timezone.utc)
    last_err: Exception | None = None
    # Two attempts at most — a collision in 2.8T-combo space is
    # astronomically unlikely even with concurrent issuance.
    for _ in range(2):
        code = generate_short_code()
        row = EmailCode(
            code=code,
            user_id=user.id,
            purpose=purpose,
            token=token,
            created_at=now,
            expires_at=now + ttl,
        )
        session.add(row)
        try:
            await session.flush()
            return code
        except Exception as exc:  # noqa: BLE001 — narrow on retry
            last_err = exc
            await session.rollback()
            continue
    assert last_err is not None  # for mypy
    raise last_err


async def invalidate_open_codes_for_user(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    purpose: str,
) -> int:
    """Mark every unconsumed, unexpired code for this user+purpose as
    consumed_at=now.

    Phase 5 / F5-E 3vr fix-forward (Sonnet finding): without this,
    pressing "forgot password" twice leaves TWO simultaneously valid
    codes in flight. Calling this BEFORE ``create_code_for_token``
    in the UserManager hook ensures only the latest code is usable.

    Caller commits or rolls back. Returns the row count for tests.
    """
    if purpose not in _VALID_PURPOSES:
        raise ValueError(
            f"purpose must be one of {sorted(_VALID_PURPOSES)}, got {purpose!r}"
        )
    from sqlalchemy import update as sa_update

    now = datetime.now(tz=timezone.utc)
    result = await session.execute(
        sa_update(EmailCode)
        .where(
            EmailCode.user_id == user_id,
            EmailCode.purpose == purpose,
            EmailCode.consumed_at.is_(None),
            EmailCode.expires_at > now,
        )
        .values(consumed_at=now)
    )
    return int(getattr(result, "rowcount", 0) or 0)


async def exchange_code_for_token(
    session: AsyncSession,
    *,
    code: str,
    purpose: str,
) -> str | None:
    """Look up the code, mark it consumed, return the original token.

    Returns ``None`` on any failure path (unknown / wrong purpose /
    expired / already consumed). The caller maps that to HTTP 400 —
    we deliberately do NOT distinguish between failure modes so
    enumeration attacks can't tell "this code never existed" from
    "this code expired 2 min ago".

    Caller commits or rolls back. The consume step is INSIDE this
    function so even if the caller forgets to commit, the next call
    with the same code finds it still consumable — that's not great
    but the row is also short-lived (15 min TTL) so the window is
    bounded.
    """
    if purpose not in _VALID_PURPOSES:
        return None

    stmt = select(EmailCode).where(EmailCode.code == code.upper())
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    if row.purpose != purpose:
        return None
    if row.consumed_at is not None:
        return None
    if row.expires_at <= datetime.now(tz=timezone.utc):
        return None

    row.consumed_at = datetime.now(tz=timezone.utc)
    await session.flush()
    return row.token
