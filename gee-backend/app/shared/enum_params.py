"""Shared enum checks for query filters (422) and pydantic fields (ValueError)."""

from __future__ import annotations

import enum

from fastapi import HTTPException


def _allowed(choices: type[enum.Enum]) -> tuple[str, ...]:
    return tuple(str(member.value) for member in choices)


def _as_text(value: object) -> str:
    if isinstance(value, enum.Enum):
        return str(value.value)
    return str(value)


def choice_or_raise(value: object, choices: type[enum.Enum], field: str) -> str | None:
    """Pydantic field validator: None stays None, unknown values raise ValueError."""
    if value is None:
        return None
    text = _as_text(value).strip()
    allowed = _allowed(choices)
    if text not in allowed:
        options = ", ".join(allowed)
        raise ValueError(f"{field} invalido. Opciones: {options}")
    return text


def require_choice(value: str | None, choices: type[enum.Enum], field: str) -> str | None:
    """Query-param guard. Blank means no filter. Unknown values are HTTP 422.

    Comparing a raw string to a SQLAlchemy ``Enum`` column raises ``LookupError``
    inside the query compiler, which the API turns into a 500.
    """
    if value is None:
        return None
    text = value.strip()
    if text == "":
        return None
    allowed = _allowed(choices)
    if text not in allowed:
        options = ", ".join(allowed)
        raise HTTPException(
            status_code=422,
            detail=f"{field} invalido. Opciones: {options}",
        )
    return text
