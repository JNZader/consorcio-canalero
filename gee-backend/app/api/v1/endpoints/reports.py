"""
Reports Endpoints.
Gestion de denuncias ciudadanas (admin).
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

from app.services.supabase_service import get_supabase_service
from app.auth import User, require_admin_or_operator, require_authenticated
from app.core.logging import get_logger
from app.core.exceptions import ReportNotFoundError

router = APIRouter()
logger = get_logger(__name__)


# ===========================================
# SCHEMAS
# ===========================================


class ReportStatus(str, Enum):
    PENDIENTE = "pendiente"
    EN_REVISION = "en_revision"
    RESUELTO = "resuelto"
    RECHAZADO = "rechazado"


class ReportPriority(str, Enum):
    BAJA = "baja"
    NORMAL = "normal"
    ALTA = "alta"
    URGENTE = "urgente"


class ReportUpdate(BaseModel):
    """Datos para actualizar una denuncia."""

    estado: Optional[ReportStatus] = None
    asignado_a: Optional[str] = Field(default=None, description="ID del operador asignado")
    notas_internas: Optional[str] = None
    prioridad: Optional[ReportPriority] = None
    resolucion_descripcion: Optional[str] = None


class ReportAssign(BaseModel):
    """Asignar denuncia a operador."""

    operador_id: str
    notas: Optional[str] = None


# ===========================================
# ENDPOINTS
# ===========================================


@router.get("")
async def get_reports(
    user: User = Depends(require_authenticated),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    status: Optional[ReportStatus] = None,
    cuenca: Optional[str] = None,
    tipo: Optional[str] = None,
    assigned_to: Optional[str] = None,
):
    """
    Obtener lista de denuncias con filtros.
    Requiere autenticacion.

    - **page**: Numero de pagina
    - **limit**: Items por pagina (max 100)
    - **status**: Filtrar por estado
    - **cuenca**: Filtrar por cuenca
    - **tipo**: Filtrar por tipo de denuncia
    - **assigned_to**: Filtrar por operador asignado
    """
    logger.info(
        "Listing reports",
        user_id=user.id,
        user_role=user.role,
        filters={
            "status": status.value if status else None,
            "cuenca": cuenca,
            "tipo": tipo,
            "assigned_to": assigned_to,
        },
    )

    db = get_supabase_service()

    return db.get_reports(
        page=page,
        limit=limit,
        status=status.value if status else None,
        cuenca=cuenca,
        tipo=tipo,
        assigned_to=assigned_to,
    )


@router.get("/stats")
async def get_reports_stats(
    user: User = Depends(require_authenticated),
):
    """
    Obtener estadisticas de denuncias.
    Requiere autenticacion.

    Conteos por estado y totales.
    """
    logger.info("Getting reports stats", user_id=user.id)

    db = get_supabase_service()
    return db.get_reports_stats()


@router.get("/{report_id}")
async def get_report(
    report_id: str,
    user: User = Depends(require_authenticated),
):
    """
    Obtener detalle de una denuncia.
    Requiere autenticacion.

    Incluye historial de cambios.
    """
    logger.info(
        "Getting report detail",
        report_id=report_id,
        user_id=user.id,
    )

    db = get_supabase_service()
    report = db.get_report(report_id)

    if not report:
        raise ReportNotFoundError(report_id)

    return report


@router.put("/{report_id}")
async def update_report(
    report_id: str,
    updates: ReportUpdate,
    user: User = Depends(require_admin_or_operator),
):
    """
    Actualizar una denuncia.

    Registra el cambio en el historial.
    Requiere rol: admin u operador.
    """
    logger.info(
        "Updating report",
        report_id=report_id,
        user_id=user.id,
        user_role=user.role,
    )

    db = get_supabase_service()

    # Verificar que existe
    existing = db.get_report(report_id)
    if not existing:
        raise ReportNotFoundError(report_id)

    data = updates.model_dump(exclude_unset=True)
    if "estado" in data:
        data["estado"] = data["estado"].value if isinstance(data["estado"], ReportStatus) else data["estado"]
    if "prioridad" in data:
        data["prioridad"] = data["prioridad"].value if isinstance(data["prioridad"], ReportPriority) else data["prioridad"]

    result = db.update_report(report_id, data, user.id)

    logger.info(
        "Report updated",
        report_id=report_id,
        user_id=user.id,
        updates=list(data.keys()),
    )

    return result


@router.post("/{report_id}/assign")
async def assign_report(
    report_id: str,
    assignment: ReportAssign,
    user: User = Depends(require_admin_or_operator),
):
    """
    Asignar denuncia a un operador.
    Requiere rol: admin u operador.
    """
    logger.info(
        "Assigning report",
        report_id=report_id,
        operador_id=assignment.operador_id,
        user_id=user.id,
    )

    db = get_supabase_service()

    # Verificar que existe
    existing = db.get_report(report_id)
    if not existing:
        raise ReportNotFoundError(report_id)

    updates = {
        "asignado_a": assignment.operador_id,
        "estado": "en_revision",
    }

    if assignment.notas:
        updates["notas_internas"] = assignment.notas

    result = db.update_report(report_id, updates, user.id)

    logger.info(
        "Report assigned",
        report_id=report_id,
        operador_id=assignment.operador_id,
        user_id=user.id,
    )

    return result


@router.post("/{report_id}/resolve")
async def resolve_report(
    report_id: str,
    descripcion: str,
    user: User = Depends(require_admin_or_operator),
):
    """
    Marcar denuncia como resuelta.
    Requiere rol: admin u operador.
    """
    logger.info(
        "Resolving report",
        report_id=report_id,
        user_id=user.id,
    )

    db = get_supabase_service()

    # Verificar que existe
    existing = db.get_report(report_id)
    if not existing:
        raise ReportNotFoundError(report_id)

    updates = {
        "estado": "resuelto",
        "resolucion_descripcion": descripcion,
    }

    result = db.update_report(report_id, updates, user.id)

    logger.info(
        "Report resolved",
        report_id=report_id,
        user_id=user.id,
    )

    return result
