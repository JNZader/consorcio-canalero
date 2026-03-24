"""FastAPI router for the padron domain."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.padron.schemas import (
    ConsorcistaCreate,
    ConsorcistaListResponse,
    ConsorcistaResponse,
    ConsorcistaUpdate,
    CsvImportResponse,
)
from app.domains.padron.service import PadronService

router = APIRouter(prefix="/padron", tags=["padron"])


def get_service() -> PadronService:
    """Dependency that provides the service instance."""
    return PadronService()


# Lazy import to avoid circular deps at module level.
def _require_operator():
    """Return the operator dependency at call time."""
    from app.auth import require_admin_or_operator

    return require_admin_or_operator


def _require_admin():
    """Return the admin dependency at call time."""
    from app.auth import require_admin

    return require_admin


# ──────────────────────────────────────────────
# STATS (must be before /{id} to avoid route conflict)
# ──────────────────────────────────────────────


@router.get("/stats", response_model=dict)
def get_stats(
    db: Session = Depends(get_db),
    service: PadronService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Estadisticas agregadas del padron (requiere operador)."""
    return service.get_stats(db)


# ──────────────────────────────────────────────
# LIST & DETAIL
# ──────────────────────────────────────────────


@router.get("", response_model=dict)
def list_consorcistas(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    estado: Optional[str] = None,
    categoria: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    service: PadronService = Depends(get_service),
):
    """Listar consorcistas con paginacion, filtros y busqueda."""
    items, total = service.list_consorcistas(
        db,
        page=page,
        limit=limit,
        estado=estado,
        categoria=categoria,
        search=search,
    )
    return {
        "items": [ConsorcistaListResponse.model_validate(c) for c in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/{consorcista_id}", response_model=ConsorcistaResponse)
def get_consorcista(
    consorcista_id: uuid.UUID,
    db: Session = Depends(get_db),
    service: PadronService = Depends(get_service),
):
    """Obtener detalle de un consorcista."""
    return service.get_by_id(db, consorcista_id)


# ──────────────────────────────────────────────
# WRITE (operator+)
# ──────────────────────────────────────────────


@router.post("", response_model=ConsorcistaResponse, status_code=201)
def create_consorcista(
    payload: ConsorcistaCreate,
    db: Session = Depends(get_db),
    service: PadronService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Crear un nuevo consorcista (requiere operador)."""
    return service.create(db, payload)


@router.patch("/{consorcista_id}", response_model=ConsorcistaResponse)
def update_consorcista(
    consorcista_id: uuid.UUID,
    payload: ConsorcistaUpdate,
    db: Session = Depends(get_db),
    service: PadronService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Actualizar un consorcista existente (requiere operador)."""
    return service.update(db, consorcista_id, payload)


# ──────────────────────────────────────────────
# IMPORT (admin only)
# ──────────────────────────────────────────────


@router.post("/import", response_model=CsvImportResponse)
async def import_consorcistas(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    service: PadronService = Depends(get_service),
    _user=Depends(_require_admin()),
):
    """Importar consorcistas desde CSV/XLSX (requiere admin)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nombre de archivo requerido")

    if not file.filename.lower().endswith((".csv", ".xls", ".xlsx")):
        raise HTTPException(
            status_code=400,
            detail="Formato no soportado. Use archivos CSV, XLS o XLSX",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Archivo vacio")

    try:
        result = service.import_csv(db, content, file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return CsvImportResponse(
        filename=file.filename,
        **result,
    )
