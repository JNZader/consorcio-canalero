"""SQLAlchemy models for the operational intelligence sub-module."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
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
    capacidad_m3s: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Canal hydraulic capacity m3/s",
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
        return f"<PuntoConflicto {self.id} tipo={self.tipo!r} severidad={self.severidad!r}>"


# ── Cruce Camino ──────────────────────────────


class CruceCamino(UUIDMixin, TimestampMixin, Base):
    """A road crossing point — natural drainage or canal (flujo-caminos Fase A).

    Mirrors ``0022_add_cruce_camino`` column for column. A **dedicated** table, on
    purpose: ``PuntoConflicto`` above has no area column, so the per-area re-run
    this feature performs (``DELETE ... WHERE area_id = :area_id``) is not
    expressible there, and its ``NOT NULL`` ``severidad`` / ``pendiente_valor``
    would fabricate a risk grade on every crossing. ``PuntoConflicto`` is
    therefore **not modified** and keeps counting exactly what it counts today.

    **No ``severidad``, no ``pendiente_valor``, no ``acumulacion_valor``.** This
    capability derives a direction, a contributing area and a relative rank; it
    derives no risk grade and no slope, and a column that would have to be
    invented to be filled is a column that does not belong here.

    The per-``tipo`` rules live in the four CHECKs rather than in ``nullable``,
    because the same column is required on one ``tipo`` and meaningless on the
    other: ``flujo_natural`` needs direction, road bearing, side, area, rank and a
    confidence band and may carry no ``canal_ref``; ``canal`` needs a
    ``canal_ref`` and never carries a rank, since ranking is defined over the
    natural-drainage set only.
    """

    __tablename__ = "cruce_camino"
    __table_args__ = (
        CheckConstraint("tipo IN ('flujo_natural', 'canal')", name="ck_cruce_tipo"),
        CheckConstraint(
            "confianza IS NULL OR confianza IN ('alta', 'baja')",
            name="ck_cruce_confianza_valores",
        ),
        CheckConstraint(
            "tipo <> 'flujo_natural' OR ("
            "direccion_flujo_deg IS NOT NULL AND rumbo_camino_deg IS NOT NULL "
            "AND lado_cruce IS NOT NULL "
            "AND area_aporte_ha IS NOT NULL AND orden_ranking IS NOT NULL)",
            name="ck_cruce_flujo_completo",
        ),
        CheckConstraint(
            "tipo <> 'canal' OR (orden_ranking IS NULL AND canal_ref IS NOT NULL)",
            name="ck_cruce_canal_sin_rank",
        ),
        CheckConstraint(
            "tipo <> 'flujo_natural' OR canal_ref IS NULL",
            name="ck_cruce_flujo_sin_canal",
        ),
        CheckConstraint(
            "tipo <> 'flujo_natural' OR confianza IS NOT NULL",
            name="ck_cruce_flujo_confianza",
        ),
        Index("ix_cruce_camino_area", "area_id", "tipo"),
        Index("ix_cruce_camino_tramo", "tramo_ref"),
    )

    area_id: Mapped[str] = mapped_column(
        # ``String(100)`` — physically identical to the migration's
        # ``VARCHAR(100)`` and to ``GeoLayer.area_id``. NOT a UUID: ``geo_jobs``
        # has no area column at all, so there is no UUID precedent, and the
        # staleness comparison stays a plain ``text = text``.
        String(100),
        nullable=False,
        comment="Processing area, matching geo_layer.area_id",
    )
    tramo_ref: Mapped[str] = mapped_column(
        Text,
        ForeignKey("red_vial.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Road segment this crossing belongs to",
    )
    tipo: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="flujo_natural | canal",
    )
    geometria: Mapped[str] = mapped_column(
        Geometry("POINT", srid=4326),
        nullable=False,
        comment="Crossing location, REPROJECTED to 4326 (never merely stamped)",
    )
    direccion_flujo_deg: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Absolute azimuth in the raster's UTM grid frame, [0, 360)",
    )
    rumbo_camino_deg: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Local road bearing at the crossing, same UTM-grid frame",
    )
    lado_cruce: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="izq_a_der | der_a_izq, relative to the stored digitization",
    )
    area_aporte_ha: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Upslope contributing area in hectares",
    )
    orden_ranking: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Rank over the flujo_natural rows only; always NULL on canal",
    )
    confianza: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="alta | baja — the three-band crossing predicate",
    )
    nota: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Why confianza is baja, when it is",
    )
    canal_ref: Mapped[Optional[str]] = mapped_column(
        # TEXT, not UUID: ``canal_consorcio.id`` is ``TEXT PRIMARY KEY``
        # (``0020_add_canal_consorcio.py:65-66``), so a UUID column could never
        # have referenced it and would have accepted any value at all.
        #
        # The ``REFERENCES canal_consorcio(id) ON DELETE RESTRICT`` lives in the
        # migration and NOT here, deliberately: ``canal_consorcio`` is a
        # migration-only table with no ORM model (it is read through ``text()``
        # SQL — ``ficha_service.py:518-571``, ``load_canales_consorcio.py``), so
        # a ``ForeignKey`` on this column would make ``Base.metadata.create_all``
        # raise ``NoReferencedTableError`` for every test in the suite. The real
        # database gets the constraint from ``0022``; the migration test asserts
        # its target and its ``RESTRICT`` delete rule against the real DDL.
        Text,
        nullable=True,
        comment="Canal this crossing belongs to, for tipo='canal' (FK lives in 0022)",
    )
    geo_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("geo_jobs.id"),
        nullable=False,
        comment="The run that produced this row",
    )
    calculada_en: Mapped[dt_datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Generation timestamp of the run; the staleness comparison reads it",
    )

    def __repr__(self) -> str:
        return (
            f"<CruceCamino {self.id} tipo={self.tipo!r} tramo={self.tramo_ref!r} "
            f"rank={self.orden_ranking}>"
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


# ── Canal Suggestion ────────────────────────


class CanalSuggestion(UUIDMixin, Base):
    """AI-generated canal infrastructure suggestion from network analysis."""

    __tablename__ = "canal_suggestions"

    tipo: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="hotspot | gap | route | maintenance | bottleneck",
    )
    geometry: Mapped[Optional[str]] = mapped_column(
        Geometry("GEOMETRY", srid=4326),
        nullable=True,
        comment="Suggestion geometry (point, line, or polygon)",
    )
    score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Relevance / priority score 0-100",
    )
    metadata_: Mapped[Optional[dict]] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
        comment="Analysis-specific payload (parameters, sources, etc.)",
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="Groups suggestions from the same analysis run",
    )
    created_at: Mapped[dt_datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<CanalSuggestion {self.id} tipo={self.tipo!r} "
            f"score={self.score} batch={self.batch_id}>"
        )


# ── Parcela Catastro ─────────────────────────


class ParcelaCatastro(Base):
    """IDECOR cadastral parcel with PostGIS geometry for spatial queries."""

    __tablename__ = "parcelas_catastro"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    nomenclatura: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        comment="IDECOR parcel identifier — links to consorcistas.parcela",
    )
    geometria: Mapped[str] = mapped_column(
        Geometry("POLYGON", srid=4326),
        nullable=False,
    )
    tipo_parcela: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    desig_oficial: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    departamento: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    pedania: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    superficie_ha: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Area in hectares",
    )
    nro_cuenta: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    par_idparcela: Mapped[Optional[int]] = mapped_column(nullable=True)
    created_at: Mapped[dt_datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<ParcelaCatastro {self.id} nomenclatura={self.nomenclatura!r}>"
