"""Pydantic response schemas for the Documentos domain (Wave 1)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ArchivoPublico(BaseModel):
    """File descriptor exposed to clients — never includes storage paths."""

    model_config = ConfigDict(extra="forbid")

    id: str
    nombre: str
    mime: str
    bytes: int | None = None
    display_name: str | None = None


class DocumentoResumen(BaseModel):
    """List-row summary. Files live only on detail."""

    model_config = ConfigDict(extra="forbid")

    id: str
    titulo: str
    group: str
    expediente: str
    clasificacion: Literal["privado"] = "privado"
    badge: str | None = None
    fecha: str | None = None
    group_label: str | None = None
    destinatario: str | None = None
    file_count: int = Field(ge=0)


class DocumentoDetalle(DocumentoResumen):
    """Detail payload including public file descriptors."""

    files: list[ArchivoPublico]


class DocumentoListResponse(BaseModel):
    """List envelope (no pagination — fixed ~25-row catalog)."""

    model_config = ConfigDict(extra="forbid")

    items: list[DocumentoResumen]
