"""Privacy boundary on external services (task 4.10).

O.5 resolved the hosted-embedding baseline to a LOCAL model, so V0 makes zero
external calls. The gate still ships, and not as ceremony: the leg it guards is
the one a V1 will reach for first, and `clasificacion` defaults to `privado` for
every ingested document, so the gate's real job is to make the API baseline
UNREACHABLE until somebody deliberately promotes a document.

Two independent guarantees, tested separately because either alone is one edit
from being bypassed:

* `assert_public_domain` REFUSES (D3: "it raises unless *zero* documents in the
  snapshot have `clasificacion <> 'publico'`") — default-deny, not filter;
* the payload builder's SQL selects `clasificacion = 'publico'` rows only, so
  even a caller that skipped the assert cannot emit private text.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.domains.conocimiento.eval.privacy import (
    CorpusNoPublico,
    assert_public_domain,
    payload_para_servicio_externo,
)

SHA = "c" * 40


def seed(db, clasificaciones: dict[str, str]) -> None:
    db.execute(
        text(
            "INSERT INTO rag_corpus (corpus_sha, repo_url, manifest_version, "
            "articulos_declarados, activo) VALUES (:sha, 'u', '2', 1, true)"
        ),
        {"sha": SHA},
    )
    db.execute(
        text(
            "INSERT INTO rag_documento (corpus_sha, documento_id, tipo, es_secundaria, "
            "jurisdiccion, estado_vigencia, clasificacion) VALUES (:sha, :documento_id, "
            "'ley-provincial', false, 'provincial', 'vigente', :clasificacion)"
        ),
        [
            {"sha": SHA, "documento_id": documento_id, "clasificacion": clasificacion}
            for documento_id, clasificacion in clasificaciones.items()
        ],
    )
    db.execute(
        text(
            "INSERT INTO rag_unidad (corpus_sha, citation_key, documento_id, tipo_chunk, "
            "texto, texto_indexado, source_file, source_offset) VALUES "
            "(:sha, :key, :documento_id, 'articulo', :texto, :texto, 'f.md', 0)"
        ),
        [
            {
                "sha": SHA,
                "key": f"{documento_id}#1",
                "documento_id": documento_id,
                "texto": f"texto de {documento_id}",
            }
            for documento_id in clasificaciones
        ],
    )
    db.flush()


class TestDefaultDeny:
    """4.10: `test_api_baseline_gated_by_assert_public_domain`."""

    def test_api_baseline_gated_by_assert_public_domain(self, db):
        seed(db, {"ley-9750": "publico", "acta-interna": "privado"})
        with pytest.raises(CorpusNoPublico) as excinfo:
            assert_public_domain(db, SHA)
        # The refusal names the offender: an operator who cannot see WHICH
        # document blocked the leg will promote the wrong one.
        assert "acta-interna" in str(excinfo.value)

    def test_an_all_public_snapshot_passes(self, db):
        seed(db, {"ley-9750": "publico", "ley-5589": "publico"})
        assert_public_domain(db, SHA)  # does not raise

    def test_the_real_ingestion_path_is_refused_because_everything_is_privado(self, db):
        """`documento_row_from_frontmatter` writes `clasificacion = 'privado'`
        for every document, with no code path that promotes one. So the API
        baseline is unreachable by construction today, and this test is what
        turns that from a claim into a check."""
        seed(db, {"ley-9750": "privado", "ley-5589": "privado"})
        with pytest.raises(CorpusNoPublico):
            assert_public_domain(db, SHA)

    def test_an_unknown_snapshot_is_refused_rather_than_read_as_empty(self, db):
        """Zero private documents is trivially true of a snapshot that does not
        exist. Default-deny has to mean deny, not "nothing to object to"."""
        with pytest.raises(CorpusNoPublico):
            assert_public_domain(db, "f" * 40)


class TestPayload:
    """4.10: `test_private_document_excluded_from_external_payload`."""

    def test_private_document_excluded_from_external_payload(self, db):
        seed(db, {"ley-9750": "publico", "acta-interna": "privado"})
        with pytest.raises(CorpusNoPublico):
            payload_para_servicio_externo(db, SHA)

    def test_the_payload_query_itself_cannot_emit_private_text(self, db):
        """The second, independent guarantee: even with the assert bypassed, the
        SQL never selects a non-public row."""
        seed(db, {"ley-9750": "publico", "acta-interna": "privado"})
        payload = payload_para_servicio_externo(db, SHA, _saltear_gate_solo_para_test=True)
        claves = {clave for clave, _ in payload}
        assert claves == {"ley-9750#1"}
        assert all("acta-interna" not in texto for _, texto in payload)

    def test_payload_is_ordered_for_reproducibility(self, db):
        seed(db, {"b-ley": "publico", "a-ley": "publico"})
        payload = payload_para_servicio_externo(db, SHA)
        assert [clave for clave, _ in payload] == ["a-ley#1", "b-ley#1"]
