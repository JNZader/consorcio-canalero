"""SQLAlchemy models for the geo domain."""

import enum
import uuid
from datetime import date, datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

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
        Enum(TipoGeoLayer, name="tipo_geo_layer", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    fuente: Mapped[str] = mapped_column(
        Enum(FuenteGeoLayer, name="fuente_geo_layer", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    archivo_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Path to the GeoTIFF/GeoJSON file on disk",
    )
    formato: Mapped[str] = mapped_column(
        Enum(FormatoGeoLayer, name="formato_geo_layer", values_callable=lambda x: [e.value for e in x]),
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
        Enum(TipoGeoJob, name="tipo_geo_job", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    estado: Mapped[str] = mapped_column(
        Enum(EstadoGeoJob, name="estado_geo_job", values_callable=lambda x: [e.value for e in x]),
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
