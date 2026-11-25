"""FastAPI router for the Documentos domain."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.config import settings
from app.domains.documentos.schemas import DocumentoDetalle, DocumentoListResponse
from app.domains.documentos.service import (
    DocumentoNotFound,
    get_detalle,
    list_resumenes,
    open_archivo_stream,
)

router = APIRouter(prefix="/documentos", tags=["documentos"])


def _require_operator():
    from app.auth import require_admin_or_operator

    return require_admin_or_operator


@router.get("", response_model=DocumentoListResponse)
def list_documentos_endpoint(
    group: str | None = Query(default=None),
    _user=Depends(_require_operator()),
) -> DocumentoListResponse:
    """List Documentos catalog summaries (operator+)."""
    return list_resumenes(group=group)


@router.get("/{dossier_id}", response_model=DocumentoDetalle)
def get_documento_endpoint(
    dossier_id: str,
    _user=Depends(_require_operator()),
) -> DocumentoDetalle:
    """Dossier detail including public file descriptors."""
    try:
        return get_detalle(dossier_id)
    except DocumentoNotFound as exc:
        raise HTTPException(status_code=404, detail="Documento no encontrado") from exc


@router.get("/{dossier_id}/archivo/{file_id}")
def download_archivo_endpoint(
    dossier_id: str,
    file_id: str,
    _user=Depends(_require_operator()),
) -> StreamingResponse:
    """Stream an attachment as Content-Disposition: attachment."""
    try:
        archivo, _path, chunks = open_archivo_stream(settings.documentos_root, dossier_id, file_id)
    except DocumentoNotFound as exc:
        raise HTTPException(status_code=404, detail="Archivo no encontrado") from exc

    headers = {
        "Content-Disposition": f'attachment; filename="{archivo.nombre}"',
    }
    return StreamingResponse(
        chunks,
        media_type=archivo.mime or "application/octet-stream",
        headers=headers,
    )
