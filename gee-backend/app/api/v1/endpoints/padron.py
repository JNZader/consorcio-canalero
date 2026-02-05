"""
Padron and Payments Endpoints.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Dict, Any, Optional
from uuid import UUID

from app.services.padron_service import get_padron_service
from app.auth import User, get_current_user

router = APIRouter()

@router.get("/consorcistas")
async def list_consorcistas(
    search: Optional[str] = Query(None),
    user: User = Depends(get_current_user)
):
    service = get_padron_service()
    return service.get_consorcistas(search)

@router.post("/consorcistas")
async def add_consorcista(
    data: Dict[str, Any],
    user: User = Depends(get_current_user)
):
    if user.rol != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores pueden editar el padron")
    service = get_padron_service()
    return service.create_consorcista(data)

@router.get("/consorcistas/{consorcista_id}/pagos")
async def get_pagos(
    consorcista_id: UUID,
    user: User = Depends(get_current_user)
):
    service = get_padron_service()
    return service.get_pagos_by_consorcista(consorcista_id)

@router.post("/pagos")
async def register_payment(
    data: Dict[str, Any],
    user: User = Depends(get_current_user)
):
    if user.rol not in ["admin", "operador"]:
        raise HTTPException(status_code=403, detail="No autorizado")
    service = get_padron_service()
    return service.registrar_pago(data)
