"""Submission-quota response schemas (Phase 5 / F5-B).

Used by the citizen-facing rate-limit endpoints
(``GET /denuncias/rate-limit``, ``GET /sugerencias/rate-limit``)
to report how many submissions a user has left in the current
24-hour rolling window. Identical shape both places — the helper
in ``app/shared/submission_limit.py`` computes it once and either
endpoint just returns it.

Surfacing a real Pydantic schema (instead of ``response_model=dict``)
means the frontend gets a typed contract: ``remaining: number``,
``limit: number``, ``reset_seconds: number``. Previously the
generated client typed this as ``Record<string, unknown>``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SubmissionStatusResponse(BaseModel):
    """Current quota state for a citizen in the rolling 24-hour window."""

    remaining: int = Field(
        ...,
        ge=0,
        description="Submissions the caller can still create before the limit resets.",
    )
    limit: int = Field(
        ...,
        ge=1,
        description="Total submissions allowed per 24-hour rolling window.",
    )
    reset_seconds: int = Field(
        ...,
        ge=0,
        description=(
            "Seconds until the oldest submission in the current window "
            "ages out (i.e., when one slot frees up). 0 means the caller "
            "has not submitted anything in the window."
        ),
    )
