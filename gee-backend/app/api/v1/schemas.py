"""
Pydantic models for API request/response validation.
Replaces raw Dict[str, Any] parameters with typed schemas.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


# ===========================================
# Infrastructure Schemas
# ===========================================


class AssetCreate(BaseModel):
    """Schema for creating a new infrastructure asset."""

    nombre: str = Field(..., min_length=1, max_length=200)
    tipo: str = Field(
        ..., description="Tipo de activo: canal, alcantarilla, compuerta, etc."
    )
    cuenca: Optional[str] = None
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    estado_actual: str = Field(
        default="bueno", description="Estado: bueno, regular, malo, critico"
    )
    descripcion: Optional[str] = None
    material: Optional[str] = None
    dimensiones: Optional[str] = None


class AssetUpdate(BaseModel):
    """Schema for updating an infrastructure asset (partial)."""

    nombre: Optional[str] = None
    tipo: Optional[str] = None
    cuenca: Optional[str] = None
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    estado_actual: Optional[str] = None
    descripcion: Optional[str] = None
    material: Optional[str] = None
    dimensiones: Optional[str] = None


class MaintenanceLogCreate(BaseModel):
    """Schema for creating a maintenance log entry."""

    infraestructura_id: str = Field(
        ..., description="UUID del activo de infraestructura"
    )
    tipo_trabajo: str = Field(..., description="Tipo de trabajo realizado")
    descripcion: Optional[str] = None
    fecha: Optional[str] = Field(
        default=None, description="Fecha del mantenimiento (ISO 8601)"
    )
    nuevo_estado: Optional[str] = Field(
        default="bueno", description="Estado despues del mantenimiento"
    )
    costo: Optional[float] = None
    responsable: Optional[str] = None


# ===========================================
# Management Schemas
# ===========================================


class TramiteCreate(BaseModel):
    """Schema for creating an administrative procedure."""

    titulo: str = Field(..., min_length=1, max_length=300)
    descripcion: Optional[str] = None
    tipo: str = Field(..., description="Tipo de tramite")
    organismo: Optional[str] = Field(
        default=None, description="Organismo ante el que se tramita"
    )
    estado: str = Field(default="iniciado")
    prioridad: Optional[str] = Field(default="media")
    fecha_inicio: Optional[str] = None


class TramiteUpdate(BaseModel):
    """Schema for updating a procedure."""

    titulo: Optional[str] = None
    descripcion: Optional[str] = None
    estado: Optional[str] = None
    prioridad: Optional[str] = None
    organismo: Optional[str] = None


class TramiteAvanceCreate(BaseModel):
    """Schema for adding a progress update to a procedure."""

    tramite_id: str = Field(..., description="UUID del tramite")
    descripcion: str = Field(..., min_length=1)
    fecha: Optional[str] = None
    nuevo_estado: Optional[str] = Field(
        default=None, description="Nuevo estado del tramite si cambio"
    )
    documentos: Optional[List[str]] = None


class SeguimientoCreate(BaseModel):
    """Schema for creating a tracking/follow-up entry."""

    entidad_tipo: str = Field(..., description="Tipo de entidad: reporte o sugerencia")
    entidad_id: str = Field(..., description="UUID de la entidad")
    estado_nuevo: Optional[str] = None
    comentario: Optional[str] = None
    accion_tomada: Optional[str] = None
    fecha: Optional[str] = None


class ReunionCreate(BaseModel):
    """Schema for creating a meeting."""

    titulo: str = Field(..., min_length=1, max_length=300)
    fecha_reunion: str = Field(..., description="Fecha y hora de la reunion (ISO 8601)")
    lugar: Optional[str] = None
    descripcion: Optional[str] = None
    tipo: Optional[str] = Field(default="ordinaria")


class AgendaItemCreate(BaseModel):
    """Schema for adding an item to a meeting agenda."""

    item: "AgendaItemData"
    referencias: List["AgendaReferenciaData"] = Field(default_factory=list)


class AgendaItemData(BaseModel):
    """Agenda item data."""

    titulo: str = Field(..., min_length=1, max_length=300)
    descripcion: Optional[str] = None
    orden: Optional[int] = None
    tipo: Optional[str] = None


class AgendaReferenciaData(BaseModel):
    """Reference link for an agenda item."""

    tipo_referencia: Optional[str] = None
    referencia_id: Optional[str] = None
    descripcion: Optional[str] = None


# ===========================================
# Padron Schemas
# ===========================================


class ConsorcistaCreate(BaseModel):
    """Schema for creating a consortium member."""

    nombre: str = Field(..., min_length=1, max_length=100)
    apellido: str = Field(..., min_length=1, max_length=100)
    cuit: Optional[str] = Field(default=None, max_length=20)
    email: Optional[str] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    hectareas: Optional[float] = Field(default=None, ge=0)
    cuenca: Optional[str] = None
    estado: str = Field(default="activo")


class ConsorcistaUpdate(BaseModel):
    """Schema for updating a consortium member (partial)."""

    nombre: Optional[str] = None
    apellido: Optional[str] = None
    cuit: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    hectareas: Optional[float] = Field(default=None, ge=0)
    cuenca: Optional[str] = None
    estado: Optional[str] = None


class PagoCreate(BaseModel):
    """Schema for registering a payment."""

    consorcista_id: str = Field(..., description="UUID del consorcista")
    anio: int = Field(..., ge=2000, le=2100)
    monto: float = Field(..., gt=0)
    fecha_pago: Optional[str] = None
    metodo_pago: Optional[str] = None
    comprobante: Optional[str] = None
    estado: str = Field(default="pagado")


# ===========================================
# Finance Schemas
# ===========================================


class GastoCreate(BaseModel):
    """Schema for creating an expense."""

    descripcion: str = Field(..., min_length=1)
    monto: float = Field(..., gt=0)
    fecha: str = Field(..., description="Fecha del gasto (YYYY-MM-DD)")
    categoria: str = Field(..., description="Categoria del gasto")
    infraestructura_id: Optional[str] = Field(
        default=None, description="UUID del activo relacionado"
    )
    comprobante: Optional[str] = None
    proveedor: Optional[str] = None
    notas: Optional[str] = None


class PresupuestoCreate(BaseModel):
    """Schema for creating/updating a budget."""

    anio: int = Field(..., ge=2000, le=2100)
    monto_total: float = Field(..., gt=0)
    descripcion: Optional[str] = None
    estado: str = Field(default="borrador")


# Rebuild models to resolve forward references
AgendaItemCreate.model_rebuild()
