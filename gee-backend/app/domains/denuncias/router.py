"""FastAPI router for the denuncias domain."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.denuncias.schemas import (
    DenunciaCreate,
    DenunciaCreateResponse,
    DenunciaListResponse,
    DenunciaResponse,
    DenunciaUpdate,
)
from app.domains.denuncias.service import DenunciaService

router = APIRouter(prefix="/denuncias", tags=["denuncias"])


def get_service() -> DenunciaService:
    """Dependency that provides the service instance."""
    return DenunciaService()


# ──────────────────────────────────────────────
# PUBLIC
# ──────────────────────────────────────────────


@router.post("", response_model=DenunciaCreateResponse, status_code=201)
def create_denuncia(
    payload: DenunciaCreate,
    db: Session = Depends(get_db),
    service: DenunciaService = Depends(get_service),
):
    """
    Crear una denuncia publica.

    No requiere autenticacion — cualquier ciudadano puede reportar
    problemas en la red de canales y caminos rurales.
    """
    denuncia = service.create(db, payload)
    return DenunciaCreateResponse(
        id=denuncia.id,
        message="Denuncia creada exitosamente. Gracias por colaborar.",
        estado=denuncia.estado,
    )


# ──────────────────────────────────────────────
# PROTECTED (operator+)
# ──────────────────────────────────────────────

# Lazy import to avoid circular deps at module level.
# The auth module depends on config which may not be ready
# when this file is first imported during tests.


def _require_operator():
    """Return the operator dependency at call time."""
    from app.auth import require_admin_or_operator

    return require_admin_or_operator


@router.get("/stats", response_model=dict)
def get_stats(
    db: Session = Depends(get_db),
    service: DenunciaService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Estadisticas agregadas de denuncias (requiere operador)."""
    return service.get_stats(db)


@router.get("", response_model=dict)
def list_denuncias(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    estado: Optional[str] = None,
    cuenca: Optional[str] = None,
    db: Session = Depends(get_db),
    service: DenunciaService = Depends(get_service),
):
    """Listar denuncias con paginacion y filtros."""
    items, total = service.list_denuncias(
        db, page=page, limit=limit, estado=estado, cuenca=cuenca
    )
    return {
        "items": [DenunciaListResponse.model_validate(d) for d in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/{denuncia_id}", response_model=DenunciaResponse)
def get_denuncia(
    denuncia_id: uuid.UUID,
    db: Session = Depends(get_db),
    service: DenunciaService = Depends(get_service),
):
    """Obtener detalle de una denuncia con historial."""
    return service.get_by_id(db, denuncia_id)


@router.patch("/{denuncia_id}", response_model=DenunciaResponse)
def update_denuncia(
    denuncia_id: uuid.UUID,
    payload: DenunciaUpdate,
    db: Session = Depends(get_db),
    service: DenunciaService = Depends(get_service),
    user=Depends(_require_operator()),
):
    """Actualizar estado/respuesta de una denuncia (requiere operador)."""
    return service.update(db, denuncia_id, payload, operator_id=uuid.UUID(str(user.id)))
