"""SQLAlchemy models for the reuniones domain."""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class TipoReunion(str, enum.Enum):
    ORDINARIA = "ordinaria"
    EXTRAORDINARIA = "extraordinaria"
    URGENTE = "urgente"


class EstadoReunion(str, enum.Enum):
    PLANIFICADA = "planificada"
    EN_CURSO = "en_curso"
    FINALIZADA = "finalizada"
    CANCELADA = "cancelada"


# Valid state transitions: state -> set of allowed next states
VALID_TRANSITIONS: dict[str, set[str]] = {
    EstadoReunion.PLANIFICADA: {
        EstadoReunion.EN_CURSO,
        EstadoReunion.CANCELADA,
    },
    EstadoReunion.EN_CURSO: {
        EstadoReunion.FINALIZADA,
        EstadoReunion.CANCELADA,
    },
    EstadoReunion.FINALIZADA: set(),
    EstadoReunion.CANCELADA: set(),
}


class Reunion(UUIDMixin, TimestampMixin, Base):
    """Reunion de comision — commission meeting."""

    __tablename__ = "reuniones_v2"

    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    fecha_reunion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    lugar: Mapped[str] = mapped_column(
        String(200), nullable=False, server_default="Sede Consorcio"
    )
    descripcion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tipo: Mapped[str] = mapped_column(
        Enum(
            TipoReunion,
            name="tipo_reunion",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=TipoReunion.ORDINARIA,
    )
    estado: Mapped[str] = mapped_column(
        Enum(
            EstadoReunion,
            name="estado_reunion",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=EstadoReunion.PLANIFICADA,
    )
    orden_del_dia_items: Mapped[list] = mapped_column(
        JSON, nullable=False, server_default="[]"
    )
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
    )

    # Relationships
    agenda_items: Mapped[list["AgendaItem"]] = relationship(
        back_populates="reunion",
        order_by="AgendaItem.orden",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Reunion {self.id} tipo={self.tipo} estado={self.estado}>"


class AgendaItem(UUIDMixin, Base):
    """Agenda item for a reunion."""

    __tablename__ = "agenda_items_v2"

    reunion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reuniones_v2.id", ondelete="CASCADE"),
        nullable=False,
    )
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    reunion: Mapped["Reunion"] = relationship(back_populates="agenda_items")
    referencias: Mapped[list["AgendaReferencia"]] = relationship(
        back_populates="agenda_item",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<AgendaItem {self.id} titulo={self.titulo}>"


class AgendaReferencia(UUIDMixin, Base):
    """Cross-entity reference from an agenda item."""

    __tablename__ = "agenda_referencias_v2"

    agenda_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agenda_items_v2.id", ondelete="CASCADE"),
        nullable=False,
    )
    entidad_tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    entidad_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    metadata_json: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    agenda_item: Mapped["AgendaItem"] = relationship(
        back_populates="referencias"
    )

    def __repr__(self) -> str:
        return (
            f"<AgendaReferencia {self.id} "
            f"{self.entidad_tipo}:{self.entidad_id}>"
        )
