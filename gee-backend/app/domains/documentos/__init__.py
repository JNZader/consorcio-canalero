"""Documentos domain — code catalog + authenticated attachment download."""

from app.domains.documentos.catalog import (
    DOCUMENTOS,
    ArchivoCatalogo,
    DocumentoCatalogo,
    get_archivo,
    get_documento,
    list_documentos,
)

__all__ = [
    "DOCUMENTOS",
    "ArchivoCatalogo",
    "DocumentoCatalogo",
    "get_archivo",
    "get_documento",
    "list_documentos",
]
