"""
Stats Endpoints.
Estadisticas y dashboard.
"""

import csv
import io
import json as json_module
from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from fastapi import APIRouter, Query, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.constants import (
    CUENCA_AREAS_HA,
    CONSORCIO_AREA_HA,
    CONSORCIO_KM_CAMINOS,
    CUENCA_IDS,
)
from app.services.supabase_service import get_supabase_service
from app.auth import User, require_authenticated

router = APIRouter()


# ===========================================
# SCHEMAS
# ===========================================


class ExportFormat(str, Enum):
    CSV = "csv"
    XLSX = "xlsx"
    PDF = "pdf"


class ExportRequest(BaseModel):
    """Request para exportar datos."""

    format: ExportFormat = ExportFormat.CSV
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    cuencas: Optional[List[str]] = None
    include_reports: bool = False


# ===========================================
# ENDPOINTS
# ===========================================


@router.get("/dashboard")
async def get_dashboard_stats(
    user: User = Depends(require_authenticated),
):
    """
    Obtener estadisticas para el dashboard principal.

    Incluye:
    - Datos del ultimo analisis
    - Conteos de denuncias por estado
    - Area total del consorcio
    """
    db = get_supabase_service()
    return db.get_dashboard_stats()


@router.get("/by-cuenca")
async def get_stats_by_cuenca(analysis_id: Optional[str] = None):
    """
    Obtener estadisticas desglosadas por cuenca.

    - **analysis_id**: ID del analisis a consultar (opcional, ultimo por defecto)
    """
    db = get_supabase_service()

    if analysis_id:
        analysis = db.get_analysis(analysis_id)
    else:
        analysis = db.get_latest_analysis()

    if not analysis:
        return {
            "message": "No hay analisis disponibles",
            "cuencas": [],
        }

    # Parsear stats_cuencas si es string
    stats_cuencas = analysis.get("stats_cuencas", {})
    if isinstance(stats_cuencas, str):
        stats_cuencas = json_module.loads(stats_cuencas)

    # Areas por cuenca (from centralized constants)
    areas_cuencas = CUENCA_AREAS_HA

    cuencas = []
    for nombre, stats in stats_cuencas.items():
        cuencas.append(
            {
                "nombre": nombre,
                "hectareas_inundadas": stats.get("hectareas", 0),
                "porcentaje": stats.get("porcentaje", 0),
                "area_total": areas_cuencas.get(nombre, 0),
            }
        )

    return {
        "analysis_id": analysis.get("id"),
        "fecha_analisis": analysis.get("created_at"),
        "periodo": {
            "inicio": analysis.get("fecha_inicio"),
            "fin": analysis.get("fecha_fin"),
        },
        "cuencas": cuencas,
        "total": {
            "hectareas_inundadas": analysis.get("hectareas_inundadas", 0),
            "porcentaje": analysis.get("porcentaje_area", 0),
            "caminos_afectados": analysis.get("caminos_afectados", 0),
        },
    }


@router.get("/historical")
async def get_historical_stats(
    cuenca: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = Query(default=20, ge=1, le=100),
):
    """
    Obtener historial de estadisticas.

    Util para graficos de evolucion temporal.

    - **cuenca**: Filtrar por cuenca
    - **date_from**: Fecha desde
    - **date_to**: Fecha hasta
    - **limit**: Maximo de resultados
    """
    db = get_supabase_service()

    # Obtener historial de analisis
    history = db.get_analysis_history(page=1, limit=limit, status="completed")

    items = []
    for analysis in history.get("items", []):
        stats_cuencas = analysis.get("stats_cuencas", {})
        if isinstance(stats_cuencas, str):
            stats_cuencas = json_module.loads(stats_cuencas)

        item = {
            "id": analysis.get("id"),
            "fecha": analysis.get("created_at"),
            "periodo_inicio": analysis.get("fecha_inicio"),
            "periodo_fin": analysis.get("fecha_fin"),
            "hectareas_total": analysis.get("hectareas_inundadas", 0),
            "porcentaje_total": analysis.get("porcentaje_area", 0),
            "caminos_afectados": analysis.get("caminos_afectados", 0),
        }

        if cuenca and cuenca in stats_cuencas:
            item["hectareas_cuenca"] = stats_cuencas[cuenca].get("hectareas", 0)
            item["porcentaje_cuenca"] = stats_cuencas[cuenca].get("porcentaje", 0)

        items.append(item)

    return {
        "items": items,
        "total": history.get("total", 0),
        "cuenca_filter": cuenca,
    }


