"""FastAPI router for the reuniones domain."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.reuniones.schemas import (
    AgendaItemCreate,
    AgendaItemResponse,
    ReunionCreate,
    ReunionCreateResponse,
    ReunionListResponse,
    ReunionResponse,
    ReunionUpdate,
)
from app.domains.reuniones.service import ReunionService

router = APIRouter(prefix="/reuniones", tags=["reuniones"])


def get_service() -> ReunionService:
    """Dependency that provides the service instance."""
    return ReunionService()


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
# REUNIONES CRUD
# ──────────────────────────────────────────────


@router.get("", response_model=dict)
def list_reuniones(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    estado: Optional[str] = None,
    tipo: Optional[str] = None,
    db: Session = Depends(get_db),
    service: ReunionService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Listar reuniones con paginacion y filtros."""
    items, total = service.list_reuniones(
        db, page=page, limit=limit, estado=estado, tipo=tipo
    )
    return {
        "items": [ReunionListResponse.model_validate(r) for r in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.post("", response_model=ReunionCreateResponse, status_code=201)
def create_reunion(
    payload: ReunionCreate,
    db: Session = Depends(get_db),
    service: ReunionService = Depends(get_service),
    user=Depends(_require_operator()),
):
    """Crear una nueva reunion (requiere operador)."""
    reunion = service.create(db, payload, usuario_id=uuid.UUID(str(user.id)))
    return ReunionCreateResponse(
        id=reunion.id,
        message="Reunion creada exitosamente.",
        estado=reunion.estado,
    )


@router.get("/{reunion_id}", response_model=ReunionResponse)
def get_reunion(
    reunion_id: uuid.UUID,
    db: Session = Depends(get_db),
    service: ReunionService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Obtener detalle de una reunion con agenda items."""
    return service.get_by_id(db, reunion_id)


@router.patch("/{reunion_id}", response_model=ReunionResponse)
def update_reunion(
    reunion_id: uuid.UUID,
    payload: ReunionUpdate,
    db: Session = Depends(get_db),
    service: ReunionService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Actualizar una reunion (requiere operador)."""
    return service.update(db, reunion_id, payload)


@router.delete("/{reunion_id}", status_code=204)
def delete_reunion(
    reunion_id: uuid.UUID,
    db: Session = Depends(get_db),
    service: ReunionService = Depends(get_service),
    _user=Depends(_require_admin()),
):
    """Eliminar una reunion (requiere admin)."""
    service.delete(db, reunion_id)


# ──────────────────────────────────────────────
# AGENDA ITEMS
# ──────────────────────────────────────────────


@router.get("/{reunion_id}/agenda", response_model=list[AgendaItemResponse])
def list_agenda_items(
    reunion_id: uuid.UUID,
    db: Session = Depends(get_db),
    service: ReunionService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Listar items de la agenda de una reunion."""
    return service.get_agenda_items(db, reunion_id)


@router.post(
    "/{reunion_id}/agenda",
    response_model=AgendaItemResponse,
    status_code=201,
)
def add_agenda_item(
    reunion_id: uuid.UUID,
    payload: AgendaItemCreate,
    db: Session = Depends(get_db),
    service: ReunionService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Agregar un tema a la agenda (requiere operador)."""
    return service.add_agenda_item(db, reunion_id, payload)


@router.delete("/{reunion_id}/agenda/{item_id}", status_code=204)
def delete_agenda_item(
    reunion_id: uuid.UUID,
    item_id: uuid.UUID,
    db: Session = Depends(get_db),
    service: ReunionService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Eliminar un tema de la agenda (requiere operador)."""
    service.delete_agenda_item(db, reunion_id, item_id)


# ──────────────────────────────────────────────
# PDF EXPORT
# ──────────────────────────────────────────────


@router.get("/{reunion_id}/export-pdf")
def export_reunion_pdf(
    reunion_id: uuid.UUID,
    db: Session = Depends(get_db),
    service: ReunionService = Depends(get_service),
    _user=Depends(_require_operator()),
):
    """Exportar agenda de reunion como PDF (requiere operador)."""
    from app.shared.pdf import build_reunion_pdf, get_branding

    reunion = service.get_by_id(db, reunion_id)
    branding = get_branding(db)
    pdf_buffer = build_reunion_pdf(reunion, branding)

    filename = f"reunion-{reunion_id}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
