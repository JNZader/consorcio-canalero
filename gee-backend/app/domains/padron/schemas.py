"""Pydantic v2 schemas for the padron domain."""

import re
import uuid
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


_NON_DIGITS = re.compile(r"\D")


def validar_cuit(cuit: str) -> bool:
    """
    Validate the AFIP check digit of a CUIT/CUIL (mod-11 algorithm).

    Multipliers [5, 4, 3, 2, 7, 6, 5, 4, 3, 2] are applied to the first
    10 digits, the products are summed and ``resto = suma % 11``:

    - ``resto == 0``  -> check digit must be 0
    - ``resto == 1``  -> invalid (AFIP never issues these; the prefix
      is changed instead, e.g. 20 -> 23)
    - otherwise       -> check digit must be ``11 - resto``

    Accepts formatted (``XX-XXXXXXXX-X``) or digits-only input.
    """
    digits = _NON_DIGITS.sub("", cuit)
    if len(digits) != 11:
        return False

    multiplicadores = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    suma = sum(int(d) * m for d, m in zip(digits[:10], multiplicadores))
    resto = suma % 11

    if resto == 0:
        dv = 0
    elif resto == 1:
        return False
    else:
        dv = 11 - resto

    return dv == int(digits[10])


def _normalize_cuit(value: str) -> str:
    """
    Accept CUIT in formats: XX-XXXXXXXX-X or XXXXXXXXXXX (11 digits).
    Validates the AFIP check digit and always returns the formatted
    version: XX-XXXXXXXX-X.
    """
    stripped = value.strip()
    digits = _NON_DIGITS.sub("", stripped)

    if len(digits) != 11:
        raise ValueError("CUIT debe tener 11 digitos con formato XX-XXXXXXXX-X o XXXXXXXXXXX")

    if not validar_cuit(digits):
        raise ValueError("CUIT invalido: el digito verificador no coincide")

    return f"{digits[:2]}-{digits[2:10]}-{digits[10:]}"


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


class PadronStatsResponse(BaseModel):
    """Aggregate counts + hectareas surfaced by ``GET /padron/stats``."""

    total: int
    por_estado: dict[str, int]
    por_categoria: dict[str, int]
    total_hectareas: float
