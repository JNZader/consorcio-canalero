"""FastAPI router for the capas (map layers) domain."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.capas.schemas import (
    CapaCreate,
    CapaListResponse,
    CapaReorder,
    CapaResponse,
    CapaUpdate,
)
from app.domains.capas.service import CapasService

router = APIRouter(prefix="/capas", tags=["capas"])


def get_service() -> CapasService:
    """Dependency that provides the service instance."""
    return CapasService()


# Lazy imports to avoid circular deps at module level.
def _require_operator():
    """Return the operator dependency at call time."""
    from app.auth import require_admin_or_operator

    return require_admin_or_operator


def _require_admin():
    """Return the admin dependency at call time."""
    from app.auth import require_admin

    return require_admin


# ──────────────────────────────────────────────
# PUBLIC
# ──────────────────────────────────────────────


@router.get("/public", response_model=list[CapaListResponse])
def list_public_capas(
    db: Session = Depends(get_db),
    service: CapasService = Depends(get_service),
):
    """
    Capas publicas para el visor sin autenticacion.

    Solo devuelve capas con es_publica=True y visible=True.
    """
    return service.list_public(db)


# ──────────────────────────────────────────────
# PROTECTED (operator+)
# ──────────────────────────────────────────────


@router.get("", response_model=list[CapaListResponse])
def list_capas(
    visible_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    service: CapasService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Listar todas las capas (requiere operador)."""
    return service.list_capas(db, visible_only=visible_only)


@router.get("/{capa_id}", response_model=CapaResponse)
def get_capa(
    capa_id: uuid.UUID,
    db: Session = Depends(get_db),
    service: CapasService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Obtener detalle de una capa (requiere operador)."""
    return service.get_by_id(db, capa_id)


@router.post("", response_model=CapaResponse, status_code=201)
def create_capa(
    payload: CapaCreate,
    db: Session = Depends(get_db),
    service: CapasService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Crear una nueva capa (requiere operador)."""
    return service.create(db, payload)


@router.patch("/{capa_id}", response_model=CapaResponse)
def update_capa(
    capa_id: uuid.UUID,
    payload: CapaUpdate,
    db: Session = Depends(get_db),
    service: CapasService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Actualizar una capa (requiere operador)."""
    return service.update(db, capa_id, payload)


@router.delete("/{capa_id}", status_code=204)
def delete_capa(
    capa_id: uuid.UUID,
    db: Session = Depends(get_db),
    service: CapasService = Depends(get_service),
    _user=Depends(_require_admin()),
):
    """Eliminar una capa (requiere admin)."""
    service.delete(db, capa_id)


@router.put("/reorder", response_model=dict)
def reorder_capas(
    payload: CapaReorder,
    db: Session = Depends(get_db),
    service: CapasService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Reordenar capas (requiere operador)."""
    count = service.reorder(db, payload.ordered_ids)
    return {"message": "Orden actualizado", "count": count}
