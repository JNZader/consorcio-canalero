"""SQLAlchemy models for the settings domain."""

import enum
from typing import Any, Optional

from sqlalchemy import Enum, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class CategoriaSettings(str, enum.Enum):
    GENERAL = "general"
    BRANDING = "branding"
    TERRITORIO = "territorio"
    ANALISIS = "analisis"
    CONTACTO = "contacto"
    MAPA = "mapa"


class SystemSettings(UUIDMixin, TimestampMixin, Base):
    """Per-deployment configuration stored as key-value pairs."""

    __tablename__ = "system_settings"

    clave: Mapped[str] = mapped_column(
        String(200), nullable=False, unique=True, index=True
    )
    valor: Mapped[Any] = mapped_column(JSONB, nullable=False)
    categoria: Mapped[str] = mapped_column(
        Enum(CategoriaSettings, name="categoria_settings", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    descripcion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<SystemSettings {self.clave} ({self.categoria})>"
