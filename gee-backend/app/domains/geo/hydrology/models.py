"""SQLAlchemy models for the hydrology subdomain."""

import uuid
from datetime import date
from typing import Optional

from sqlalchemy import Date, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class FloodFlowResult(UUIDMixin, TimestampMixin, Base):
    """Peak flood flow estimate computed via the Rational Method for a zona operativa."""

    __tablename__ = "flood_flow_results"
    __table_args__ = (
        UniqueConstraint("zona_id", "fecha_lluvia", name="uq_flood_flow_zona_fecha"),
        Index("ix_flood_flow_results_zona_id", "zona_id"),
    )

    zona_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("zonas_operativas.id", ondelete="CASCADE"),
        nullable=False,
        comment="FK to zonas_operativas",
    )
    fecha_calculo: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="Date this computation was run",
    )
    fecha_lluvia: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="Rainfall event date (UNIQUE with zona_id)",
    )
    tc_minutos: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Concentration time in minutes (Kirpich formula)",
    )
    c_escorrentia: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Runoff coefficient C (dimensionless)",
    )
    c_source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="How C was obtained: ndvi_sentinel2 | fallback_default | manual",
    )
    intensidad_mm_h: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Rainfall intensity in mm/h",
    )
    area_km2: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Zone drainage area in km²",
    )
    caudal_m3s: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Estimated peak flow Q in m³/s (Rational Method)",
    )
    capacidad_m3s: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Canal capacity in m³/s (nullable — may not be set yet)",
    )
    porcentaje_capacidad: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Q / capacity * 100 (nullable when capacity is unknown)",
    )
    nivel_riesgo: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="bajo | moderado | alto | critico | sin_capacidad",
    )
    metadata_: Mapped[Optional[dict]] = mapped_column(
        JSON,
        name="metadata",
        nullable=True,
        comment="Arbitrary extra metadata (JSONB)",
    )

    def __repr__(self) -> str:
        return (
            f"<FloodFlowResult {self.id} zona={self.zona_id} "
            f"fecha={self.fecha_lluvia} Q={self.caudal_m3s} riesgo={self.nivel_riesgo}>"
        )
