"""
API endpoints para sugerencias ciudadanas y temas de comision.
"""

from datetime import datetime, date, timedelta, timezone
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field, EmailStr

from app.services.supabase_service import get_supabase_client
from app.auth import User, require_authenticated, require_admin_or_operator
from app.core.logging import get_logger
from app.core.exceptions import (
    AppException,
    SuggestionNotFoundError,
    ValidationError,
    RateLimitExceededError,
)

router = APIRouter()
logger = get_logger(__name__)


# ===========================================
# SCHEMAS
# ===========================================


class SugerenciaBase(BaseModel):
    """Base schema para sugerencias."""

    titulo: str = Field(..., min_length=5, max_length=200)
    descripcion: str = Field(..., min_length=10)
    categoria: Optional[str] = None


class SugerenciaCiudadanaCreate(SugerenciaBase):
    """Schema para crear sugerencia ciudadana (publica)."""

    contacto_nombre: Optional[str] = None
    contacto_email: Optional[EmailStr] = None
    contacto_telefono: Optional[str] = None
    contacto_verificado: bool = False  # Debe ser True para aceptar


class SugerenciaInternaCreate(SugerenciaBase):
    """Schema para crear tema interno (comision)."""

    prioridad: Optional[str] = "normal"
    cuenca_id: Optional[str] = None  # Cuenca asociada (opcional)


class SugerenciaUpdate(BaseModel):
    """Schema para actualizar sugerencia."""

    titulo: Optional[str] = None
    descripcion: Optional[str] = None
    categoria: Optional[str] = None
    estado: Optional[str] = None
    prioridad: Optional[str] = None
    fecha_reunion: Optional[date] = None
    notas_comision: Optional[str] = None
    resolucion: Optional[str] = None
    cuenca_id: Optional[str] = None  # Cuenca asociada (opcional)


class AgendarRequest(BaseModel):
    """Schema para agendar sugerencia a una reunion."""

    fecha_reunion: date


class ResolverRequest(BaseModel):
    """Schema para resolver sugerencia."""

    resolucion: str = Field(..., min_length=5, max_length=2000)


class SugerenciaResponse(BaseModel):
    """Schema de respuesta para sugerencia."""

    id: UUID
    tipo: str
    titulo: str
    descripcion: str
    categoria: Optional[str]
    contacto_nombre: Optional[str]
    contacto_email: Optional[str]
    estado: str
    prioridad: str
    fecha_reunion: Optional[date]
    notas_comision: Optional[str]
    resolucion: Optional[str]
    cuenca_id: Optional[str]  # Cuenca asociada
    autor_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime


class SugerenciaListResponse(BaseModel):
    """Schema para lista paginada."""

    items: List[SugerenciaResponse]
    total: int
    page: int
    limit: int


class HistorialEntry(BaseModel):
    """Schema para entrada de historial."""

    id: UUID
    accion: str
    estado_anterior: Optional[str]
    estado_nuevo: Optional[str]
    notas: Optional[str]
    created_at: datetime
    usuario: Optional[dict] = None


# ===========================================
# ENDPOINTS PUBLICOS
# ===========================================


class RateLimitResponse(BaseModel):
    """Respuesta con info de rate limit."""

    remaining: int
    limit: int
    reset_hours: int = 24


