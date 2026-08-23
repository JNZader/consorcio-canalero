"""SQLAlchemy models for the geo domain."""

import enum
import uuid
from datetime import date, datetime
from typing import Optional

import sqlalchemy as sa
from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


# ── Enums ────────────────────────────────────────


class TipoGeoLayer(str, enum.Enum):
    """Types of geospatial layers produced by terrain analysis."""

    SLOPE = "slope"
    ASPECT = "aspect"
    FLOW_DIR = "flow_dir"
    FLOW_ACC = "flow_acc"
    TWI = "twi"
    HAND = "hand"
    DRAINAGE = "drainage"
    TERRAIN_CLASS = "terrain_class"
    DEM_RAW = "dem_raw"
    BASINS = "basins"
    PROFILE_CURVATURE = "profile_curvature"
    TPI = "tpi"
    FLOOD_RISK = "flood_risk"
    DRAINAGE_NEED = "drainage_need"
    PRECIP_NORMAL = "precip_normal"


class FuenteGeoLayer(str, enum.Enum):
    """Source of a geospatial layer."""

    DEM_PIPELINE = "dem_pipeline"
    GEE = "gee"
    MANUAL = "manual"


class FormatoGeoLayer(str, enum.Enum):
    """Output format of a geospatial layer."""

    GEOTIFF = "geotiff"
    GEOJSON = "geojson"


