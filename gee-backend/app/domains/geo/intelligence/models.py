"""SQLAlchemy models for the operational intelligence sub-module."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from datetime import datetime as dt_datetime

from app.db.base import Base, TimestampMixin, UUIDMixin


# ── Zona Operativa ────────────────────────────


class ZonaOperativa(UUIDMixin, TimestampMixin, Base):
    """An operational zone (sub-basin) derived from watershed delineation."""

    __tablename__ = "zonas_operativas"

    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    geometria: Mapped[str] = mapped_column(
        Geometry("POLYGON", srid=4326),
        nullable=False,
        comment="Zone boundary polygon",
    )
    cuenca: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Parent watershed name",
    )
    superficie_ha: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Area in hectares",
    )

    # Relationships
    indices_hidricos: Mapped[list["IndiceHidrico"]] = relationship(
        back_populates="zona",
        cascade="all, delete-orphan",
    )
    alertas: Mapped[list["AlertaGeo"]] = relationship(
        back_populates="zona",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ZonaOperativa {self.id} nombre={self.nombre!r}>"


# ── Indice Hidrico de Criticidad ──────────────


class IndiceHidrico(UUIDMixin, TimestampMixin, Base):
    """Hydric Criticality Index (HCI) calculation result for a zone."""

    __tablename__ = "indices_hidricos"

    zona_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("zonas_operativas.id", ondelete="CASCADE"),
        nullable=False,
    )
    fecha_calculo: Mapped[date] = mapped_column(Date, nullable=False)
    pendiente_media: Mapped[float] = mapped_column(Float, nullable=False)
    acumulacion_media: Mapped[float] = mapped_column(Float, nullable=False)
    twi_medio: Mapped[float] = mapped_column(Float, nullable=False)
    proximidad_canal_m: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Average distance to nearest canal in meters",
    )
    historial_inundacion: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Flood history factor 0-1",
    )
    indice_final: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Final HCI score 0-100",
    )
    nivel_riesgo: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="bajo / medio / alto / critico",
    )

    # Relationships
    zona: Mapped["ZonaOperativa"] = relationship(back_populates="indices_hidricos")

    def __repr__(self) -> str:
        return (
            f"<IndiceHidrico {self.id} zona={self.zona_id} "
            f"indice={self.indice_final} nivel={self.nivel_riesgo}>"
        )


# ── Punto de Conflicto ────────────────────────


class PuntoConflicto(UUIDMixin, TimestampMixin, Base):
    """A detected infrastructure conflict point (canal/road/drainage crossing)."""

    __tablename__ = "puntos_conflicto"

    tipo: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="canal_camino / canal_drenaje / camino_drenaje",
    )
    geometria: Mapped[str] = mapped_column(
        Geometry("POINT", srid=4326),
        nullable=False,
        comment="Conflict location",
    )
    descripcion: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default="",
    )
    severidad: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="baja / media / alta",
    )
    infraestructura_ids: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        comment="Related asset IDs",
    )
    acumulacion_valor: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Flow accumulation at conflict point",
    )
    pendiente_valor: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Slope at conflict point",
    )

    def __repr__(self) -> str:
        return (
            f"<PuntoConflicto {self.id} tipo={self.tipo!r} "
            f"severidad={self.severidad!r}>"
        )


# ── Alerta Geo ────────────────────────────────


class AlertaGeo(UUIDMixin, Base):
    """Geo-spatial alert triggered by threshold, rainfall, or SAR change."""

    __tablename__ = "alertas_geo"

    tipo: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="umbral_superado / lluvia_reciente / cambio_sar",
    )
    zona_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("zonas_operativas.id", ondelete="SET NULL"),
        nullable=True,
    )
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    nivel: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="info / advertencia / critico",
    )
    datos: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Additional alert data payload",
    )
    activa: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    created_at: Mapped[dt_datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    zona: Mapped[Optional["ZonaOperativa"]] = relationship(back_populates="alertas")

    def __repr__(self) -> str:
        return f"<AlertaGeo {self.id} tipo={self.tipo!r} nivel={self.nivel!r}>"


# ── Composite Zonal Stats ────────────────────


class CompositeZonalStats(UUIDMixin, TimestampMixin, Base):
    """Per-zone statistics from composite analysis rasters (flood risk, drainage need)."""

    __tablename__ = "composite_zonal_stats"
    __table_args__ = (
        UniqueConstraint("zona_id", "tipo", name="uq_composite_zonal_stats_zona_tipo"),
    )

    zona_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("zonas_operativas.id", ondelete="CASCADE"),
        nullable=False,
    )
    tipo: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="flood_risk | drainage_need",
    )
    fecha_calculo: Mapped[date] = mapped_column(Date, nullable=False)
    mean_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Mean composite score for the zone",
    )
    max_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Maximum composite score for the zone",
    )
    p90_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="90th percentile composite score",
    )
    area_high_risk_ha: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Area in hectares where score > 70",
    )
    weights_used: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Snapshot of weights at computation time",
    )

    # Relationships
    zona: Mapped["ZonaOperativa"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<CompositeZonalStats {self.id} zona={self.zona_id} "
            f"tipo={self.tipo!r} mean={self.mean_score}>"
        )
