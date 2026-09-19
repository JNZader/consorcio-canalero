"""ORM for ``punto_interes`` — staff notepad pins, unpublished."""

from __future__ import annotations

import uuid
from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import CheckConstraint, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin

PUNTO_INTERES_TIPOS: tuple[str, ...] = ("alcantarilla", "alteo", "taponamiento", "otro")


class PuntoInteres(UUIDMixin, TimestampMixin, Base):
    """A staff-authored map pin. Not a denuncia, not a survey, not a conflict.

    Mirrors ``0025_add_punto_interes``. ``created_by`` is a UUID with **no FK**
    to ``users``: auth tests override ``current_active_user`` with a
    ``SimpleNamespace``, and an FK would make POST require a real users row.
    """

    __tablename__ = "punto_interes"
    __table_args__ = (
        CheckConstraint(
            "char_length(titulo) BETWEEN 1 AND 120",
            name="ck_punto_interes_titulo_len",
        ),
        CheckConstraint(
            "nota IS NULL OR char_length(nota) <= 2000",
            name="ck_punto_interes_nota_len",
        ),
        CheckConstraint(
            "tipo IN ('alcantarilla', 'alteo', 'taponamiento', 'otro')",
            name="ck_punto_interes_tipo",
        ),
        Index("ix_punto_interes_geom", "geometria", postgresql_using="gist"),
    )

    geometria: Mapped[str] = mapped_column(
        Geometry("POINT", srid=4326),
        nullable=False,
        comment="Pin location in WGS84",
    )
    titulo: Mapped[str] = mapped_column(Text, nullable=False)
    nota: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Staff user id; no FK to users (see module docstring)",
    )

    def __repr__(self) -> str:
        return f"<PuntoInteres {self.id} tipo={self.tipo!r} titulo={self.titulo!r}>"
