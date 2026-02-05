"""
Infrastructure and Reporting Endpoints.
"""

from fastapi import APIRouter, HTTPException, Depends, Response
from typing import List, Dict, Any, Optional
from uuid import UUID

from app.services.infrastructure_service import get_infrastructure_service
from app.services.pdf_service import get_pdf_service
from app.auth import User, get_current_user

router = APIRouter()

@router.get("/assets")
async def list_assets(
    cuenca: Optional[str] = None,
    user: User = Depends(get_current_user)
):
    """List all infrastructure assets."""
    service = get_infrastructure_service()
    return service.get_all_assets(cuenca)

@router.post("/assets")
async def create_asset(
    asset_data: Dict[str, Any],
    user: User = Depends(get_current_user)
):
    """Register a new point of interest/infrastructure asset."""
    if user.rol not in ["admin", "operador"]:
        raise HTTPException(status_code=403, detail="No tienes permisos para registrar activos")
    
    service = get_infrastructure_service()
    return service.create_asset(asset_data)

@router.get("/potential-intersections")
async def get_intersections(
    user: User = Depends(get_current_user)
):
    """Get points where roads cross drainage (potential culverts)."""
    service = get_infrastructure_service()
    return service.get_potential_intersections()

@router.get("/assets/{asset_id}/history")
async def get_asset_history(
    asset_id: UUID,
    user: User = Depends(get_current_user)
):
    """Get history for a specific asset."""
    service = get_infrastructure_service()
    return service.get_asset_history(asset_id)

@router.get("/assets/{asset_id}/export-pdf")
async def export_asset_pdf(
    asset_id: UUID,
    user: User = Depends(get_current_user)
):
    """Export technical sheet for a specific asset."""
    service = get_infrastructure_service()
    pdf_service = get_pdf_service()
    
    asset = service.db.client.table("infraestructura").select("*").eq("id", str(asset_id)).single().execute().data
    history = service.get_asset_history(asset_id)
    
    pdf_buffer = pdf_service.create_asset_ficha_pdf(asset, history)
    return Response(
        content=pdf_buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=ficha_activo_{asset_id}.pdf"}
    )

@router.post("/maintenance")
async def add_maintenance(
    log_data: Dict[str, Any],
    user: User = Depends(get_current_user)
):
    """Record a new maintenance activity."""
    if user.rol not in ["admin", "operador"]:
        raise HTTPException(status_code=403, detail="No tienes permisos para registrar mantenimiento")
    
    service = get_infrastructure_service()
    return service.add_maintenance_log(log_data)

@router.get("/export-pdf")
async def export_pdf_report(
    user: User = Depends(get_current_user)
):
    """
    Export a professional situation report in PDF.
    """
    pdf_service = get_pdf_service()
    
    # Mock data for now - in a real scenario we'd fetch this from GEE and Supabase
    report_data = {
        "cuenca": "Consorcio 10 de Mayo",
        "stats": [
            {"nombre": "Cuenca Candil", "ha": 450, "pct": 12, "estado": "Alerta"},
            {"nombre": "Cuenca ML", "ha": 120, "pct": 3, "estado": "Normal"},
            {"nombre": "Cuenca Noroeste", "ha": 890, "pct": 24, "estado": "Crítico"},
        ],
        "recent_maintenance": [
            {"fecha": "01/02/2026", "nombre": "Canal Principal A", "tarea": "Limpieza malezas", "estado": "Completado"},
            {"fecha": "03/02/2026", "nombre": "Alcantarilla Km 12", "tarea": "Desobstrucción", "estado": "Completado"},
        ]
    }
    
    pdf_buffer = pdf_service.create_emergency_report(report_data)
    
    return Response(
        content=pdf_buffer.getvalue(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": "attachment; filename=informe_situacion.pdf"
        }
    )
