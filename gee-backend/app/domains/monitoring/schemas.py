"""Pydantic v2 schemas for the monitoring domain."""

import uuid
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ──────────────────────────────────────────────
# SUGERENCIA
# ──────────────────────────────────────────────


class SugerenciaCreate(BaseModel):
    """Public payload to create a sugerencia (no auth required)."""

    titulo: str = Field(..., min_length=5, max_length=200)
    descripcion: str = Field(..., min_length=10)
    categoria: Optional[str] = None
    contacto_email: Optional[EmailStr] = None
    contacto_nombre: Optional[str] = Field(default=None, max_length=200)
    geometry: Optional[dict[str, Any]] = None

    @field_validator("geometry")
    @classmethod
    def validate_geometry(cls, value: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if value is None:
            return value
        if value.get("type") != "FeatureCollection":
            raise ValueError("geometry debe ser un FeatureCollection")
        features = value.get("features")
        if not isinstance(features, list) or len(features) == 0:
            raise ValueError("geometry debe incluir al menos una linea")
        for feature in features:
            geometry = feature.get("geometry", {}) if isinstance(feature, dict) else {}
            if geometry.get("type") != "LineString":
                raise ValueError("solo se admiten geometrias LineString")
            coordinates = geometry.get("coordinates")
            if not isinstance(coordinates, list) or len(coordinates) < 2:
                raise ValueError("cada linea debe tener al menos dos vertices")
        return value


class SugerenciaUpdate(BaseModel):
    """Operator payload to update a sugerencia."""

    estado: Optional[str] = None
    respuesta: Optional[str] = None
    categoria: Optional[str] = None
    geometry: Optional[dict[str, Any]] = None


class SugerenciaResponse(BaseModel):
    """Full sugerencia response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    titulo: str
    descripcion: str
    categoria: Optional[str] = None
    estado: str
    contacto_email: Optional[str] = None
    contacto_nombre: Optional[str] = None
    geometry: Optional[dict[str, Any]] = None
    respuesta: Optional[str] = None
    usuario_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime


class SugerenciaListResponse(BaseModel):
    """Lightweight sugerencia for list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    titulo: str
    descripcion: str
    categoria: Optional[str] = None
    estado: str
    contacto_email: Optional[str] = None
    contacto_nombre: Optional[str] = None
    geometry: Optional[dict[str, Any]] = None
    created_at: datetime


# ──────────────────────────────────────────────
# ANALISIS GEE
# ──────────────────────────────────────────────


class AnalisisGeeResponse(BaseModel):
    """Full GEE analysis response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: str
    fecha_inicio: date
    fecha_fin: date
    resultados: dict[str, Any]
    hectareas_afectadas: Optional[float] = None
    porcentaje_area: Optional[float] = None
    parametros: dict[str, Any]
    usuario_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ──────────────────────────────────────────────
# DASHBOARD
# ──────────────────────────────────────────────


class DenunciaStats(BaseModel):
    """Denuncia counts by estado."""

    pendiente: int = 0
    en_revision: int = 0
    resuelto: int = 0
    descartado: int = 0
    total: int = 0


class DashboardStatsResponse(BaseModel):
    """Aggregated dashboard statistics."""

    denuncias: DenunciaStats
    total_assets: int = 0
    total_sugerencias: int = 0
    total_tramites: int = 0
    latest_analyses: list[AnalisisGeeResponse] = []
    resumen_financiero: dict[str, Any] = {}
