"""Pydantic v2 schemas for the finanzas domain."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ──────────────────────────────────────────────
# GASTO
# ──────────────────────────────────────────────


class GastoCreate(BaseModel):
    """Payload to create a gasto."""

    descripcion: str = Field(..., min_length=3, max_length=2000)
    monto: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)
    categoria: str = Field(
        ...,
        description="obras | mantenimiento | personal | administrativo | otros",
    )
    fecha: date
    comprobante_url: Optional[str] = None
    proveedor: Optional[str] = Field(default=None, max_length=200)


class GastoUpdate(BaseModel):
    """Partial update for a gasto."""

    descripcion: Optional[str] = Field(default=None, min_length=3, max_length=2000)
    monto: Optional[Decimal] = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    categoria: Optional[str] = None
    fecha: Optional[date] = None
    comprobante_url: Optional[str] = None
    proveedor: Optional[str] = Field(default=None, max_length=200)


class GastoResponse(BaseModel):
    """Full gasto detail."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    descripcion: str
    monto: Decimal
    categoria: str
    fecha: date
    comprobante_url: Optional[str] = None
    proveedor: Optional[str] = None
    usuario_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class GastoListResponse(BaseModel):
    """Lightweight gasto for list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    descripcion: str
    monto: Decimal
    categoria: str
    fecha: date
    proveedor: Optional[str] = None
    created_at: datetime


# ──────────────────────────────────────────────
# INGRESO
# ──────────────────────────────────────────────


class IngresoCreate(BaseModel):
    """Payload to create an ingreso."""

    descripcion: str = Field(..., min_length=3, max_length=2000)
    monto: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)
    categoria: str = Field(
        ...,
        description="cuotas | subsidio | otros",
    )
    fecha: date
    consorcista_id: Optional[uuid.UUID] = None
    comprobante_url: Optional[str] = None


class IngresoUpdate(BaseModel):
    """Partial update for an ingreso."""

    descripcion: Optional[str] = Field(default=None, min_length=3, max_length=2000)
    monto: Optional[Decimal] = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    categoria: Optional[str] = None
    fecha: Optional[date] = None
    consorcista_id: Optional[uuid.UUID] = None
    comprobante_url: Optional[str] = None


class IngresoResponse(BaseModel):
    """Full ingreso detail."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    descripcion: str
    monto: Decimal
    categoria: str
    fecha: date
    consorcista_id: Optional[uuid.UUID] = None
    comprobante_url: Optional[str] = None
    usuario_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class IngresoListResponse(BaseModel):
    """Lightweight ingreso for list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    descripcion: str
    monto: Decimal
    categoria: str
    fecha: date
    consorcista_id: Optional[uuid.UUID] = None
    created_at: datetime


# ──────────────────────────────────────────────
# PRESUPUESTO
# ──────────────────────────────────────────────


class PresupuestoCreate(BaseModel):
    """Payload to create a budget line item."""

    anio: int = Field(..., ge=2000, le=2100)
    rubro: str = Field(..., min_length=2, max_length=100)
    monto_proyectado: Decimal = Field(..., ge=0, max_digits=12, decimal_places=2)


class PresupuestoUpdate(BaseModel):
    """Partial update for a budget line item."""

    monto_proyectado: Optional[Decimal] = Field(
        default=None, ge=0, max_digits=12, decimal_places=2
    )


class PresupuestoResponse(BaseModel):
    """Full presupuesto detail."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    anio: int
    rubro: str
    monto_proyectado: Decimal
    created_at: datetime
    updated_at: datetime


# ──────────────────────────────────────────────
# REPORTS
# ──────────────────────────────────────────────


class BudgetExecutionResponse(BaseModel):
    """Budget vs actual for a single rubro."""

    rubro: str
    proyectado: Decimal
    real: Decimal


class FinancialSummaryResponse(BaseModel):
    """Annual financial summary."""

    anio: int
    total_ingresos: Decimal
    total_gastos: Decimal
    balance: Decimal