@router.post("/public", response_model=dict, tags=["Public"])
async def crear_sugerencia_publica(data: SugerenciaCiudadanaCreate):
    """
    Crear sugerencia ciudadana (sin autenticacion).
    Requiere contacto verificado por email.
    Limite: 3 sugerencias por dia por contacto verificado.
    """
    # Validar que tenga algun contacto
    if not data.contacto_email and not data.contacto_telefono:
        raise ValidationError(
            message="Debe proporcionar email o telefono de contacto",
            code="CONTACT_REQUIRED",
        )

    # Validar que el contacto este verificado
    if not data.contacto_verificado:
        raise ValidationError(
            message="Debe verificar su email o telefono antes de enviar la sugerencia",
            code="CONTACT_NOT_VERIFIED",
        )

    supabase = get_supabase_client()

    # Determinar contacto principal (el verificado)
    contact_value = data.contacto_email or data.contacto_telefono
    contact_type = "email" if data.contacto_email else "phone"

    # Verificar rate limit (max 3 sugerencias por dia)
    MAX_SUGERENCIAS_POR_DIA = 3

    # Contar envios en las ultimas 24 horas
    yesterday = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    count_result = (
        supabase.table("contact_submissions")
        .select("id", count="exact")
        .eq("contact_value", contact_value.lower())
        .eq("submission_type", "sugerencia")
        .gte("created_at", yesterday)
        .execute()
    )

    submissions_today = count_result.count or 0

    if submissions_today >= MAX_SUGERENCIAS_POR_DIA:
        logger.warning(
            "Rate limit exceeded for suggestions",
            contact=contact_value[:3] + "***",  # Partially masked
            submissions_today=submissions_today,
        )
        raise RateLimitExceededError(
            message=f"Has alcanzado el limite de {MAX_SUGERENCIAS_POR_DIA} sugerencias por dia. Intenta nuevamente manana.",
            retry_after=86400,
            limit=MAX_SUGERENCIAS_POR_DIA,
        )

    # Crear sugerencia
    sugerencia_data = {
        "tipo": "ciudadana",
        "titulo": data.titulo,
        "descripcion": data.descripcion,
        "categoria": data.categoria,
        "contacto_nombre": data.contacto_nombre,
        "contacto_email": data.contacto_email,
        "contacto_telefono": data.contacto_telefono,
        "contacto_verificado": True,
        "estado": "pendiente",
        "prioridad": "normal",
    }

    result = supabase.table("sugerencias").insert(sugerencia_data).execute()

    if not result.data:
        logger.error("Failed to create suggestion")
        raise AppException(
            message="Error al crear sugerencia",
            code="SUGGESTION_CREATE_ERROR",
            status_code=500,
        )

    sugerencia = result.data[0]

    # Registrar envio para rate limiting
    supabase.table("contact_submissions").insert(
        {
            "contact_type": contact_type,
            "contact_value": contact_value.lower(),
            "submission_type": "sugerencia",
            "submission_id": sugerencia["id"],
        }
    ).execute()

    # Registrar en historial
    supabase.table("sugerencias_historial").insert(
        {
            "sugerencia_id": sugerencia["id"],
            "accion": "creado",
            "estado_nuevo": "pendiente",
            "notas": f"Sugerencia ciudadana recibida (contacto verificado: {contact_type})",
        }
    ).execute()

    remaining = MAX_SUGERENCIAS_POR_DIA - submissions_today - 1

    logger.info(
        "Public suggestion created",
        suggestion_id=sugerencia["id"],
        contact_type=contact_type,
    )

    return {
        "id": sugerencia["id"],
        "message": "Sugerencia enviada correctamente. Gracias por tu participacion.",
        "remaining_today": remaining,
    }


@router.get("/public/limit", response_model=RateLimitResponse, tags=["Public"])
async def verificar_limite_sugerencias(
    email: Optional[str] = Query(None),
    telefono: Optional[str] = Query(None),
):
    """
    Verificar cuantas sugerencias puede enviar un contacto hoy.
    """
    if not email and not telefono:
        raise ValidationError(
            message="Debe proporcionar email o telefono",
            code="CONTACT_REQUIRED",
        )

    contact_value = email or telefono
    MAX_SUGERENCIAS_POR_DIA = 3

    supabase = get_supabase_client()

    yesterday = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    count_result = (
        supabase.table("contact_submissions")
        .select("id", count="exact")
        .eq("contact_value", contact_value.lower())
        .eq("submission_type", "sugerencia")
        .gte("created_at", yesterday)
        .execute()
    )

    submissions_today = count_result.count or 0
    remaining = max(0, MAX_SUGERENCIAS_POR_DIA - submissions_today)

    return {
        "remaining": remaining,
        "limit": MAX_SUGERENCIAS_POR_DIA,
        "reset_hours": 24,
    }


# ===========================================
# ENDPOINTS AUTENTICADOS (COMISION)
# ===========================================


