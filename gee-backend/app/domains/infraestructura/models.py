"""SQLAlchemy models for the infraestructura domain."""

import enum
import uuid
from datetime import date
from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import (
    Date,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class EstadoAsset(str, enum.Enum):
    BUENO = "bueno"
    REGULAR = "regular"
    MALO = "malo"
    CRITICO = "critico"


class Asset(UUIDMixin, TimestampMixin, Base):
    """Infrastructure asset — canal, road, bridge, culvert, gate, etc."""

    __tablename__ = "assets"

    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    tipo: Mapped[str] = mapped_column(String(100), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    estado_actual: Mapped[str] = mapped_column(
        Enum(EstadoAsset, name="estado_asset", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=EstadoAsset.BUENO,
    )
    latitud: Mapped[float] = mapped_column(Float, nullable=False)
    longitud: Mapped[float] = mapped_column(Float, nullable=False)
    geom: Mapped[Optional[str]] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326),
        nullable=True,
    )
    longitud_km: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    material: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    anio_construccion: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    responsable: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Relationships
    mantenimientos: Mapped[list["MantenimientoLog"]] = relationship(
        back_populates="asset",
        order_by="MantenimientoLog.fecha_trabajo.desc()",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Asset {self.id} nombre={self.nombre} tipo={self.tipo}>"


class MantenimientoLog(UUIDMixin, TimestampMixin, Base):
    """Maintenance log entry for an infrastructure asset."""

    __tablename__ = "mantenimiento_logs"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    tipo_trabajo: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    costo: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fecha_trabajo: Mapped[date] = mapped_column(Date, nullable=False)
    realizado_por: Mapped[str] = mapped_column(String(200), nullable=False)
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
    )

    # Relationships
    asset: Mapped["Asset"] = relationship(back_populates="mantenimientos")

    def __repr__(self) -> str:
        return (
            f"<MantenimientoLog {self.id} "
            f"asset={self.asset_id} tipo={self.tipo_trabajo}>"
        )
