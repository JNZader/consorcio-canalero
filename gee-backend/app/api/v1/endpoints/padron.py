"""
Padron and Payments Endpoints.
"""

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from typing import Optional
from uuid import UUID

from app.services.padron_service import get_padron_service
from app.auth import User, require_admin_or_operator, require_authenticated
from app.api.v1.schemas import ConsorcistaCreate, PagoCreate

router = APIRouter()


@router.get("/consorcistas")
async def list_consorcistas(
    search: Optional[str] = Query(None),
    user: User = Depends(require_authenticated),
):
    service = get_padron_service()
    return service.get_consorcistas(search)


@router.post("/consorcistas")
async def add_consorcista(
    data: ConsorcistaCreate,
    user: User = Depends(require_admin_or_operator),
):
    service = get_padron_service()
    return service.create_consorcista(data.model_dump(exclude_unset=True))


@router.get("/consorcistas/{consorcista_id}/pagos")
async def get_pagos(
    consorcista_id: UUID,
    user: User = Depends(require_authenticated),
):
    service = get_padron_service()
    return service.get_pagos_by_consorcista(consorcista_id)


@router.post("/pagos")
async def register_payment(
    data: PagoCreate,
    user: User = Depends(require_admin_or_operator),
):
    service = get_padron_service()
    return service.registrar_pago(data.model_dump(exclude_unset=True))


@router.post("/consorcistas/import")
async def import_consorcistas(
    file: UploadFile = File(...),
    user: User = Depends(require_admin_or_operator),
):
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

    service = get_padron_service()

    try:
        result = service.import_consorcistas(file.filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "filename": file.filename,
        **result,
    }