@router.get("", response_model=SugerenciaListResponse)
async def listar_sugerencias(
    user: User = Depends(require_authenticated),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    tipo: Optional[str] = Query(None, description="ciudadana o interna"),
    estado: Optional[str] = Query(None),
    prioridad: Optional[str] = Query(None),
    fecha_reunion: Optional[date] = Query(None),
    cuenca_id: Optional[str] = Query(None, description="Filtrar por cuenca"),
):
    """
    Listar sugerencias con filtros.
    Solo accesible para usuarios autenticados (comision).
    """
    logger.info(
        "Listing suggestions",
        user_id=user.id,
        user_role=user.role,
        filters={"tipo": tipo, "estado": estado, "prioridad": prioridad},
    )

    supabase = get_supabase_client()

    # Construir query
    query = supabase.table("sugerencias").select("*", count="exact")

    if tipo:
        query = query.eq("tipo", tipo)
    if estado:
        query = query.eq("estado", estado)
    if prioridad:
        query = query.eq("prioridad", prioridad)
    if fecha_reunion:
        query = query.eq("fecha_reunion", fecha_reunion.isoformat())
    if cuenca_id:
        query = query.eq("cuenca_id", cuenca_id)

    # Ordenar por prioridad y fecha
    query = query.order("prioridad", desc=True).order("created_at", desc=True)

    # Paginacion
    offset = (page - 1) * limit
    query = query.range(offset, offset + limit - 1)

    result = query.execute()

    return {
        "items": result.data,
        "total": result.count or 0,
        "page": page,
        "limit": limit,
    }


@router.get("/stats", response_model=dict)
async def obtener_estadisticas(
    user: User = Depends(require_authenticated),
):
    """Obtener estadisticas de sugerencias."""
    logger.info("Getting suggestion stats", user_id=user.id)

    supabase = get_supabase_client()

    # Use individual count queries instead of fetching all records
    stats = {}

    # Count by estado
    for estado in ["pendiente", "en_agenda", "tratado", "descartado"]:
        result = (
            supabase.table("sugerencias")
            .select("id", count="exact")
            .eq("estado", estado)
            .limit(1)
            .execute()
        )
        stats[estado] = result.count or 0

    # Count by tipo
    for tipo_key, tipo_value in [("ciudadanas", "ciudadana"), ("internas", "interna")]:
        result = (
            supabase.table("sugerencias")
            .select("id", count="exact")
            .eq("tipo", tipo_value)
            .limit(1)
            .execute()
        )
        stats[tipo_key] = result.count or 0

    stats["total"] = (
        stats["pendiente"] + stats["en_agenda"] + stats["tratado"] + stats["descartado"]
    )

    return stats


@router.get("/proxima-reunion", response_model=List[SugerenciaResponse])
async def temas_proxima_reunion(
    user: User = Depends(require_authenticated),
):
    """Obtener temas agendados para la proxima reunion."""
    logger.info("Getting next meeting topics", user_id=user.id)

    supabase = get_supabase_client()

    # Buscar temas en_agenda ordenados por prioridad
    result = (
        supabase.table("sugerencias")
        .select("*")
        .eq("estado", "en_agenda")
        .order("prioridad", desc=True)
        .order("created_at")
        .execute()
    )

    return result.data


@router.post("/interna", response_model=SugerenciaResponse)
async def crear_tema_interno(
    data: SugerenciaInternaCreate,
    user: User = Depends(require_admin_or_operator),
):
    """
    Crear tema interno (propuesto por miembro de comision).
    Requiere rol: admin u operador.
    """
    logger.info(
        "Creating internal topic",
        user_id=user.id,
        user_role=user.role,
        titulo=data.titulo,
    )

    supabase = get_supabase_client()

    sugerencia_data = {
        "tipo": "interna",
        "titulo": data.titulo,
        "descripcion": data.descripcion,
        "categoria": data.categoria,
        "prioridad": data.prioridad or "normal",
        "estado": "pendiente",
        "autor_id": user.id,
        "cuenca_id": data.cuenca_id,
    }

    result = supabase.table("sugerencias").insert(sugerencia_data).execute()

    if not result.data:
        logger.error("Failed to create internal topic", user_id=user.id)
        raise AppException(
            message="Error al crear tema",
            code="TOPIC_CREATE_ERROR",
            status_code=500,
        )

    sugerencia = result.data[0]

    # Registrar en historial
    supabase.table("sugerencias_historial").insert(
        {
            "sugerencia_id": sugerencia["id"],
            "usuario_id": user.id,
            "accion": "creado",
            "estado_nuevo": "pendiente",
            "notas": "Tema interno propuesto",
        }
    ).execute()

    logger.info(
        "Internal topic created",
        suggestion_id=sugerencia["id"],
        user_id=user.id,
    )

    return sugerencia


