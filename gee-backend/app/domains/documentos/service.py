"""Documentos business logic: catalog mapping + realpath jail for downloads."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from app.domains.documentos.catalog import (
    ArchivoCatalogo,
    DocumentoCatalogo,
    get_archivo,
    get_documento,
    list_documentos,
)
from app.domains.documentos.schemas import (
    ArchivoPublico,
    DocumentoDetalle,
    DocumentoListResponse,
    DocumentoResumen,
)


class DocumentoNotFound(Exception):
    """Unknown dossier/file id or path outside the jail / missing on disk."""


def _to_resumen(doc: DocumentoCatalogo) -> DocumentoResumen:
    return DocumentoResumen(
        id=doc.id,
        titulo=doc.titulo,
        group=doc.group,
        expediente=doc.expediente,
        clasificacion=doc.clasificacion,
        badge=doc.badge,
        fecha=doc.fecha,
        group_label=doc.group_label,
        destinatario=doc.destinatario,
        file_count=len(doc.files),
    )


def _to_archivo_publico(archivo: ArchivoCatalogo) -> ArchivoPublico:
    return ArchivoPublico(
        id=archivo.id,
        nombre=archivo.nombre,
        mime=archivo.mime,
        bytes=archivo.bytes,
        display_name=archivo.display_name,
    )


def list_resumenes(group: str | None = None) -> DocumentoListResponse:
    items = [_to_resumen(doc) for doc in list_documentos(group=group)]
    return DocumentoListResponse(items=items)


def get_detalle(dossier_id: str) -> DocumentoDetalle:
    doc = get_documento(dossier_id)
    if doc is None:
        raise DocumentoNotFound(dossier_id)
    resumen = _to_resumen(doc)
    return DocumentoDetalle(
        **resumen.model_dump(),
        files=[_to_archivo_publico(f) for f in doc.files],
    )


def resolve_archivo_path(documentos_root: str, relative_path: str) -> Path:
    """Resolve ``relative_path`` under ``documentos_root`` with a realpath jail.

    Raises DocumentoNotFound on traversal, escape, or missing file.
    """
    if not relative_path or relative_path.startswith("/") or "\\" in relative_path:
        raise DocumentoNotFound("invalid path")
    parts = Path(relative_path).parts
    if any(part == ".." for part in parts):
        raise DocumentoNotFound("invalid path")

    root = Path(os.path.realpath(documentos_root))
    candidate = Path(os.path.realpath(root.joinpath(*parts)))
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise DocumentoNotFound("outside root") from exc
    if not candidate.is_file():
        raise DocumentoNotFound("missing")
    return candidate


def open_archivo_stream(
    documentos_root: str, dossier_id: str, file_id: str
) -> tuple[ArchivoCatalogo, Path, Iterator[bytes]]:
    """Return catalog file metadata, jailed path, and a chunk iterator."""
    hit = get_archivo(dossier_id, file_id)
    if hit is None:
        raise DocumentoNotFound(file_id)
    _doc, archivo = hit
    path = resolve_archivo_path(documentos_root, archivo.relative_path)

    def _iter() -> Iterator[bytes]:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(64 * 1024)
                if not chunk:
                    break
                yield chunk

    return archivo, path, _iter()
