"""Admin action: refresh ``mv_suelos_por_zona``.

The soils ETL refreshes the view as its last step, but that refresh runs
*outside* the load transaction (PostgreSQL forbids ``REFRESH ... CONCURRENTLY``
inside a transaction block). So a load can commit and the refresh still fail,
leaving the data current and the view stale. This endpoint is the documented
recovery path — spec ``soils-etl`` › "Stale view is recoverable" (JD-A-004,
JDB-016).

The view has no readers yet — its consumer arrives in a later slice of this
change. The ficha endpoint never reads it either: it runs the same SQL
parameterized by the request geometry, so a stale view can never affect ficha
correctness. This endpoint exists so the recovery path is in place before the
first reader is, not because something is degraded today.

Admin-only: it is a maintenance action on shared state, and the concurrent
refresh, while non-blocking for readers, is not free.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import get_db
from app.domains.geo.router_common import _require_admin

logger = get_logger(__name__)

router = APIRouter(prefix="/admin/geo/suelos", tags=["admin-geo"])


class RefreshMvResponse(BaseModel):
    vista: str
    filas: int


@router.post("/refresh-mv", response_model=RefreshMvResponse)
def refresh_suelos_materialized_view(
    db: Session = Depends(get_db),
    _user=Depends(_require_admin()),
) -> RefreshMvResponse:
    """Run the concurrent refresh and report the resulting row count.

    Sync ``def`` on purpose: the refresh is blocking I/O, so FastAPI runs it in
    the threadpool instead of stalling the event loop.
    """
    from app.domains.geo.etl.load_suelos_catastro import (
        MATERIALIZED_VIEW,
        refresh_materialized_view,
    )

    try:
        filas = refresh_materialized_view(db)
    except Exception as exc:  # noqa: BLE001 — surfaced as 503, not swallowed
        # The cause goes to the log, never to the response: a database error
        # string leaks schema and connection details to the client.
        logger.error("refresh de %s falló: %s", MATERIALIZED_VIEW, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="no se pudo refrescar la vista; revisá los logs del backend",
        ) from exc

    return RefreshMvResponse(vista=MATERIALIZED_VIEW, filas=filas)
