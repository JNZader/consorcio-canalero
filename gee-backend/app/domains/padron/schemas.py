"""Pydantic v2 schemas for the padron domain."""

import re
import uuid
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


_CUIT_FORMATTED = re.compile(r"^\d{2}-\d{8}-\d{1}$")
_CUIT_DIGITS_ONLY = re.compile(r"^\d{11}$")
_NON_DIGITS = re.compile(r"\D")


def _normalize_cuit(value: str) -> str:
    """
    Accept CUIT in formats: XX-XXXXXXXX-X or XXXXXXXXXXX (11 digits).
    Always returns the formatted version: XX-XXXXXXXX-X.
    """
    stripped = value.strip()

    # Already formatted
    if _CUIT_FORMATTED.match(stripped):
        return stripped

    # Try digits-only
    digits = _NON_DIGITS.sub("", stripped)
    if len(digits) == 11:
        return f"{digits[:2]}-{digits[2:10]}-{digits[10:]}"

    raise ValueError(
        "CUIT debe tener 11 digitos con formato XX-XXXXXXXX-X o XXXXXXXXXXX"
    )


# ──────────────────────────────────────────────
# CREATE
# ──────────────────────────────────────────────


class ConsorcistaCreate(BaseModel):
    """Payload to create a consorcista."""

    nombre: str = Field(..., min_length=1, max_length=200)
    apellido: str = Field(..., min_length=1, max_length=200)
    cuit: str = Field(..., description="CUIT/CUIL: XX-XXXXXXXX-X or 11 digits")
    dni: Optional[str] = Field(default=None, max_length=20)
    domicilio: Optional[str] = Field(default=None, max_length=500)
    localidad: Optional[str] = Field(default=None, max_length=200)
    telefono: Optional[str] = Field(default=None, max_length=50)
    email: Optional[str] = Field(default=None, max_length=255)
    parcela: Optional[str] = Field(default=None, max_length=100)
    hectareas: Optional[float] = Field(default=None, ge=0)
    categoria: Optional[str] = Field(
        default=None,
        description="propietario, arrendatario, otro",
    )
    estado: str = Field(
        default="activo",
        description="activo, inactivo, suspendido",
    )
    fecha_ingreso: Optional[date] = None
    notas: Optional[str] = None

    @field_validator("cuit")
    @classmethod
    def validate_cuit(cls, v: str) -> str:
        return _normalize_cuit(v)


# ──────────────────────────────────────────────
# UPDATE
# ──────────────────────────────────────────────


class ConsorcistaUpdate(BaseModel):
    """Partial update payload for a consorcista."""

    nombre: Optional[str] = Field(default=None, min_length=1, max_length=200)
    apellido: Optional[str] = Field(default=None, min_length=1, max_length=200)
    cuit: Optional[str] = Field(default=None)
    dni: Optional[str] = Field(default=None, max_length=20)
    domicilio: Optional[str] = Field(default=None, max_length=500)
    localidad: Optional[str] = Field(default=None, max_length=200)
    telefono: Optional[str] = Field(default=None, max_length=50)
    email: Optional[str] = Field(default=None, max_length=255)
    parcela: Optional[str] = Field(default=None, max_length=100)
    hectareas: Optional[float] = Field(default=None, ge=0)
    categoria: Optional[str] = None
    estado: Optional[str] = None
    fecha_ingreso: Optional[date] = None
    notas: Optional[str] = None

    @field_validator("cuit")
    @classmethod
    def validate_cuit(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _normalize_cuit(v)


# ──────────────────────────────────────────────
# RESPONSES
# ──────────────────────────────────────────────


class ConsorcistaResponse(BaseModel):
    """Full consorcista detail."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    apellido: str
    cuit: str
    dni: Optional[str] = None
    domicilio: Optional[str] = None
    localidad: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    parcela: Optional[str] = None
    hectareas: Optional[float] = None
    categoria: Optional[str] = None
    estado: str
    fecha_ingreso: Optional[date] = None
    notas: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ConsorcistaListResponse(BaseModel):
    """Lightweight consorcista for list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    apellido: str
    cuit: str
    localidad: Optional[str] = None
    parcela: Optional[str] = None
    hectareas: Optional[float] = None
    categoria: Optional[str] = None
    estado: str
    created_at: datetime


class CsvImportResponse(BaseModel):
    """Response after bulk CSV/XLSX import."""

    filename: str
    processed: int
    created: int
    skipped: int
    errors: list[dict[str, Any]]
