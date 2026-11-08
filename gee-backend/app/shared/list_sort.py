"""Allowlisted ORDER BY for paginated operator lists.

Unknown names are rejected. Callers never interpolate the query string
into SQL.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import asc, desc
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

# InstrumentedAttribute[X] es ColumnElement pero mypy no resuelve la
# varianza del genérico en un dict; aceptamos ambos.
_ColumnLike = ColumnElement[Any] | InstrumentedAttribute[Any]


def order_clause(
    sort: str | None,
    order: str | None,
    columns: dict[str, _ColumnLike],
    *,
    default: _ColumnLike,
    tie: _ColumnLike,
) -> tuple[Any, Any]:
    """Return (primary, tie-break) clauses. Default is newest first."""
    if not sort:
        return desc(default), desc(tie)
    column = columns.get(sort)
    if column is None:
        allowed = ", ".join(sorted(columns))
        raise HTTPException(status_code=400, detail=f"sort no permitido. Usá: {allowed}")
    if order not in (None, "asc", "desc"):
        raise HTTPException(status_code=400, detail="order debe ser asc o desc")
    direction = asc if order == "asc" else desc
    return direction(column), direction(tie)
