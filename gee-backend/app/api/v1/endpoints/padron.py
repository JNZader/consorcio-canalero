"""
Padron and Payments Endpoints.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from uuid import UUID

from app.services.padron_service import get_padron_service
from app.auth import User, require_admin_or_operator, require_authenticated
from app.api.v1.schemas import ConsorcistaCreate, ConsorcistaUpdate, PagoCreate

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
