"""FastAPI router for the operational intelligence sub-module.

All endpoints are under /geo/intelligence and require operator role.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import get_db
from app.domains.geo.intelligence.repository import IntelligenceRepository
from app.domains.geo.intelligence.schemas import (
    AlertaResponse,
    CriticidadRequest,
    CriticidadResponse,
    DashboardInteligente,
    EscorrentiaRequest,
    EscorrentiaResponse,
    IndiceHidricoResponse,
    PuntoConflictoResponse,
    ZonaOperativaResponse,
    ZonificacionRequest,
    ZonificacionResponse,
)
from app.domains.geo.intelligence import service as intel_service

logger = get_logger(__name__)

router = APIRouter(tags=["Intelligence"])


def _get_repo() -> IntelligenceRepository:
    return IntelligenceRepository()


def _require_operator():
    """Return the operator dependency at call time (lazy import)."""
    from app.auth import require_admin_or_operator

    return require_admin_or_operator


# ──────────────────────────────────────────────
# DASHBOARD
# ──────────────────────────────────────────────


@router.get("/dashboard", response_model=DashboardInteligente)
def get_dashboard(
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    """Get the aggregated operational intelligence dashboard."""
    return intel_service.get_dashboard(db)


# ──────────────────────────────────────────────
# HCI — Hydric Criticality Index
# ──────────────────────────────────────────────


@router.post("/hci/calculate", response_model=CriticidadResponse)
def calculate_hci(
    payload: CriticidadRequest,
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    """Calculate the Hydric Criticality Index for a zone."""
    try:
        result = intel_service.calculate_hci_for_zone(
            db,
            payload.zona_id,
            pendiente_media=payload.pendiente_media,
            acumulacion_media=payload.acumulacion_media,
            twi_medio=payload.twi_medio,
            proximidad_canal_m=payload.proximidad_canal_m,
            historial_inundacion=payload.historial_inundacion,
            pesos=payload.pesos,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/hci", response_model=dict)
def list_hci(
    zona_id: Optional[uuid.UUID] = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    repo: IntelligenceRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """List HCI results with optional zone filter."""
    items, total = repo.get_indices_hidricos(
        db, zona_id=zona_id, page=page, limit=limit
    )
    return {
        "items": [IndiceHidricoResponse.model_validate(i) for i in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


# ──────────────────────────────────────────────
# CONFLICT POINTS
# ──────────────────────────────────────────────


@router.get("/conflictos", response_model=dict)
def list_conflictos(
    tipo: Optional[str] = Query(default=None),
    severidad: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    repo: IntelligenceRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """List detected conflict points."""
    items, total = repo.get_conflictos(
        db, tipo_filter=tipo, severidad_filter=severidad, page=page, limit=limit
    )
    return {
        "items": [PuntoConflictoResponse.model_validate(i) for i in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.post("/conflictos/detectar", response_model=dict)
def detect_conflictos(
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    """Run conflict detection (dispatches Celery task for full analysis).

    For now returns a placeholder. Full execution via task_detect_all_conflicts.
    """
    from app.domains.geo.intelligence.tasks import task_detect_all_conflicts

    task = task_detect_all_conflicts.delay()
    return {"task_id": task.id, "status": "submitted"}


# ──────────────────────────────────────────────
# RUNOFF SIMULATION
# ──────────────────────────────────────────────


@router.post("/escorrentia", response_model=EscorrentiaResponse)
def run_escorrentia(
    payload: EscorrentiaRequest,
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    """Run runoff simulation from a starting point.

    Requires pre-computed flow direction and flow accumulation rasters.
    """
    # Find the latest flow_dir and flow_acc layers
    from app.domains.geo.repository import GeoRepository
    from app.domains.geo.models import TipoGeoLayer

    geo_repo = GeoRepository()
    flow_dir_layers, _ = geo_repo.get_layers(
        db, tipo_filter=TipoGeoLayer.FLOW_DIR, page=1, limit=1
    )
    flow_acc_layers, _ = geo_repo.get_layers(
        db, tipo_filter=TipoGeoLayer.FLOW_ACC, page=1, limit=1
    )

    if not flow_dir_layers or not flow_acc_layers:
        raise HTTPException(
            status_code=400,
            detail="Se requieren capas de flow_dir y flow_acc procesadas previamente",
        )

    result = intel_service.run_runoff_simulation(
        db,
        punto=tuple(payload.punto_inicio),
        lluvia_mm=payload.lluvia_mm,
        flow_dir_path=flow_dir_layers[0].archivo_path,
        flow_acc_path=flow_acc_layers[0].archivo_path,
    )
    return result


# ──────────────────────────────────────────────
# OPERATIONAL ZONES
# ──────────────────────────────────────────────


@router.get("/zonas", response_model=dict)
def list_zonas(
    cuenca: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    repo: IntelligenceRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """List operational zones."""
    items, total = repo.get_zonas(db, page=page, limit=limit, cuenca_filter=cuenca)
    return {
        "items": [ZonaOperativaResponse.model_validate(z) for z in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.post("/zonas/generar", response_model=dict)
def generate_zonas(
    payload: ZonificacionRequest,
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    """Generate operational zones from DEM (dispatches Celery task).

    For now returns a placeholder. Full execution via task_generate_zonification.
    """
    from app.domains.geo.intelligence.tasks import task_generate_zonification

    task = task_generate_zonification.delay(str(payload.dem_layer_id), payload.threshold)
    return {"task_id": task.id, "status": "submitted"}


# ──────────────────────────────────────────────
# CANAL PRIORITY
# ──────────────────────────────────────────────


@router.get("/canales/prioridad", response_model=dict)
def get_canal_priorities(
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    """Get canal priority ranking.

    Returns a pre-computed ranking or triggers computation.
    """
    # Placeholder: in production this would use cached results
    return {
        "items": [],
        "message": "Use POST /geo/intelligence/canales/prioridad/calcular to compute",
    }


# ──────────────────────────────────────────────
# ROAD RISK
# ──────────────────────────────────────────────


@router.get("/caminos/riesgo", response_model=dict)
def get_road_risks(
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    """Get road risk ranking.

    Returns a pre-computed ranking or triggers computation.
    """
    return {
        "items": [],
        "message": "Use POST /geo/intelligence/caminos/riesgo/calcular to compute",
    }


# ──────────────────────────────────────────────
# ALERTS
# ──────────────────────────────────────────────


@router.get("/alertas", response_model=dict)
def list_alertas(
    db: Session = Depends(get_db),
    repo: IntelligenceRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """List active geo-alerts."""
    alertas = repo.get_alertas_activas(db)
    return {
        "items": [AlertaResponse.model_validate(a) for a in alertas],
        "total": len(alertas),
    }


@router.post("/alertas/evaluar", response_model=dict)
def evaluate_alertas(
    db: Session = Depends(get_db),
    _user=Depends(_require_operator()),
):
    """Evaluate alert conditions and create new alerts if thresholds are exceeded."""
    result = intel_service.check_alerts(db)
    return result
