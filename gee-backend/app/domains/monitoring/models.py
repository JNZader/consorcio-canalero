"""SQLAlchemy models for the monitoring domain."""

import enum
import uuid
from datetime import date
from typing import Any, Optional

from sqlalchemy import (
    Date,
    Enum,
    Float,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


# ── Enums ─────────────────────────────────────


class EstadoSugerencia(str, enum.Enum):
    PENDIENTE = "pendiente"
    REVISADA = "revisada"
    IMPLEMENTADA = "implementada"
    DESCARTADA = "descartada"


class TipoAnalisis(str, enum.Enum):
    INUNDACION = "inundacion"
    VEGETACION = "vegetacion"
    SAR = "sar"
    CLASIFICACION = "clasificacion"


# ── Sugerencia ─────────────────────────────────


class Sugerencia(UUIDMixin, TimestampMixin, Base):
    """Sugerencia ciudadana o de la comision."""

    __tablename__ = "sugerencias_v2"

    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    categoria: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    estado: Mapped[str] = mapped_column(
        Enum(EstadoSugerencia, name="estado_sugerencia", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=EstadoSugerencia.PENDIENTE,
    )
    contacto_email: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    contacto_nombre: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )
    respuesta: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    usuario_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<Sugerencia {self.id} estado={self.estado}>"


# ── AnalisisGee ────────────────────────────────


class AnalisisGee(UUIDMixin, TimestampMixin, Base):
    """Resultado de un analisis de Google Earth Engine."""

    __tablename__ = "analisis_gee"

    tipo: Mapped[str] = mapped_column(
        Enum(TipoAnalisis, name="tipo_analisis", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    resultados: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    hectareas_afectadas: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    porcentaje_area: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    parametros: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<AnalisisGee {self.id} tipo={self.tipo} "
            f"{self.fecha_inicio} – {self.fecha_fin}>"
        )
