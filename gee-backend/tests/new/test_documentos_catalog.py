"""Committed Documentos catalog invariants (CI must not read the private clone)."""

from __future__ import annotations

from collections import Counter

from app.domains.documentos.catalog import (
    DOCUMENTOS,
    get_archivo,
    get_documento,
    list_documentos,
)

EXPECTED_GROUP_COUNTS = {
    "notas": 7,
    "cidi": 6,
    "codist": 5,
    "conflictos": 3,
    "informes": 1,
    "informes-tecnicos": 2,
    "cruces": 1,
}


def test_catalog_has_exactly_25_dossiers_with_expected_groups() -> None:
    assert len(DOCUMENTOS) == 25
    counts = Counter(d.group for d in DOCUMENTOS)
    assert dict(counts) == EXPECTED_GROUP_COUNTS
    assert all(d.clasificacion == "privado" for d in DOCUMENTOS)


def test_relative_paths_are_relative_and_skip_previews() -> None:
    file_ids: set[str] = set()
    for doc in DOCUMENTOS:
        for archivo in doc.files:
            assert not archivo.relative_path.startswith("/")
            assert ".." not in archivo.relative_path.split("/")
            assert "visor_assets/previews/" not in archivo.relative_path
            assert archivo.id.startswith(f"{doc.id}__")
            assert archivo.id not in file_ids
            file_ids.add(archivo.id)


def test_list_and_get_accessors() -> None:
    assert len(list_documentos()) == 25
    assert len(list_documentos(group="codist")) == 5
    assert list_documentos(group="no-such-group") == ()
    doc = get_documento("codist-p-ach")
    assert doc is not None
    assert doc.titulo
    assert get_documento("missing") is None
    assert get_archivo("codist-p-ach", "nope") is None
    if doc.files:
        hit = get_archivo("codist-p-ach", doc.files[0].id)
        assert hit is not None
        assert hit[1].id == doc.files[0].id