@router.post("/export")
async def export_stats(
    request: ExportRequest,
    user: User = Depends(require_authenticated),
):
    """
    Exportar estadisticas a archivo.

    Genera un archivo CSV con los datos de analisis.
    Los formatos XLSX y PDF requieren dependencias adicionales.

    - **format**: csv (soportado), xlsx/pdf (retorna JSON por ahora)
    - **date_from**: Filtrar desde fecha
    - **date_to**: Filtrar hasta fecha
    - **cuencas**: Filtrar por cuencas especificas
    - **include_reports**: Incluir datos de denuncias
    """
    db = get_supabase_service()

    # Get analysis history
    history = db.get_analysis_history(page=1, limit=500, status="completed")
    items = history.get("items", [])

    # Apply date filters
    if request.date_from or request.date_to:
        filtered_items = []
        for item in items:
            created_at = item.get("created_at", "")
            if created_at:
                try:
                    item_date = datetime.fromisoformat(
                        created_at.replace("Z", "+00:00")
                    ).date()
                    if request.date_from and item_date < request.date_from:
                        continue
                    if request.date_to and item_date > request.date_to:
                        continue
                    filtered_items.append(item)
                except (ValueError, TypeError):
                    filtered_items.append(item)
            else:
                filtered_items.append(item)
        items = filtered_items

    # Generate CSV
    if request.format == ExportFormat.CSV:
        return _generate_csv_response(items, request.cuencas, request.include_reports)

    # For XLSX and PDF, return JSON with message (would need openpyxl/reportlab)
    return {
        "message": f"Format {request.format.value} requires additional dependencies. Use CSV for now.",
        "records": len(items),
        "format": request.format.value,
        "data": _prepare_export_data(items, request.cuencas),
    }


@router.get("/summary")
async def get_summary(
    user: User = Depends(require_authenticated),
):
    """
    Obtener resumen general del sistema.

    Vista rapida del estado actual.
    """
    db = get_supabase_service()

    dashboard = db.get_dashboard_stats()
    reports_stats = dashboard.get("denuncias", {})
    ultimo = dashboard.get("ultimo_analisis", {})

    return {
        "area_consorcio_ha": CONSORCIO_AREA_HA,
        "cuencas": CUENCA_IDS,
        "km_caminos": CONSORCIO_KM_CAMINOS,
        "ultimo_analisis": {
            "fecha": ultimo.get("fecha"),
            "hectareas_inundadas": ultimo.get("hectareas_inundadas", 0),
            "porcentaje": ultimo.get("porcentaje_area", 0),
            "caminos_afectados": ultimo.get("caminos_afectados", 0),
        },
        "denuncias": {
            "pendientes": reports_stats.get("pendiente", 0),
            "en_revision": reports_stats.get("en_revision", 0),
            "resueltas_total": reports_stats.get("resuelto", 0),
        },
    }


def _prepare_export_data(
    items: List[dict], cuencas_filter: Optional[List[str]] = None
) -> List[dict]:
    """Prepare data for export."""
    export_data = []

    for item in items:
        stats_cuencas = item.get("stats_cuencas", {})
        if isinstance(stats_cuencas, str):
            try:
                stats_cuencas = json_module.loads(stats_cuencas)
            except (json_module.JSONDecodeError, TypeError):
                stats_cuencas = {}

        row = {
            "id": item.get("id", ""),
            "fecha_analisis": item.get("created_at", ""),
            "fecha_inicio": item.get("fecha_inicio", ""),
            "fecha_fin": item.get("fecha_fin", ""),
            "hectareas_inundadas": item.get("hectareas_inundadas", 0),
            "porcentaje_area": item.get("porcentaje_area", 0),
            "caminos_afectados_km": item.get("caminos_afectados", 0),
            "estado": item.get("status", ""),
        }

        # Add cuenca-specific data
        for cuenca_name in ["candil", "ml", "noroeste", "norte"]:
            if cuencas_filter and cuenca_name not in cuencas_filter:
                continue
            cuenca_stats = stats_cuencas.get(cuenca_name, {})
            row[f"{cuenca_name}_hectareas"] = cuenca_stats.get("hectareas", 0)
            row[f"{cuenca_name}_porcentaje"] = cuenca_stats.get("porcentaje", 0)

        export_data.append(row)

    return export_data


def _generate_csv_response(
    items: List[dict],
    cuencas_filter: Optional[List[str]] = None,
    include_reports: bool = False,
) -> StreamingResponse:
    """Generate CSV file response."""
    export_data = _prepare_export_data(items, cuencas_filter)

    if not export_data:
        # Return empty CSV with headers
        export_data = [
            {
                "id": "",
                "fecha_analisis": "",
                "fecha_inicio": "",
                "fecha_fin": "",
                "hectareas_inundadas": "",
                "porcentaje_area": "",
                "caminos_afectados_km": "",
                "estado": "",
            }
        ]

    # Create CSV in memory
    output = io.StringIO()
    if export_data:
        fieldnames = list(export_data[0].keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(export_data)

    # Reset stream position
    output.seek(0)

    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"estadisticas_consorcio_{timestamp}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": "text/csv; charset=utf-8",
        },
    )
