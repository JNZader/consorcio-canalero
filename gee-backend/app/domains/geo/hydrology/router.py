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
    ManningRequest,
    ManningResponse,
    ReturnPeriodResult,
    ReturnPeriodsResponse,
    ZonaFloodFlowResult,
    ZonaRiskSummary,
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


@router.get("/flood-flow/latest", response_model=list[ZonaRiskSummary])
def get_latest_flood_risk(
    db: Session = Depends(get_db),
    repo: FloodFlowRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """Return the latest flood risk level per zone (all zones).

    Used by the frontend map to color zones by hydraulic risk.
    """
    from datetime import date

    records = repo.get_latest_by_all_zonas(db, fecha=date.today())
    return [
        ZonaRiskSummary(zona_id=str(r.zona_id), nivel_riesgo=r.nivel_riesgo)
        for r in records
    ]


# ──────────────────────────────────────────────
# MANNING HYDRAULIC CAPACITY
# ──────────────────────────────────────────────


@router.post("/manning", response_model=ManningResponse)
def compute_manning(
    payload: ManningRequest,
    _user=Depends(_require_operator()),
):
    """Compute Manning hydraulic capacity for a trapezoidal canal section.

    Pure calculation — no database access required.
    Returns cross-section area, wetted perimeter, hydraulic radius,
    discharge capacity (m³/s) and mean flow velocity (m/s).
    """
    from app.domains.geo.hydrology.calculations import (
        get_manning_n,
        manning_q,
        manning_section,
    )

    n = get_manning_n(payload.material, payload.coef_manning)
    area, perimeter = manning_section(
        payload.ancho_m, payload.profundidad_m, payload.talud
    )
    R = area / perimeter if perimeter > 0 else 0.0
    slope = payload.slope
    q = manning_q(payload.ancho_m, payload.profundidad_m, slope, n, payload.talud)
    velocidad = q / area if area > 0 else 0.0

    return ManningResponse(
        ancho_m=payload.ancho_m,
        profundidad_m=payload.profundidad_m,
        talud=payload.talud,
        slope=slope,
        n=n,
        area_m2=round(area, 4),
        perimeter_m=round(perimeter, 4),
        radio_hidraulico_m=round(R, 4),
        q_capacity_m3s=round(q, 4),
        velocidad_ms=round(velocidad, 4),
    )


# ──────────────────────────────────────────────
# RETURN PERIODS (GUMBEL EV-I)
# ──────────────────────────────────────────────


@router.get("/return-periods/{zona_id}", response_model=ReturnPeriodsResponse)
def get_return_periods(
    zona_id: uuid.UUID,
    db: Session = Depends(get_db),
    repo: FloodFlowRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """Compute Gumbel EV-I return period precipitation estimates for a zone.

    Uses annual maximum daily precipitation from CHIRPS/IMERG records stored
    in ``rainfall_records``, with IMERG given priority via DISTINCT ON.
    Requires at least 5 years of data; returns empty return_periods otherwise.
    """
    import statistics

    from app.domains.geo.hydrology.calculations import gumbel_return_period

    rows = repo.get_annual_maxima(db, zona_id=zona_id)
    annual_maxima = [r["max_mm"] for r in rows]

    rp_map = gumbel_return_period(annual_maxima)
    rp_list = [
        ReturnPeriodResult(return_period_years=t, precipitation_mm=v)
        for t, v in sorted(rp_map.items())
    ]

    mean_mm = round(statistics.mean(annual_maxima), 2) if annual_maxima else 0.0
    std_mm = (
        round(statistics.stdev(annual_maxima), 2) if len(annual_maxima) >= 2 else 0.0
    )

    return ReturnPeriodsResponse(
        zona_id=str(zona_id),
        years_of_data=len(annual_maxima),
        annual_maxima_count=len(annual_maxima),
        mean_annual_max_mm=mean_mm,
        std_annual_max_mm=std_mm,
        return_periods=rp_list,
    )


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
