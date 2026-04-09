"""
FastAPI router for 3D terrain visualization endpoints.

Exposes 4 GET endpoints under the /render prefix (mounted by geo/router.py):
  GET /render/cuencas      → image/png
  GET /render/escorrentia  → image/png
  GET /render/riesgo       → image/png
  GET /render/animacion    → video/mp4

Layers are resolved from the geo_layers DB table by the service — callers
only need to pass an optional area_id query param to scope the lookup.

All endpoints require operator role (require_admin_or_operator).
Thin HTTP layer — all work is delegated to VisualizationService.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
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
    area_id: str | None = None,
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
    _svc: VisualizationService = Depends(_get_service),
) -> Response:
    """Render 3D terrain surface with basin polygon overlays.

    Resolves DEM_RAW and FLOW_ACC layers from the database.
    Returns a PNG image of the terrain rendered with cuencas (watershed basins)
    overlaid as 3D polygons. Requires operator role.

    Raises HTTP 404 if no matching layer exists (run terrain analysis first).
    """
    content = _svc.render_cuencas(db, area_id)
    return Response(content=content, media_type="image/png")


@router.get("/escorrentia")
def render_escorrentia(
    lon: float = -63.0,
    lat: float = -31.0,
    lluvia_mm: float = 50.0,
    area_id: str | None = None,
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
    _svc: VisualizationService = Depends(_get_service),
) -> Response:
    """Render escorrentia (runoff) flow paths as 3D polylines over DEM terrain.

    Resolves FLOW_DIR, FLOW_ACC, and DEM_RAW layers from the database.
    Traces a downstream flow path from (lon, lat) weighted by lluvia_mm.
    Returns a PNG image. Requires operator role.
    Raises HTTP 404 if required layers are not found.
    """
    content = _svc.render_escorrentia(db, lon, lat, lluvia_mm, area_id)
    return Response(content=content, media_type="image/png")


@router.get("/riesgo")
def render_riesgo(
    area_id: str | None = None,
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
    _svc: VisualizationService = Depends(_get_service),
) -> Response:
    """Render hydraulic risk zones as colored polygons over DEM terrain.

    Resolves DEM_RAW, FLOW_ACC, and SLOPE layers from the database.
    Risk levels: bajo=green, medio=yellow, alto=orange, crítico=red.
    Returns a PNG image. Requires operator role.
    Raises HTTP 404 if required layers are not found.
    """
    content = _svc.render_riesgo(db, area_id)
    return Response(content=content, media_type="image/png")


@router.get("/animacion")
def render_animacion(
    area_id: str | None = None,
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
    _svc: VisualizationService = Depends(_get_service),
) -> Response:
    """Produce an MP4 animation via animated camera flyover over DEM terrain.

    Resolves DEM_RAW, FLOW_ACC, and SLOPE layers from the database.
    Combines terrain surface, basin overlays, and risk zones into a
    fly-through animation. Returns MP4 video bytes. Requires operator role.
    Raises HTTP 404 if required layers are not found.
    """
    content = _svc.render_animacion(db, area_id)
    return Response(content=content, media_type="video/mp4")
