"""FastAPI router for the tramites domain."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.tramites.schemas import (
    SeguimientoCreate,
    SeguimientoResponse,
    TramiteCreate,
    TramiteCreateResponse,
    TramiteListResponse,
    TramiteResponse,
    TramiteUpdate,
)
from app.domains.tramites.service import TramiteService

router = APIRouter(prefix="/tramites", tags=["tramites"])


def get_service() -> TramiteService:
    """Dependency that provides the service instance."""
    return TramiteService()


# Lazy import to avoid circular deps at module level.
def _require_operator():
    """Return the operator dependency at call time."""
    from app.auth import require_admin_or_operator

    return require_admin_or_operator


# ──────────────────────────────────────────────
# PROTECTED (operator+)
# ──────────────────────────────────────────────


@router.get("/stats", response_model=dict)
def get_stats(
    db: Session = Depends(get_db),
    service: TramiteService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Estadisticas agregadas de tramites (requiere operador)."""
    return service.get_stats(db)


@router.get("", response_model=dict)
def list_tramites(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    estado: Optional[str] = None,
    tipo: Optional[str] = None,
    prioridad: Optional[str] = None,
    db: Session = Depends(get_db),
    service: TramiteService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Listar tramites con paginacion y filtros."""
    items, total = service.list_tramites(
        db, page=page, limit=limit, estado=estado, tipo=tipo, prioridad=prioridad
    )
    return {
        "items": [TramiteListResponse.model_validate(t) for t in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/{tramite_id}", response_model=TramiteResponse)
def get_tramite(
    tramite_id: uuid.UUID,
    db: Session = Depends(get_db),
    service: TramiteService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Obtener detalle de un tramite con historial de seguimiento."""
    return service.get_by_id(db, tramite_id)


@router.post("", response_model=TramiteCreateResponse, status_code=201)
def create_tramite(
    payload: TramiteCreate,
    db: Session = Depends(get_db),
    service: TramiteService = Depends(get_service),
    user=Depends(_require_operator()),
):
    """Crear un nuevo tramite (requiere operador)."""
    tramite = service.create(db, payload, usuario_id=uuid.UUID(user.id))
    return TramiteCreateResponse(
        id=tramite.id,
        message="Tramite creado exitosamente.",
        estado=tramite.estado,
    )


@router.patch("/{tramite_id}", response_model=TramiteResponse)
def update_tramite(
    tramite_id: uuid.UUID,
    payload: TramiteUpdate,
    db: Session = Depends(get_db),
    service: TramiteService = Depends(get_service),
    user=Depends(_require_operator()),
):
    """Actualizar estado/resolucion de un tramite (requiere operador)."""
    return service.update(db, tramite_id, payload, operator_id=uuid.UUID(user.id))


@router.post(
    "/{tramite_id}/seguimiento",
    response_model=SeguimientoResponse,
    status_code=201,
)
def add_seguimiento(
    tramite_id: uuid.UUID,
    payload: SeguimientoCreate,
    db: Session = Depends(get_db),
    service: TramiteService = Depends(get_service),
    user=Depends(_require_operator()),
):
    """Agregar seguimiento a un tramite (requiere operador)."""
    return service.add_seguimiento(
        db, tramite_id, payload, operator_id=uuid.UUID(user.id)
    )
