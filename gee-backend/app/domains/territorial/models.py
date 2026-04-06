"""SQLAlchemy models for the territorial domain (suelos + canales geo layers)."""

from __future__ import annotations

import uuid
import datetime

from geoalchemy2 import Geometry
from sqlalchemy import String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SueloCatastro(Base):
    """Soil classification polygons imported from a GeoJSON (suelos_cu.geojson)."""

    __tablename__ = "suelos_catastro"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    simbolo: Mapped[str] = mapped_column(String(50), nullable=False)
    cap: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(50), nullable=True)
    geometria: Mapped[str] = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326), nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )


class CanalGeo(Base):
    """Canal linestrings imported from a GeoJSON (canales_existentes.geojson)."""

    __tablename__ = "canales_geo"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    nombre: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tipo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    geometria: Mapped[str] = mapped_column(
        Geometry("MULTILINESTRING", srid=4326), nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