@router.get("/{sugerencia_id}", response_model=SugerenciaResponse)
async def obtener_sugerencia(
    sugerencia_id: UUID,
    user: User = Depends(require_authenticated),
):
    """Obtener detalle de una sugerencia."""
    logger.info(
        "Getting suggestion detail",
        suggestion_id=str(sugerencia_id),
        user_id=user.id,
    )

    supabase = get_supabase_client()

    result = (
        supabase.table("sugerencias")
        .select("*")
        .eq("id", str(sugerencia_id))
        .single()
        .execute()
    )

    if not result.data:
        raise SuggestionNotFoundError(str(sugerencia_id))

    return result.data


@router.get("/{sugerencia_id}/historial", response_model=List[HistorialEntry])
async def obtener_historial(
    sugerencia_id: UUID,
    user: User = Depends(require_authenticated),
):
    """Obtener historial de cambios de una sugerencia."""
    logger.info(
        "Getting suggestion history",
        suggestion_id=str(sugerencia_id),
        user_id=user.id,
    )

    supabase = get_supabase_client()

    result = (
        supabase.table("sugerencias_historial")
        .select("*, perfiles(nombre)")
        .eq("sugerencia_id", str(sugerencia_id))
        .order("created_at", desc=True)
        .execute()
    )

    return result.data


@router.put("/{sugerencia_id}", response_model=SugerenciaResponse)
async def actualizar_sugerencia(
    sugerencia_id: UUID,
    data: SugerenciaUpdate,
    user: User = Depends(require_admin_or_operator),
):
    """
    Actualizar sugerencia (cambiar estado, prioridad, agendar, etc.).
    Requiere rol: admin u operador.
    """
    logger.info(
        "Updating suggestion",
        suggestion_id=str(sugerencia_id),
        user_id=user.id,
        user_role=user.role,
    )

    supabase = get_supabase_client()

    # Obtener estado actual
    current = (
        supabase.table("sugerencias")
        .select("estado, prioridad")
        .eq("id", str(sugerencia_id))
        .single()
        .execute()
    )

    if not current.data:
        raise SuggestionNotFoundError(str(sugerencia_id))

    # Preparar datos de actualizacion (Pydantic v2: model_dump)
    update_data = {k: v for k, v in data.model_dump(exclude_none=True).items()}

    if not update_data:
        raise ValidationError(
            message="No hay datos para actualizar",
            code="NO_UPDATE_DATA",
        )

    # Convertir fecha a string si existe
    if "fecha_reunion" in update_data and update_data["fecha_reunion"]:
        update_data["fecha_reunion"] = update_data["fecha_reunion"].isoformat()

    # Actualizar
    result = (
        supabase.table("sugerencias")
        .update(update_data)
        .eq("id", str(sugerencia_id))
        .execute()
    )

    if not result.data:
        logger.error(
            "Failed to update suggestion",
            suggestion_id=str(sugerencia_id),
        )
        raise AppException(
            message="Error al actualizar",
            code="SUGGESTION_UPDATE_ERROR",
            status_code=500,
        )

    # Registrar cambio de estado en historial
    if data.estado and data.estado != current.data["estado"]:
        accion = "estado_cambiado"
        if data.estado == "en_agenda":
            accion = "agendado"
        elif data.estado == "tratado":
            accion = "resuelto"

        supabase.table("sugerencias_historial").insert(
            {
                "sugerencia_id": str(sugerencia_id),
                "usuario_id": user.id,
                "accion": accion,
                "estado_anterior": current.data["estado"],
                "estado_nuevo": data.estado,
                "notas": data.resolucion if data.estado == "tratado" else None,
            }
        ).execute()

        logger.info(
            "Suggestion status changed",
            suggestion_id=str(sugerencia_id),
            old_status=current.data["estado"],
            new_status=data.estado,
            user_id=user.id,
        )

    return result.data[0]


