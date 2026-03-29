"""SQLAlchemy models for the capas (map layers) domain."""

import enum
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class TipoCapa(str, enum.Enum):
    POLYGON = "polygon"
    LINE = "line"
    POINT = "point"
    RASTER = "raster"
    TILE = "tile"


class FuenteCapa(str, enum.Enum):
    LOCAL = "local"
    GEE = "gee"
    UPLOAD = "upload"


class Capa(UUIDMixin, TimestampMixin, Base):
    """Capa del mapa — configurable map layer for the GIS viewer."""

    __tablename__ = "capas_v2"

    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tipo: Mapped[str] = mapped_column(
        Enum(TipoCapa, name="tipo_capa", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    fuente: Mapped[str] = mapped_column(
        Enum(FuenteCapa, name="fuente_capa", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    geojson_data: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    estilo: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    visible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    orden: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    es_publica: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    publicacion_fecha: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    def __repr__(self) -> str:
        return f"<Capa {self.id} nombre={self.nombre!r} tipo={self.tipo}>"
