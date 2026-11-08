"""Allowlisted ORDER BY for paginated operator lists.

Unknown names are rejected. Callers never interpolate the query string
into SQL.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import asc, desc
from sqlalchemy.sql.elements import ColumnElement


def order_clause(
    sort: str | None,
    order: str | None,
    columns: dict[str, ColumnElement[Any]],
    *,
    default: ColumnElement[Any],
    tie: ColumnElement[Any],
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