@router.post("/{sugerencia_id}/agendar", response_model=SugerenciaResponse)
async def agendar_sugerencia(
    sugerencia_id: UUID,
    data: AgendarRequest,
    user: User = Depends(require_admin_or_operator),
):
    """
    Agendar sugerencia para una reunion especifica.
    Requiere rol: admin u operador.
    """
    logger.info(
        "Scheduling suggestion",
        suggestion_id=str(sugerencia_id),
        fecha_reunion=str(data.fecha_reunion),
        user_id=user.id,
    )

    supabase = get_supabase_client()

    result = (
        supabase.table("sugerencias")
        .update(
            {
                "estado": "en_agenda",
                "fecha_reunion": data.fecha_reunion.isoformat(),
            }
        )
        .eq("id", str(sugerencia_id))
        .execute()
    )

    if not result.data:
        raise SuggestionNotFoundError(str(sugerencia_id))

    # Registrar en historial
    supabase.table("sugerencias_historial").insert(
        {
            "sugerencia_id": str(sugerencia_id),
            "usuario_id": user.id,
            "accion": "agendado",
            "estado_nuevo": "en_agenda",
            "notas": f"Agendado para reunion del {data.fecha_reunion}",
        }
    ).execute()

    logger.info(
        "Suggestion scheduled",
        suggestion_id=str(sugerencia_id),
        fecha_reunion=str(data.fecha_reunion),
        user_id=user.id,
    )

    return result.data[0]


@router.post("/{sugerencia_id}/resolver", response_model=SugerenciaResponse)
async def resolver_sugerencia(
    sugerencia_id: UUID,
    data: ResolverRequest,
    user: User = Depends(require_admin_or_operator),
):
    """
    Marcar sugerencia como tratada con su resolucion.
    Requiere rol: admin u operador.
    """
    logger.info(
        "Resolving suggestion",
        suggestion_id=str(sugerencia_id),
        user_id=user.id,
    )

    supabase = get_supabase_client()

    result = (
        supabase.table("sugerencias")
        .update(
            {
                "estado": "tratado",
                "resolucion": data.resolucion,
            }
        )
        .eq("id", str(sugerencia_id))
        .execute()
    )

    if not result.data:
        raise SuggestionNotFoundError(str(sugerencia_id))

    # Registrar en historial
    supabase.table("sugerencias_historial").insert(
        {
            "sugerencia_id": str(sugerencia_id),
            "usuario_id": user.id,
            "accion": "resuelto",
            "estado_nuevo": "tratado",
            "notas": data.resolucion,
        }
    ).execute()

    logger.info(
        "Suggestion resolved",
        suggestion_id=str(sugerencia_id),
        user_id=user.id,
    )

    return result.data[0]


@router.delete("/{sugerencia_id}", status_code=204)
async def eliminar_sugerencia(
    sugerencia_id: UUID,
    user: User = Depends(require_admin_or_operator),
):
    """
    Eliminar sugerencia.
    Requiere rol: admin u operador.
    """
    logger.info(
        "Deleting suggestion",
        suggestion_id=str(sugerencia_id),
        user_id=user.id,
        user_role=user.role,
    )

    supabase = get_supabase_client()

    result = (
        supabase.table("sugerencias").delete().eq("id", str(sugerencia_id)).execute()
    )

    if not result.data:
        raise SuggestionNotFoundError(str(sugerencia_id))

    logger.info(
        "Suggestion deleted",
        suggestion_id=str(sugerencia_id),
        user_id=user.id,
    )

    return Response(status_code=204)
