"""FastAPI router for the infraestructura domain."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.infraestructura.schemas import (
    AssetCreate,
    AssetListResponse,
    AssetResponse,
    AssetUpdate,
    MantenimientoLogCreate,
    MantenimientoLogResponse,
)
from app.domains.infraestructura.service import InfraestructuraService

router = APIRouter(prefix="/infraestructura", tags=["infraestructura"])


def get_service() -> InfraestructuraService:
    """Dependency that provides the service instance."""
    return InfraestructuraService()


# Lazy import to avoid circular deps at module level.
def _require_operator():
    """Return the operator dependency at call time."""
    from app.auth import require_admin_or_operator

    return require_admin_or_operator


# ──────────────────────────────────────────────
# ASSETS
# ──────────────────────────────────────────────


@router.get("/assets", response_model=dict)
def list_assets(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    tipo: Optional[str] = None,
    estado: Optional[str] = None,
    db: Session = Depends(get_db),
    service: InfraestructuraService = Depends(get_service),
):
    """Listar assets de infraestructura con paginacion y filtros."""
    items, total = service.list_assets(
        db, page=page, limit=limit, tipo=tipo, estado=estado
    )
    return {
        "items": [AssetListResponse.model_validate(a) for a in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/assets/{asset_id}", response_model=AssetResponse)
def get_asset(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
    service: InfraestructuraService = Depends(get_service),
):
    """Obtener detalle de un asset."""
    return service.get_asset(db, asset_id)


@router.post("/assets", response_model=AssetResponse, status_code=201)
def create_asset(
    payload: AssetCreate,
    db: Session = Depends(get_db),
    service: InfraestructuraService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Crear un nuevo asset de infraestructura (requiere operador)."""
    return service.create_asset(db, payload)


@router.patch("/assets/{asset_id}", response_model=AssetResponse)
def update_asset(
    asset_id: uuid.UUID,
    payload: AssetUpdate,
    db: Session = Depends(get_db),
    service: InfraestructuraService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Actualizar un asset existente (requiere operador)."""
    return service.update_asset(db, asset_id, payload)


# ──────────────────────────────────────────────
# MAINTENANCE HISTORY
# ──────────────────────────────────────────────


@router.get("/assets/{asset_id}/history", response_model=dict)
def get_asset_history(
    asset_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    service: InfraestructuraService = Depends(get_service),
):
    """Historial de mantenimiento de un asset."""
    items, total = service.get_asset_history(
        db, asset_id, page=page, limit=limit
    )
    return {
        "items": [MantenimientoLogResponse.model_validate(m) for m in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.post(
    "/assets/{asset_id}/maintenance",
    response_model=MantenimientoLogResponse,
    status_code=201,
)
def add_maintenance_log(
    asset_id: uuid.UUID,
    payload: MantenimientoLogCreate,
    db: Session = Depends(get_db),
    service: InfraestructuraService = Depends(get_service),
    user=Depends(_require_operator()),
):
    """Registrar actividad de mantenimiento (requiere operador)."""
    return service.add_maintenance_log(
        db, asset_id, payload, usuario_id=uuid.UUID(str(user.id))
    )


# ──────────────────────────────────────────────
# STATS
# ──────────────────────────────────────────────


@router.get("/stats", response_model=dict)
def get_stats(
    db: Session = Depends(get_db),
    service: InfraestructuraService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Estadisticas agregadas de infraestructura (requiere operador)."""
    return service.get_stats(db)