class EstadoGeoJob(str, enum.Enum):
    """Status of a geo processing job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TipoGeoJob(str, enum.Enum):
    """Types of geo processing jobs."""

    DEM_PIPELINE = "dem_pipeline"
    SLOPE = "slope"
    ASPECT = "aspect"
    FLOW_DIR = "flow_dir"
    FLOW_ACC = "flow_acc"
    TWI = "twi"
    HAND = "hand"
    DRAINAGE = "drainage"
    TERRAIN_CLASS = "terrain_class"
    GEE_FLOOD = "gee_flood"
    GEE_CLASSIFICATION = "gee_classification"
    DEM_FULL_PIPELINE = "dem_full_pipeline"
    BASIN_DELINEATION = "basin_delineation"
    COMPOSITE_ANALYSIS = "composite_analysis"


class TipoAnalisisGee(str, enum.Enum):
    """Types of GEE analyses."""

    FLOOD = "flood"
    VEGETATION = "vegetation"
    CLASSIFICATION = "classification"
    NDVI = "ndvi"
    CUSTOM = "custom"
    SAR_TEMPORAL = "sar_temporal"


# ── Models ───────────────────────────────────────


class GeoLayer(UUIDMixin, TimestampMixin, Base):
    """A geospatial layer (raster or vector) stored on disk."""

    __tablename__ = "geo_layers"

    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo: Mapped[str] = mapped_column(
        Enum(
            TipoGeoLayer,
            name="tipo_geo_layer",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    fuente: Mapped[str] = mapped_column(
        Enum(
            FuenteGeoLayer,
            name="fuente_geo_layer",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    archivo_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Path to the GeoTIFF/GeoJSON file on disk",
    )
    formato: Mapped[str] = mapped_column(
        Enum(
            FormatoGeoLayer,
            name="formato_geo_layer",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=FormatoGeoLayer.GEOTIFF,
    )
    srid: Mapped[int] = mapped_column(Integer, nullable=False, default=4326)
    bbox: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Bounding box [minx, miny, maxx, maxy]",
    )
    metadata_extra: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Resolution, nodata value, statistics, etc.",
    )
    area_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Identifier for the processing area",
    )

    def __repr__(self) -> str:
        return f"<GeoLayer {self.id} nombre={self.nombre!r} tipo={self.tipo}>"


class GeoJob(UUIDMixin, TimestampMixin, Base):
    """A geo processing job submitted via Celery."""

    __tablename__ = "geo_jobs"

    tipo: Mapped[str] = mapped_column(
        Enum(
            TipoGeoJob,
            name="tipo_geo_job",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    estado: Mapped[str] = mapped_column(
        Enum(
            EstadoGeoJob,
            name="estado_geo_job",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=EstadoGeoJob.PENDING,
    )
    celery_task_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Celery async result ID",
    )
    parametros: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Input parameters for the job",
    )
    resultado: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Output summary after completion",
    )
    error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if job failed",
    )
    progreso: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Completion percentage 0-100",
    )
    usuario_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
        comment="User who submitted the job",
    )

    def __repr__(self) -> str:
        return f"<GeoJob {self.id} tipo={self.tipo} estado={self.estado}>"


class AnalisisGeo(UUIDMixin, TimestampMixin, Base):
    """A GEE analysis request tracked in the geo domain.

    Separate from monitoring.AnalisisGee — this model tracks analysis
    requests submitted through the geo domain pipeline, with Celery
    task lifecycle (estado, celery_task_id) and richer result metadata.
    """

    __tablename__ = "geo_analisis_gee"

    tipo: Mapped[str] = mapped_column(
        Enum(
            TipoAnalisisGee,
            name="tipo_analisis_geo",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    fecha_analisis: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_inicio: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="Analysis period start date",
    )
    fecha_fin: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="Analysis period end date",
    )
    parametros: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Input params: date range, region, thresholds, method",
    )
    resultado: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Output: stats, metrics, tile URLs, classification %",
    )
    estado: Mapped[str] = mapped_column(
        Enum(
            EstadoGeoJob,
            name="estado_geo_job",
            values_callable=lambda x: [e.value for e in x],
            create_constraint=False,
        ),
        nullable=False,
        default=EstadoGeoJob.PENDING,
    )
    error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if analysis failed",
    )
    celery_task_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Celery async result ID",
    )
    usuario_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
        comment="User who requested the analysis",
    )

    def __repr__(self) -> str:
        return f"<AnalisisGeo {self.id} tipo={self.tipo} estado={self.estado}>"


class GeoApprovedZoning(UUIDMixin, TimestampMixin, Base):
    """Persisted approved consorcio zoning used by 2D and 3D views."""

    __tablename__ = "geo_approved_zonings"

    nombre: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="Zonificación Consorcio aprobada",
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    cuenca: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Optional parent watershed/grouping identifier",
    )
    feature_collection: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="Approved dissolved zoning as GeoJSON FeatureCollection",
    )
    assignments: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Optional draft basin->zone assignments used to build the zoning",
    )
    zone_names: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Optional human-friendly names per approved zone",
    )
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Optional approval notes or change summary",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=sa.text("true"),
    )
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    approved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<GeoApprovedZoning {self.id} nombre={self.nombre!r} cuenca={self.cuenca!r}>"


class FloodEvent(UUIDMixin, TimestampMixin, Base):
    """A labeled flood event used for model calibration."""

    __tablename__ = "flood_events"

    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Optional notes about this event",
    )
    satellite_source: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="COPERNICUS/S2_SR_HARMONIZED",
        server_default="COPERNICUS/S2_SR_HARMONIZED",
    )

    labels: Mapped[list["FloodLabel"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<FloodEvent {self.id} date={self.event_date}>"


class FloodLabel(UUIDMixin, TimestampMixin, Base):
    """A per-zone flood label within an event."""

    __tablename__ = "flood_labels"
    __table_args__ = (UniqueConstraint("event_id", "zona_id", name="uq_flood_label_event_zona"),)

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("flood_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    zona_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("zonas_operativas.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_flooded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ndwi_value: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="NDWI value at event date for this zone",
    )
    extracted_features: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="DEM-based features: {hand_mean, twi_mean, slope_mean, flow_acc_mean}",
    )

    event: Mapped["FloodEvent"] = relationship(back_populates="labels")

    def __repr__(self) -> str:
        return f"<FloodLabel {self.id} event={self.event_id} zona={self.zona_id} flooded={self.is_flooded}>"


class NdwiBaseline(UUIDMixin, TimestampMixin, Base):
    """Historical NDWI baseline per zona operativa.

    Computed from Sentinel-2 dry-season imagery over multiple years.
    Used to detect anomalous water levels: z-score = (ndwi - mean) / std.
    """

    __tablename__ = "ndwi_baselines"

    zona_operativa_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("zonas_operativas.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        comment="One baseline per zona",
    )
    ndwi_mean: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Mean NDWI across dry-season images",
    )
    ndwi_std: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Std dev of NDWI across dry-season images",
    )
    sample_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of S2 images used",
    )
    dry_season_months: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        comment="Month numbers used e.g. [6,7,8]",
    )
    years_back: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Years of history used",
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the baseline was last computed",
    )

    def __repr__(self) -> str:
        return f"<NdwiBaseline zona={self.zona_operativa_id} mean={self.ndwi_mean:.3f} std={self.ndwi_std:.3f}>"


# ── Red vial ─────────────────────────────────────


class RedVial(TimestampMixin, Base):
    """One native road-network feature — the segment unit of the road analysis.

    Mirrors ``0021_add_red_vial`` column for column. Not ``UUIDMixin``: the PK is
    the source's own string id (``"28188"``), ordinal-suffixed (``"28188#2"``)
    for later rows of the same lineage, because the crossing and survey tables
    reference it and that reference has to survive a reload.

    ``source_id`` is the id the source publishes and ``parte`` is which connected
    part of that feature the row carries; every row of a lineage shares the
    ``source_id`` and at most one row is ``activo`` per ``(source_id, parte)``
    (partial unique index ``ux_red_vial_source_activo``). ``geom_hash`` is the
    sha256 of the WKB of the stored part geometry, which is how the loader tells
    "same road re-published" from "different road, same id". The loader never
    deletes: a segment that leaves the source is retired with ``activo = false``.
    """

    __tablename__ = "red_vial"
    __table_args__ = (
        # PARTIAL unique: at most one ACTIVE row per source id, while retired
        # rows of the same lineage remain. Declared here as well as in the
        # migration because the test schema is built from ``Base.metadata``.
        Index(
            "ux_red_vial_source_activo",
            "source_id",
            "parte",
            unique=True,
            postgresql_where=sa.text("activo"),
        ),
        Index("ix_red_vial_ccc", "ccc"),
        Index("ix_red_vial_hct", "hct"),
    )

    id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
        comment="Row identity: source id, ordinal-suffixed for later lineage rows",
    )
    source_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        index=True,
        comment="Identifier published by the source; shared by a whole lineage",
    )
    parte: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        server_default=sa.text("1"),
        comment="Which connected part of the source feature this row carries",
    )
    fna: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Full name")
    gna: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Generic name")
    rtn: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Route number")
    fun: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Function code")
    rst: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Surface type")
    hct: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Hierarchy")
    ccn: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Consorcio name")
    ccc: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Consorcio code")
    rcc: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Consorcio road nr")
    red: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="Network tier")
    lzn: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Length declared by the source, in km",
    )
    geom: Mapped[str] = mapped_column(
        Geometry("LINESTRING", srid=4326),
        nullable=False,
        comment="Road segment trace",
    )
    geom_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="sha256 of the WKB of the normalized geometry",
    )
    activo: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=sa.text("true"),
        comment="False once retired; rows are never deleted",
    )
    ultima_carga_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Every load writes it, even when no attribute changed",
    )

    def __repr__(self) -> str:
        return f"<RedVial {self.id!r} source={self.source_id!r} activo={self.activo}>"
