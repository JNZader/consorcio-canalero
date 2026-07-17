"""FastAPI router for the monitoring domain."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.monitoring.schemas import (
    AnalisisGeeResponse,
    DashboardStatsResponse,
    SugerenciaAgendarRequest,
    SugerenciaCitizenResponse,
    SugerenciaCreate,
    SugerenciaListResponse,
    SugerenciaResponse,
    SugerenciaStatsResponse,
    SugerenciaUpdate,
)
from app.domains.monitoring.service import MonitoringService
from app.shared.pagination import PaginatedResponse
from app.shared.quota import SubmissionStatusResponse

router = APIRouter(tags=["monitoring"])


def get_service() -> MonitoringService:
    """Dependency that provides the service instance."""
    return MonitoringService()


# Lazy import to avoid circular deps at module level.
def _require_operator():
    """Return the operator dependency at call time."""
    from app.auth import require_admin_or_operator

    return require_admin_or_operator


def _require_user():
    """Any authenticated user (citizen / operador / admin)."""
    from app.auth import require_authenticated

    return require_authenticated


# ──────────────────────────────────────────────
# SUGERENCIAS — CITIZEN-OWNED CREATE
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
    user=Depends(_require_user()),
):
    """
    Crear una sugerencia (requiere ciudadano autenticado).

    Anti-spam: se retiró el create anónimo (espejo del flujo de
    denuncias). El `usuario_id` y el `contacto_email` se autollenan
    desde el JWT — cualquier `contacto_*` en el body se ignora
    deliberadamente; el server confía en el token, no en el cliente.
    Esto también es lo que permite que la sugerencia aparezca después
    en `GET /sugerencias/mine`.
    """
    payload_data = payload.model_copy(
        update={
            "contacto_email": user.email,
        }
    )
    return service.create_sugerencia(db, payload_data, usuario_id=uuid.UUID(str(user.id)))


@router.get(
    "/sugerencias",
    response_model=PaginatedResponse[SugerenciaListResponse],
    tags=["sugerencias"],
)
def list_sugerencias(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    estado: Optional[str] = None,
    categoria: Optional[str] = None,
    db: Session = Depends(get_db),
    service: MonitoringService = Depends(get_service),
    _user=Depends(_require_operator()),
) -> PaginatedResponse[SugerenciaListResponse]:
    """Listar sugerencias con paginacion y filtros (requiere operador)."""
    items, total = service.list_sugerencias(
        db, page=page, limit=limit, estado=estado, categoria=categoria
    )
    return PaginatedResponse[SugerenciaListResponse].create(
        items=[SugerenciaListResponse.model_validate(s) for s in items],
        total=total,
        page=page,
        limit=limit,
    )


# ──────────────────────────────────────────────
# SUGERENCIAS — CITIZEN-OWNED
# ──────────────────────────────────────────────


@router.get(
    "/sugerencias/mine",
    response_model=PaginatedResponse[SugerenciaCitizenResponse],
    tags=["sugerencias"],
)
def list_my_sugerencias(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    service: MonitoringService = Depends(get_service),
    user=Depends(_require_user()),
) -> PaginatedResponse[SugerenciaCitizenResponse]:
    """
    Lista paginada de sugerencias del ciudadano logueado, con todo el
    detalle. Mirror de `/denuncias/mine` — usado en la sección
    "Mis sugerencias" del `/perfil`.

    ``SugerenciaCitizenResponse`` (no ``notas_internas``) en lugar de la
    full operator response — las notas internas del consorcio no
    tienen que viajar al ciudadano nunca, ni siquiera ocultas en el
    JSON.
    """
    items, total = service.list_sugerencias_by_user(
        db, user_id=uuid.UUID(str(user.id)), page=page, limit=limit
    )
    return PaginatedResponse[SugerenciaCitizenResponse].create(
        items=[SugerenciaCitizenResponse.model_validate(s) for s in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.get(
    "/sugerencias/rate-limit",
    response_model=SubmissionStatusResponse,
    tags=["sugerencias"],
)
def get_sugerencia_rate_limit(
    db: Session = Depends(get_db),
    service: MonitoringService = Depends(get_service),
    user=Depends(_require_user()),
) -> SubmissionStatusResponse:
    """
    Cupo restante del ciudadano para crear sugerencias (5 cada 24 h
    rolling, espejo del flujo de `/denuncias/rate-limit`).
    """
    return SubmissionStatusResponse.model_validate(
        service.get_rate_limit_status(db, uuid.UUID(str(user.id)))
    )


# ──────────────────────────────────────────────
# SUGERENCIAS — PROTECTED
# ──────────────────────────────────────────────


@router.get(
    "/sugerencias/stats",
    response_model=SugerenciaStatsResponse,
    tags=["sugerencias"],
)
def get_sugerencias_stats(
    db: Session = Depends(get_db),
    service: MonitoringService = Depends(get_service),
    _user=Depends(_require_operator()),
) -> SugerenciaStatsResponse:
    """Estadisticas agregadas de sugerencias (requiere operador)."""
    return SugerenciaStatsResponse.model_validate(service.get_sugerencias_stats(db))


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


@router.get(
    "/sugerencias/{sugerencia_id}",
    response_model=SugerenciaResponse,
    tags=["sugerencias"],
)
def get_sugerencia(
    sugerencia_id: uuid.UUID,
    db: Session = Depends(get_db),
    service: MonitoringService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Obtener detalle completo de una sugerencia (requiere operador)."""
    return service.get_sugerencia(db, sugerencia_id)


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


@router.post(
    "/sugerencias/{sugerencia_id}/agendar",
    response_model=SugerenciaResponse,
    tags=["sugerencias"],
)
def agendar_sugerencia(
    sugerencia_id: uuid.UUID,
    payload: SugerenciaAgendarRequest,
    db: Session = Depends(get_db),
    service: MonitoringService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """
    Asignar (o limpiar) la fecha de reunión de una sugerencia.

    The admin SugerenciasPanel exposes a "Agendar para Reunion" button
    with a DatePicker; this endpoint persists the chosen date into
    `Sugerencia.fecha_reunion`. The same endpoint clears it when the
    payload `fecha_reunion` is null (operator changed their mind), so
    the UI stays a single button instead of two.
    """
    return service.agendar_sugerencia(db, sugerencia_id, fecha_reunion=payload.fecha_reunion)


# ──────────────────────────────────────────────
# MONITORING — DASHBOARD & ANALYSES
# ──────────────────────────────────────────────


@router.get("/monitoring/dashboard", response_model=DashboardStatsResponse)
def get_dashboard(
    db: Session = Depends(get_db),
    service: MonitoringService = Depends(get_service),
    _user=Depends(_require_operator()),
) -> DashboardStatsResponse:
    """Dashboard con estadisticas agregadas de todos los dominios."""
    return DashboardStatsResponse.model_validate(service.get_dashboard_stats(db))


@router.get(
    "/monitoring/analyses",
    response_model=PaginatedResponse[AnalisisGeeResponse],
)
def list_analyses(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    tipo: Optional[str] = None,
    db: Session = Depends(get_db),
    service: MonitoringService = Depends(get_service),
    _user=Depends(_require_operator()),
) -> PaginatedResponse[AnalisisGeeResponse]:
    """Historial de analisis GEE con paginacion."""
    items, total = service.list_analyses(db, page=page, limit=limit, tipo=tipo)
    return PaginatedResponse[AnalisisGeeResponse].create(
        items=[AnalisisGeeResponse.model_validate(a) for a in items],
        total=total,
        page=page,
        limit=limit,
    )


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
