"""SQLAlchemy models for the tramites domain."""

import enum
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date,
    Enum,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class TipoTramite(str, enum.Enum):
    OBRA = "obra"
    PERMISO = "permiso"
    HABILITACION = "habilitacion"
    RECLAMO = "reclamo"
    OTRO = "otro"


class EstadoTramite(str, enum.Enum):
    INGRESADO = "ingresado"
    EN_TRAMITE = "en_tramite"
    APROBADO = "aprobado"
    RECHAZADO = "rechazado"
    ARCHIVADO = "archivado"


class PrioridadTramite(str, enum.Enum):
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"
    URGENTE = "urgente"


# Valid state transitions: state -> set of allowed next states
VALID_TRANSITIONS: dict[str, set[str]] = {
    EstadoTramite.INGRESADO: {
        EstadoTramite.EN_TRAMITE,
        EstadoTramite.RECHAZADO,
        EstadoTramite.ARCHIVADO,
    },
    EstadoTramite.EN_TRAMITE: {
        EstadoTramite.APROBADO,
        EstadoTramite.RECHAZADO,
        EstadoTramite.INGRESADO,
        EstadoTramite.ARCHIVADO,
    },
    EstadoTramite.APROBADO: {
        EstadoTramite.ARCHIVADO,
    },
    EstadoTramite.RECHAZADO: {
        EstadoTramite.INGRESADO,
        EstadoTramite.ARCHIVADO,
    },
    EstadoTramite.ARCHIVADO: set(),
}


class Tramite(UUIDMixin, TimestampMixin, Base):
    """Tramite administrativo — administrative procedure tracking."""

    __tablename__ = "tramites_v2"

    tipo: Mapped[str] = mapped_column(
        Enum(TipoTramite, name="tipo_tramite", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    solicitante: Mapped[str] = mapped_column(String(200), nullable=False)
    estado: Mapped[str] = mapped_column(
        Enum(EstadoTramite, name="estado_tramite", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=EstadoTramite.INGRESADO,
    )
    prioridad: Mapped[str] = mapped_column(
        Enum(PrioridadTramite, name="prioridad_tramite", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=PrioridadTramite.MEDIA,
    )
    fecha_ingreso: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        server_default=func.current_date(),
    )
    fecha_resolucion: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True
    )
    resolucion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
    )

    # Relationships
    seguimiento: Mapped[list["TramiteSeguimiento"]] = relationship(
        back_populates="tramite",
        order_by="TramiteSeguimiento.created_at.desc()",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Tramite {self.id} tipo={self.tipo} estado={self.estado}>"


class TramiteSeguimiento(UUIDMixin, Base):
    """Audit log for tramite state changes and follow-ups."""

    __tablename__ = "tramites_seguimiento"

    tramite_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tramites_v2.id", ondelete="CASCADE"),
        nullable=False,
    )
    estado_anterior: Mapped[str] = mapped_column(String(50), nullable=False)
    estado_nuevo: Mapped[str] = mapped_column(String(50), nullable=False)
    comentario: Mapped[str] = mapped_column(Text, nullable=False)
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    tramite: Mapped["Tramite"] = relationship(back_populates="seguimiento")

    def __repr__(self) -> str:
        return (
            f"<TramiteSeguimiento {self.id} "
            f"{self.estado_anterior}->{self.estado_nuevo}>"
        )
