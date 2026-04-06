"""FastAPI router for the hydrology sub-module.

All endpoints are under /geo/hydrology and require operator role.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.geo.hydrology.repository import FloodFlowRepository
from app.domains.geo.hydrology.schemas import (
    FloodFlowHistoryResponse,
    FloodFlowRequest,
    FloodFlowResponse,
    ZonaFloodFlowResult,
)
from app.domains.geo.hydrology.service import FloodFlowService

router = APIRouter(tags=["Hydrology"])


def _get_repo() -> FloodFlowRepository:
    return FloodFlowRepository()


def _require_operator():
    """Return the operator dependency at call time (lazy import to avoid circular deps)."""
    from app.auth import require_admin_or_operator

    return require_admin_or_operator


# ──────────────────────────────────────────────
# FLOOD FLOW COMPUTATION
# ──────────────────────────────────────────────


@router.post("/flood-flow", response_model=FloodFlowResponse)
async def compute_flood_flow(
    payload: FloodFlowRequest,
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    """Compute flood flow via Kirpich + Rational Method for one or more zones.

    Fetches slope from SRTM (GEE), NDVI from Sentinel-2 (GEE), and rainfall
    intensity from CHIRPS records. Returns per-zone peak discharge and
    hydraulic risk classification.
    """
    service = FloodFlowService(FloodFlowRepository())
    return await service.compute_flood_flow(db, payload.zona_ids, payload.fecha_lluvia)


# ──────────────────────────────────────────────
# FLOOD FLOW HISTORY
# ──────────────────────────────────────────────


@router.get("/flood-flow/{zona_id}", response_model=FloodFlowHistoryResponse)
def get_flood_flow_history(
    zona_id: uuid.UUID,
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    repo: FloodFlowRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """Return the most recent flood flow records for a zone.

    Results are ordered by fecha_lluvia descending. Use ``limit`` to control
    how many records are returned (default 10, max 100).
    """
    records = repo.get_by_zona(db, zona_id=zona_id, limit=limit)
    return FloodFlowHistoryResponse(
        zona_id=zona_id,
        records=[ZonaFloodFlowResult.model_validate(r) for r in records],
        total=len(records),
    )
