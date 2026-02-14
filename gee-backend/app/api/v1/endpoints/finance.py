"""
Finance Endpoints.
"""

from fastapi import APIRouter, HTTPException, Depends, Query, Response
from typing import List, Optional
from uuid import UUID

from app.services.finance_service import get_finance_service
from app.services.pdf_service import get_pdf_service
from app.auth import User, require_admin_or_operator, require_authenticated
from app.api.v1.schemas import GastoCreate, PresupuestoCreate

router = APIRouter()

@router.get("/gastos")
async def list_gastos(
    categoria: Optional[str] = Query(None),
    user: User = Depends(require_authenticated),
):
    service = get_finance_service()
    return service.get_gastos(categoria)

@router.post("/gastos")
async def add_gasto(
    data: GastoCreate,
    user: User = Depends(require_admin_or_operator),
):
    service = get_finance_service()
    return service.create_gasto(data.model_dump(exclude_unset=True))

@router.get("/presupuestos")
async def list_presupuestos(
    user: User = Depends(require_authenticated),
):
    service = get_finance_service()
    return service.get_presupuestos()

@router.get("/balance-summary/{anio}")
async def get_summary(
    anio: int,
    user: User = Depends(require_authenticated),
):
    service = get_finance_service()
    return service.get_balance_summary(anio)

@router.get("/export-presupuesto/{anio}")
async def export_presupuesto_pdf(
    anio: int,
    user: User = Depends(require_authenticated),
):
    """Generates a PDF for the general assembly."""
    finance = get_finance_service()
    pdf_service = get_pdf_service()

    summary = finance.get_balance_summary(anio)
    gastos = finance.get_gastos() # Filter by year in real case

    # Mock structure for PDF generation
    report_data = {
        "anio": anio,
        "summary": summary,
        "gastos_detalle": gastos
    }

    # We'll need to implement create_presupuesto_pdf in pdf_service later
    # For now, using a placeholder logic
    return {"message": "PDF Generation logic pending in pdf_service", "data": report_data}
