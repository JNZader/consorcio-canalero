"""
Finance Endpoints.
"""

from fastapi import APIRouter, HTTPException, Depends, Query, Response
from typing import List, Dict, Any, Optional
from uuid import UUID

from app.services.finance_service import get_finance_service
from app.services.pdf_service import get_pdf_service
from app.auth import User, get_current_user

router = APIRouter()

@router.get("/gastos")
async def list_gastos(
    categoria: Optional[str] = Query(None),
    user: User = Depends(get_current_user)
):
    service = get_finance_service()
    return service.get_gastos(categoria)

@router.post("/gastos")
async def add_gasto(
    data: Dict[str, Any],
    user: User = Depends(get_current_user)
):
    if user.rol not in ["admin", "operador"]:
        raise HTTPException(status_code=403, detail="No autorizado")
    service = get_finance_service()
    return service.create_gasto(data)

@router.get("/presupuestos")
async def list_presupuestos(user: User = Depends(get_current_user)):
    service = get_finance_service()
    return service.get_presupuestos()

@router.get("/balance-summary/{anio}")
async def get_summary(anio: int, user: User = Depends(get_current_user)):
    service = get_finance_service()
    return service.get_balance_summary(anio)

@router.get("/export-presupuesto/{anio}")
async def export_presupuesto_pdf(anio: int, user: User = Depends(get_current_user)):
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
