"""FastAPI router for the monitoring domain."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.monitoring.schemas import (
    AnalisisGeeResponse,
    SugerenciaCreate,
    SugerenciaListResponse,
    SugerenciaResponse,
    SugerenciaUpdate,
)
from app.domains.monitoring.service import MonitoringService

router = APIRouter(tags=["monitoring"])


def get_service() -> MonitoringService:
    """Dependency that provides the service instance."""
    return MonitoringService()


# Lazy import to avoid circular deps at module level.
def _require_operator():
    """Return the operator dependency at call time."""
    from app.auth import require_admin_or_operator

    return require_admin_or_operator


# ──────────────────────────────────────────────
# SUGERENCIAS — PUBLIC
# ──────────────────────────────────────────────


@router.post(
    "/sugerencias",
    response_model=SugerenciaResponse,
    status_code=201,
    tags=["sugerencias"],
)
def create_sugerencia(
    payload: SugerenciaCreate,
    db: Session = Depends(get_db),
    service: MonitoringService = Depends(get_service),
):
    """
    Crear una sugerencia publica.

    No requiere autenticacion — cualquier ciudadano puede enviar
    sugerencias o comentarios al consorcio.
    """
    return service.create_sugerencia(db, payload)


@router.get(
    "/sugerencias",
    response_model=dict,
    tags=["sugerencias"],
)
def list_sugerencias(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    estado: Optional[str] = None,
    categoria: Optional[str] = None,
    db: Session = Depends(get_db),
    service: MonitoringService = Depends(get_service),
):
    """Listar sugerencias con paginacion y filtros."""
    items, total = service.list_sugerencias(
        db, page=page, limit=limit, estado=estado, categoria=categoria
    )
    return {
        "items": [SugerenciaListResponse.model_validate(s) for s in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


# ──────────────────────────────────────────────
# SUGERENCIAS — PROTECTED
# ──────────────────────────────────────────────


@router.get(
    "/sugerencias/stats",
    response_model=dict,
    tags=["sugerencias"],
)
def get_sugerencias_stats(
    db: Session = Depends(get_db),
    service: MonitoringService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Estadisticas agregadas de sugerencias (requiere operador)."""
    return service.get_sugerencias_stats(db)


@router.get(
    "/sugerencias/proxima-reunion",
    response_model=list[SugerenciaListResponse],
    tags=["sugerencias"],
)
def get_proxima_reunion(
    db: Session = Depends(get_db),
    service: MonitoringService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Sugerencias agendadas para la proxima reunion (requiere operador)."""
    return service.get_proxima_reunion(db)


@router.patch(
    "/sugerencias/{sugerencia_id}",
    response_model=SugerenciaResponse,
    tags=["sugerencias"],
)
def update_sugerencia(
    sugerencia_id: uuid.UUID,
    payload: SugerenciaUpdate,
    db: Session = Depends(get_db),
    service: MonitoringService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Actualizar estado/respuesta de una sugerencia (requiere operador)."""
    return service.update_sugerencia(db, sugerencia_id, payload)


# ──────────────────────────────────────────────
# MONITORING — DASHBOARD & ANALYSES
# ──────────────────────────────────────────────


@router.get("/monitoring/dashboard", response_model=dict)
def get_dashboard(
    db: Session = Depends(get_db),
    service: MonitoringService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Dashboard con estadisticas agregadas de todos los dominios."""
    return service.get_dashboard_stats(db)


@router.get("/monitoring/analyses", response_model=dict)
def list_analyses(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    tipo: Optional[str] = None,
    db: Session = Depends(get_db),
    service: MonitoringService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Historial de analisis GEE con paginacion."""
    items, total = service.list_analyses(db, page=page, limit=limit, tipo=tipo)
    return {
        "items": [AnalisisGeeResponse.model_validate(a) for a in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get(
    "/monitoring/analyses/{analysis_id}",
    response_model=AnalisisGeeResponse,
)
def get_analysis(
    analysis_id: uuid.UUID,
    db: Session = Depends(get_db),
    service: MonitoringService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Detalle de un analisis GEE."""
    return service.get_analysis(db, analysis_id)
