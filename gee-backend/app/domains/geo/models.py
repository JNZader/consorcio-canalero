"""SQLAlchemy models for the geo domain."""

import enum
import uuid
from typing import Optional

from sqlalchemy import (
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
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


# ── Models ───────────────────────────────────────


class GeoLayer(UUIDMixin, TimestampMixin, Base):
    """A geospatial layer (raster or vector) stored on disk."""

    __tablename__ = "geo_layers"

    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo: Mapped[str] = mapped_column(
        Enum(TipoGeoLayer, name="tipo_geo_layer"),
        nullable=False,
    )
    fuente: Mapped[str] = mapped_column(
        Enum(FuenteGeoLayer, name="fuente_geo_layer"),
        nullable=False,
    )
    archivo_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Path to the GeoTIFF/GeoJSON file on disk",
    )
    formato: Mapped[str] = mapped_column(
        Enum(FormatoGeoLayer, name="formato_geo_layer"),
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
        Enum(TipoGeoJob, name="tipo_geo_job"),
        nullable=False,
    )
    estado: Mapped[str] = mapped_column(
        Enum(EstadoGeoJob, name="estado_geo_job"),
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
