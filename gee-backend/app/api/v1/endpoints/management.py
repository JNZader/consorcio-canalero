"""
Management and Tracking Endpoints.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
from uuid import UUID

from app.services.management_service import get_management_service
from app.auth import User, get_current_user

router = APIRouter()

# --- Trámites Provinciales ---

@router.get("/tramites")
async def list_tramites(
    estado: Optional[str] = None,
    user: User = Depends(get_current_user)
):
    """List administrative procedures."""
    service = get_management_service()
    return service.get_tramites(estado)

@router.post("/tramites")
async def create_tramite(
    data: Dict[str, Any],
    user: User = Depends(get_current_user)
):
    """Create a new administrative procedure."""
    if user.rol not in ["admin", "operador"]:
        raise HTTPException(status_code=403, detail="No autorizado")
    service = get_management_service()
    return service.create_tramite(data)

@router.get("/tramites/{tramite_id}")
async def get_tramite(
    tramite_id: UUID,
    user: User = Depends(get_current_user)
):
    """Get full detail of a procedure including its advances."""
    service = get_management_service()
    return service.get_tramite_detalle(tramite_id)

@router.post("/tramites/avance")
async def add_tramite_avance(
    data: Dict[str, Any],
    user: User = Depends(get_current_user)
):
    """Add a progress update to a procedure."""
    service = get_management_service()
    return service.add_tramite_avance(data)

# --- Trazabilidad (Seguimiento) ---

@router.get("/seguimiento/{entidad_tipo}/{entidad_id}")
async def get_history(
    entidad_tipo: str,
    entidad_id: UUID,
    user: User = Depends(get_current_user)
):
    """Get management history for a report or suggestion."""
    if entidad_tipo not in ["reporte", "sugerencia"]:
        raise HTTPException(status_code=400, detail="Tipo de entidad invalido")
    service = get_management_service()
    return service.get_historial_entidad(entidad_tipo, entidad_id)

@router.post("/seguimiento")
async def add_history_entry(
    data: Dict[str, Any],
    user: User = Depends(get_current_user)
):
    """Update status and add management log for a report or suggestion."""
    if user.rol not in ["admin", "operador"]:
        raise HTTPException(status_code=403, detail="No autorizado")
    
    service = get_management_service()
    # Add the current user ID to the log
    data["usuario_gestion"] = str(user.id)
    return service.add_seguimiento(data)

# --- Reuniones ---

@router.get("/reuniones")
async def list_reuniones(
    user: User = Depends(get_current_user)
):
    """List all meetings."""
    service = get_management_service()
    return service.get_reuniones()

@router.post("/reuniones")
async def create_reunion(
    data: Dict[str, Any],
    user: User = Depends(get_current_user)
):
    """Create a new meeting."""
    service = get_management_service()
    return service.create_reunion(data)

@router.get("/reuniones/{reunion_id}/agenda")
async def get_agenda(
    reunion_id: UUID,
    user: User = Depends(get_current_user)
):
    """Get the agenda items for a specific meeting."""
    service = get_management_service()
    return service.get_agenda_detalle(reunion_id)

@router.post("/reuniones/{reunion_id}/agenda")
async def add_item(
    reunion_id: UUID,
    payload: Dict[str, Any],
    user: User = Depends(get_current_user)
):
    """Add a new item to the meeting agenda with references."""
    service = get_management_service()
    item_data = payload.get("item", {})
    referencias = payload.get("referencias", [])
    return service.add_agenda_item(reunion_id, item_data, referencias)

@router.get("/tramites/{tramite_id}/export-pdf")
async def export_tramite_pdf(tramite_id: UUID, user: User = Depends(get_current_user)):
    service = get_management_service()
    pdf_service = get_pdf_service()
    detail = service.get_tramite_detalle(tramite_id)
    pdf_buffer = pdf_service.create_tramite_summary_pdf(detail, detail['avances'])
    return Response(content=pdf_buffer.getvalue(), media_type="application/pdf")

@router.get("/seguimiento/reporte/{reporte_id}/export-pdf")
async def export_resolution_pdf(reporte_id: UUID, user: User = Depends(get_current_user)):
    service = get_management_service()
    pdf_service = get_pdf_service()
    reporte = service.db.client.table("denuncias").select("*").eq("id", str(reporte_id)).single().execute().data
    seguimiento = service.get_historial_entidad("reporte", reporte_id)
    pdf_buffer = pdf_service.create_report_resolution_pdf(reporte, seguimiento)
    return Response(content=pdf_buffer.getvalue(), media_type="application/pdf")

@router.get("/export-gestion-integral")
async def export_integral_report(user: User = Depends(get_current_user)):
    service = get_management_service()
    pdf_service = get_pdf_service()
    # Mock aggregation for demo
    data = {
        "satelite": [{"nombre": "Candil", "pct": 5, "estado": "Normal"}, {"nombre": "ML", "pct": 15, "estado": "Alerta"}],
        "cuencas_data": {
            "candil": {"reportes_count": 3, "sugerencias_count": 1},
            "ml": {"reportes_count": 12, "sugerencias_count": 5}
        }
    }
    pdf_buffer = pdf_service.create_general_impact_report_pdf(data)
    return Response(content=pdf_buffer.getvalue(), media_type="application/pdf")

@router.get("/reuniones/{reunion_id}/export-pdf")
async def export_agenda_pdf(
    reunion_id: UUID,
    user: User = Depends(get_current_user)
):
    """Export the meeting agenda in PDF format."""
    service = get_management_service()
    pdf_service = get_pdf_service()
    
    # Fetch data
    reunion = service.db.client.table("reuniones").select("*").eq("id", str(reunion_id)).single().execute().data
    if not reunion:
        raise HTTPException(status_code=404, detail="Reunión no encontrada")
        
    agenda = service.get_agenda_detalle(reunion_id)
    
    pdf_buffer = pdf_service.create_agenda_pdf(reunion, agenda)
    
    return Response(
        content=pdf_buffer.getvalue(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=agenda_reunion_{reunion_id}.pdf"
        }
    )
