"""FastAPI router for the territorial domain.

Endpoints are under /territorial and require admin or operator role.
Import/sync endpoints require admin role.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.territorial.repository import TerritorialRepository
from app.domains.territorial.schemas import (
    CuencaListResponse,
    GeoJSONImportRequest,
    ImportResponse,
    SyncResponse,
    TerritorialReportResponse,
)
from app.domains.territorial.service import TerritorialService

router = APIRouter(prefix="/territorial", tags=["Territorial"])


def _require_admin():
    from app.auth import require_admin

    return require_admin


def _require_operator():
    from app.auth import require_admin_or_operator

    return require_admin_or_operator


def _get_service() -> TerritorialService:
    return TerritorialService(TerritorialRepository())


# ── Sync (reads from local GeoJSON files already in the system) ─────────────


@router.post("/sync", response_model=SyncResponse)
def sync_geodata(
    db: Session = Depends(get_db),
    _user=Depends(_require_admin()),
    service: TerritorialService = Depends(_get_service),
):
    """Sync suelos, canales and caminos from GeoJSON files already in the system.

    Reads from known paths (mounted volumes in Docker):
    - /app/public/data/suelos_cu.geojson
    - /app/public/waterways/canales_existentes.geojson
    - /app/public/capas/caminos.geojson

    Truncates + re-inserts all data and refreshes materialized views.
    """
    return service.sync_geodata(db)


# ── Manual import endpoints (admin only, kept for API compatibility) ────────


@router.post("/import/suelos", response_model=ImportResponse)
def import_suelos(
    body: GeoJSONImportRequest,
    db: Session = Depends(get_db),
    _user=Depends(_require_admin()),
    service: TerritorialService = Depends(_get_service),
):
    """Replace suelos_catastro with features from the uploaded GeoJSON and refresh views."""
    return service.import_suelos(db, body.geojson)


@router.post("/import/canales", response_model=ImportResponse)
def import_canales(
    body: GeoJSONImportRequest,
    db: Session = Depends(get_db),
    _user=Depends(_require_admin()),
    service: TerritorialService = Depends(_get_service),
):
    """Replace canales_geo with features from the uploaded GeoJSON and refresh views."""
    return service.import_canales(db, body.geojson)


@router.post("/import/caminos", response_model=ImportResponse)
def import_caminos(
    body: GeoJSONImportRequest,
    db: Session = Depends(get_db),
    _user=Depends(_require_admin()),
    service: TerritorialService = Depends(_get_service),
):
    """Replace caminos_geo with features from the uploaded GeoJSON and refresh views."""
    return service.import_caminos(db, body.geojson)


# ── Report endpoints (operator+) ─────────────────────────────────────────────


@router.get("/report", response_model=TerritorialReportResponse)
def get_territorial_report(
    scope: str = Query("consorcio", description="consorcio | cuenca | zona"),
    value: Optional[str] = Query(None, description="Cuenca name or zona UUID"),
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
    service: TerritorialService = Depends(_get_service),
):
    """Return km de canales + caminos + ha/% de suelos for the requested scope."""
    return service.get_report(db, scope, value)


@router.get("/cuencas", response_model=CuencaListResponse)
def list_cuencas(
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
    service: TerritorialService = Depends(_get_service),
):
    """List distinct cuenca names available in the materialized view."""
    return CuencaListResponse(cuencas=service.get_cuencas(db))


@router.get("/status")
def get_status(
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
    service: TerritorialService = Depends(_get_service),
):
    """Return whether suelos, canales and caminos data have been imported."""
    return service.get_status(db)
