"""
Infrastructure and Reporting Endpoints.
"""

from fastapi import APIRouter, HTTPException, Depends, Response
from typing import List, Optional
from uuid import UUID

from app.services.infrastructure_service import get_infrastructure_service
from app.services.pdf_service import get_pdf_service
from app.auth import User, require_admin_or_operator, require_authenticated
from app.api.v1.schemas import AssetCreate, AssetUpdate, MaintenanceLogCreate

router = APIRouter()

@router.get("/assets")
async def list_assets(
    cuenca: Optional[str] = None,
    user: User = Depends(require_authenticated),
):
    """List all infrastructure assets."""
    service = get_infrastructure_service()
    return service.get_all_assets(cuenca)

@router.post("/assets")
async def create_asset(
    asset_data: AssetCreate,
    user: User = Depends(require_admin_or_operator),
):
    """Register a new point of interest/infrastructure asset."""
    service = get_infrastructure_service()
    return service.create_asset(asset_data.model_dump(exclude_unset=True))

@router.get("/potential-intersections")
async def get_intersections(
    user: User = Depends(require_authenticated),
):
    """Get points where roads cross drainage (potential culverts)."""
    service = get_infrastructure_service()
    return service.get_potential_intersections()

@router.get("/assets/{asset_id}/history")
async def get_asset_history(
    asset_id: UUID,
    user: User = Depends(require_authenticated),
):
    """Get history for a specific asset."""
    service = get_infrastructure_service()
    return service.get_asset_history(asset_id)

@router.get("/assets/{asset_id}/export-pdf")
async def export_asset_pdf(
    asset_id: UUID,
    user: User = Depends(require_authenticated),
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
    log_data: MaintenanceLogCreate,
    user: User = Depends(require_admin_or_operator),
):
    """Record a new maintenance activity."""
    service = get_infrastructure_service()
    return service.add_maintenance_log(log_data.model_dump(exclude_unset=True))

@router.get("/export-pdf")
async def export_pdf_report(
    user: User = Depends(require_authenticated),
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
            {"nombre": "Cuenca Noroeste", "ha": 890, "pct": 24, "estado": "Critico"},
        ],
        "recent_maintenance": [
            {"fecha": "01/02/2026", "nombre": "Canal Principal A", "tarea": "Limpieza malezas", "estado": "Completado"},
            {"fecha": "03/02/2026", "nombre": "Alcantarilla Km 12", "tarea": "Desobstruccion", "estado": "Completado"},
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
