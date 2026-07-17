"""
Per-user submission rate limit (citizen-facing creates).

Used by `denuncias` and `sugerencias` to cap how many records a single
authenticated citizen can create in a rolling 24-hour window. The
source of truth is the database itself — we count rows in the target
table where `created_at >= now() - 24h`. This is intentional:

- No drift between counter and reality (a Redis outage cannot make a
  user "lose" or "gain" submissions).
- No separate counter table or cleanup job to maintain.
- Trivial to reason about: the limit is exactly what `SELECT COUNT(*)`
  returns.

The Redis-backed `app.core.rate_limit.DistributedRateLimiter` is for a
different concern (anti-DDoS at the HTTP layer, by IP). Don't reuse it
here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Type

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

DAILY_SUBMISSION_LIMIT = 5
SUBMISSION_WINDOW_HOURS = 24


def _window_start() -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=SUBMISSION_WINDOW_HOURS)


def _oldest_in_window(
    db: Session,
    *,
    model: Type,
    user_id_attr: InstrumentedAttribute,
    user_id: uuid.UUID,
) -> datetime | None:
    stmt = (
        select(model.created_at)
        .where(user_id_attr == user_id, model.created_at >= _window_start())
        .order_by(model.created_at.asc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def get_submission_status(
    db: Session,
    *,
    model: Type,
    user_id_attr: InstrumentedAttribute,
    user_id: uuid.UUID,
) -> dict:
    """
    Return current quota for a user as `{remaining, limit, reset_seconds}`.

    `reset_seconds` is the time until the OLDEST submission in the
    current window expires (i.e., when one slot frees up). When the
    user has nothing in the window, it's 0.
    """
    cutoff = _window_start()
    used: int = db.execute(
        select(func.count())
        .select_from(model)
        .where(user_id_attr == user_id, model.created_at >= cutoff)
    ).scalar_one()

    remaining = max(0, DAILY_SUBMISSION_LIMIT - used)

    reset_seconds = 0
    oldest = _oldest_in_window(db, model=model, user_id_attr=user_id_attr, user_id=user_id)
    if oldest is not None:
        # `created_at` columns are stored as naive UTC (TimestampMixin).
        # Coerce to aware UTC before subtracting from `now`.
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        reset_at = oldest + timedelta(hours=SUBMISSION_WINDOW_HOURS)
        delta = reset_at - datetime.now(timezone.utc)
        reset_seconds = max(0, int(delta.total_seconds()))

    return {
        "remaining": remaining,
        "limit": DAILY_SUBMISSION_LIMIT,
        "reset_seconds": reset_seconds,
    }


def enforce_submission_limit(
    db: Session,
    *,
    model: Type,
    user_id_attr: InstrumentedAttribute,
    user_id: uuid.UUID,
) -> None:
    """
    Raise `HTTPException(429)` if the user has hit `DAILY_SUBMISSION_LIMIT`
    in the rolling 24h window. Call BEFORE persisting the new row.
    """
    status = get_submission_status(db, model=model, user_id_attr=user_id_attr, user_id=user_id)
    if status["remaining"] <= 0:
        hours = max(1, status["reset_seconds"] // 3600)
        raise HTTPException(
            status_code=429,
            detail=(
                f"Llegaste al límite de {DAILY_SUBMISSION_LIMIT} envíos cada "
                f"{SUBMISSION_WINDOW_HOURS} horas. Volvé en aproximadamente "
                f"{hours} h."
            ),
            headers={"Retry-After": str(status["reset_seconds"])},
        )
