"""realpath jail for Documentos downloads."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.domains.documentos.service import DocumentoNotFound, resolve_archivo_path


def test_resolve_accepts_in_root_file(tmp_path: Path) -> None:
    target = tmp_path / "visor_assets" / "codist"
    target.mkdir(parents=True)
    pdf = target / "p-ach.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")

    resolved = resolve_archivo_path(str(tmp_path), "visor_assets/codist/p-ach.pdf")
    assert resolved == pdf.resolve()


def test_resolve_rejects_dotdot(tmp_path: Path) -> None:
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("nope")
    (tmp_path / "ok").mkdir()
    with pytest.raises(DocumentoNotFound):
        resolve_archivo_path(str(tmp_path), "../secret.txt")


def test_resolve_rejects_absolute(tmp_path: Path) -> None:
    with pytest.raises(DocumentoNotFound):
        resolve_archivo_path(str(tmp_path), "/etc/passwd")


def test_resolve_missing_file(tmp_path: Path) -> None:
    with pytest.raises(DocumentoNotFound):
        resolve_archivo_path(str(tmp_path), "missing.pdf")


def test_resumen_dump_has_no_relative_path() -> None:
    from app.domains.documentos.service import list_resumenes

    payload = list_resumenes().model_dump()
    assert "items" in payload
    for item in payload["items"]:
        assert "relative_path" not in item
        assert "files" not in item
        assert item["clasificacion"] == "privado"
