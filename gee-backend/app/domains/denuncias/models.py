"""SQLAlchemy models for the denuncias domain."""

import enum
import uuid
from datetime import datetime
from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class EstadoDenuncia(str, enum.Enum):
    PENDIENTE = "pendiente"
    EN_REVISION = "en_revision"
    RESUELTO = "resuelto"
    DESCARTADO = "descartado"


# Valid state transitions: state -> set of allowed next states
VALID_TRANSITIONS: dict[str, set[str]] = {
    EstadoDenuncia.PENDIENTE: {
        EstadoDenuncia.EN_REVISION,
        EstadoDenuncia.DESCARTADO,
    },
    EstadoDenuncia.EN_REVISION: {
        EstadoDenuncia.RESUELTO,
        EstadoDenuncia.DESCARTADO,
        EstadoDenuncia.PENDIENTE,
    },
    EstadoDenuncia.RESUELTO: set(),
    EstadoDenuncia.DESCARTADO: set(),
}


class Denuncia(UUIDMixin, TimestampMixin, Base):
    """Denuncia ciudadana — citizen report about canal infrastructure."""

    __tablename__ = "denuncias"

    tipo: Mapped[str] = mapped_column(String(100), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    latitud: Mapped[float] = mapped_column(Float, nullable=False)
    longitud: Mapped[float] = mapped_column(Float, nullable=False)
    geom: Mapped[Optional[str]] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326),
        nullable=True,
    )
    cuenca: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    estado: Mapped[str] = mapped_column(
        Enum(
            EstadoDenuncia,
            name="estado_denuncia",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=EstadoDenuncia.PENDIENTE,
    )
    contacto_telefono: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    contacto_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    foto_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    respuesta: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Phase 4 / F4-K: soft delete for ARCO (Ley 25.326 art. 16).
    # The owner can request deletion; we stamp ``deleted_at`` and the
    # photo is hard-deleted from disk synchronously. The row stays for
    # 1 year (audit trail) then a periodic celery task purges it
    # (``auth.purge_stale_refresh_tokens`` pattern). All read endpoints
    # filter ``deleted_at IS NULL``.
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # Relationships
    historial: Mapped[list["DenunciaHistorial"]] = relationship(
        back_populates="denuncia",
        order_by="DenunciaHistorial.created_at.desc()",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Denuncia {self.id} tipo={self.tipo} estado={self.estado}>"


class DenunciaHistorial(UUIDMixin, Base):
    """Audit log for denuncia state changes."""

    __tablename__ = "denuncias_historial"

    denuncia_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("denuncias.id", ondelete="CASCADE"),
        nullable=False,
    )
    estado_anterior: Mapped[str] = mapped_column(String(50), nullable=False)
    estado_nuevo: Mapped[str] = mapped_column(String(50), nullable=False)
    comentario: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    usuario_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    denuncia: Mapped["Denuncia"] = relationship(back_populates="historial")

    def __repr__(self) -> str:
        return (
            f"<DenunciaHistorial {self.id} {self.estado_anterior}->{self.estado_nuevo}>"
        )
