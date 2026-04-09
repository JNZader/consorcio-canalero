"""
FastAPI router for 3D terrain visualization endpoints.

Exposes 4 GET endpoints under the /render prefix (mounted by geo/router.py):
  GET /render/cuencas      → image/png
  GET /render/escorrentia  → image/png
  GET /render/riesgo       → image/png
  GET /render/animacion    → video/mp4

All endpoints require operator role (require_admin_or_operator).
Thin HTTP layer — all work is delegated to VisualizationService.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.geo.visualization.service import VisualizationService

router = APIRouter(tags=["Visualization"])


# ---------------------------------------------------------------------------
# Dependency helpers — lazy imports to avoid circular deps (hydrology pattern)
# ---------------------------------------------------------------------------


def _require_operator():
    """Return the operator dependency at call time (lazy import to avoid circular deps)."""
    from app.auth import require_admin_or_operator

    return require_admin_or_operator


def _get_service() -> VisualizationService:
    """Return a VisualizationService instance."""
    return VisualizationService()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/cuencas")
def render_cuencas(
    dem_path: str = Query(..., description="Filesystem path to the DEM GeoTIFF"),
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
    _svc: VisualizationService = Depends(_get_service),
) -> Response:
    """Render 3D terrain surface with basin polygon overlays.

    Returns a PNG image of the terrain rendered with cuencas (watershed basins)
    overlaid as 3D polygons. Requires operator role.

    Raises HTTP 404 if the DEM file does not exist at dem_path.
    """
    png_bytes = _svc.render_cuencas(db, Path(dem_path))
    return Response(content=png_bytes, media_type="image/png")


@router.get("/escorrentia")
def render_escorrentia(
    dem_path: str = Query(..., description="Filesystem path to the DEM GeoTIFF"),
    fecha: Optional[str] = Query(default="", description="Storm date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
    _svc: VisualizationService = Depends(_get_service),
) -> Response:
    """Render escorrentia (runoff) flow paths as 3D polylines over DEM terrain.

    Returns a PNG image. Requires operator role.
    Raises HTTP 404 if the DEM file does not exist at dem_path.
    """
    png_bytes = _svc.render_escorrentia(db, Path(dem_path))
    return Response(content=png_bytes, media_type="image/png")


@router.get("/riesgo")
def render_riesgo(
    dem_path: str = Query(..., description="Filesystem path to the DEM GeoTIFF"),
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
    _svc: VisualizationService = Depends(_get_service),
) -> Response:
    """Render hydraulic risk zones as colored polygons over DEM terrain.

    Risk levels: bajo=green, medio=yellow, alto=orange, crítico=red.
    Returns a PNG image. Requires operator role.
    Raises HTTP 404 if the DEM file does not exist at dem_path.
    """
    png_bytes = _svc.render_riesgo(db, Path(dem_path))
    return Response(content=png_bytes, media_type="image/png")


@router.get("/animacion")
def render_animacion(
    dem_path: str = Query(..., description="Filesystem path to the DEM GeoTIFF"),
    fecha: Optional[str] = Query(default="", description="Storm date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
    _svc: VisualizationService = Depends(_get_service),
) -> Response:
    """Produce an MP4 animation via animated camera flyover over DEM terrain.

    Combines terrain surface, basin overlays, and risk zones into a
    fly-through animation. Returns MP4 video bytes. Requires operator role.
    Raises HTTP 404 if the DEM file does not exist at dem_path.
    """
    mp4_bytes = _svc.render_animacion(db, Path(dem_path), fecha=fecha or "")
    return Response(content=mp4_bytes, media_type="video/mp4")
