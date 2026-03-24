"""SQLAlchemy models for the finanzas domain."""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin

# ── Category constants ─────────────────────────

CATEGORIAS_GASTO = (
    "obras",
    "mantenimiento",
    "personal",
    "administrativo",
    "otros",
)

CATEGORIAS_INGRESO = (
    "cuotas",
    "subsidio",
    "otros",
)


class Gasto(UUIDMixin, TimestampMixin, Base):
    """Expense record — gastos del consorcio."""

    __tablename__ = "gastos_v2"

    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    monto: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    categoria: Mapped[str] = mapped_column(String(50), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    comprobante_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    proveedor: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Gasto {self.id} ${self.monto} cat={self.categoria}>"


class Ingreso(UUIDMixin, TimestampMixin, Base):
    """Income record — ingresos del consorcio."""

    __tablename__ = "ingresos_v2"

    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    monto: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    categoria: Mapped[str] = mapped_column(String(50), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    consorcista_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    comprobante_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Ingreso {self.id} ${self.monto} cat={self.categoria}>"


class Presupuesto(UUIDMixin, TimestampMixin, Base):
    """Annual budget line item — presupuesto por rubro."""

    __tablename__ = "presupuestos_v2"

    anio: Mapped[int] = mapped_column(Integer, nullable=False)
    rubro: Mapped[str] = mapped_column(String(100), nullable=False)
    monto_proyectado: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<Presupuesto {self.id} anio={self.anio} "
            f"rubro={self.rubro} ${self.monto_proyectado}>"
        )
