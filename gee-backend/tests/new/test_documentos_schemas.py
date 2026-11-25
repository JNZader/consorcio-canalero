"""Documentos public schemas must not expose storage paths."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_archivo_publico_forbids_relative_path_field() -> None:
    from app.domains.documentos.schemas import ArchivoPublico

    with pytest.raises(ValidationError):
        ArchivoPublico(
            id="codist-p-ach__p-ach-pdf",
            nombre="p-ach.pdf",
            mime="application/pdf",
            relative_path="visor_assets/codist/p-ach.pdf",  # type: ignore[call-arg]
        )


def test_documento_resumen_requires_privado_and_forbids_files_path() -> None:
    from app.domains.documentos.schemas import DocumentoResumen

    row = DocumentoResumen(
        id="codist-p-ach",
        titulo="P-ACH",
        group="codist",
        expediente="x",
        clasificacion="privado",
        file_count=1,
    )
    assert row.clasificacion == "privado"
    dumped = row.model_dump()
    assert "relative_path" not in dumped
    assert "files" not in dumped

    with pytest.raises(ValidationError):
        DocumentoResumen(
            id="x",
            titulo="t",
            group="g",
            expediente="",
            clasificacion="publico",  # type: ignore[arg-type]
            file_count=0,
        )


def test_documento_detalle_includes_files_without_paths() -> None:
    from app.domains.documentos.schemas import ArchivoPublico, DocumentoDetalle

    detail = DocumentoDetalle(
        id="codist-p-sar",
        titulo="P-SAR",
        group="codist",
        expediente="e",
        clasificacion="privado",
        file_count=1,
        files=[
            ArchivoPublico(
                id="codist-p-sar__p-sar-pdf",
                nombre="p-sar.pdf",
                mime="application/pdf",
            )
        ],
    )
    payload = detail.model_dump()
    assert payload["files"][0]["nombre"] == "p-sar.pdf"
    assert "relative_path" not in payload["files"][0]
