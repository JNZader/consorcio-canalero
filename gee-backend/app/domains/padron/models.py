"""SQLAlchemy models for the padron domain."""

import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date,
    Enum,
    Float,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class EstadoConsorcista(str, enum.Enum):
    ACTIVO = "activo"
    INACTIVO = "inactivo"
    SUSPENDIDO = "suspendido"


class Consorcista(UUIDMixin, TimestampMixin, Base):
    """Consorcista — member of the consorcio canalero."""

    __tablename__ = "consorcistas"

    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    apellido: Mapped[str] = mapped_column(String(200), nullable=False)
    cuit: Mapped[str] = mapped_column(String(13), nullable=False, unique=True)
    dni: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    domicilio: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    localidad: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    telefono: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    parcela: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    hectareas: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    categoria: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="propietario, arrendatario, otro",
    )
    estado: Mapped[str] = mapped_column(
        Enum(EstadoConsorcista, name="estado_consorcista"),
        nullable=False,
        default=EstadoConsorcista.ACTIVO,
    )
    fecha_ingreso: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notas: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<Consorcista {self.id} "
            f"{self.apellido}, {self.nombre} cuit={self.cuit}>"
        )
