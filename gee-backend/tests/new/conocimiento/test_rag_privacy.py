"""Privacy boundary on external services (task 4.10).

O.5 resolved the hosted-embedding baseline to a LOCAL model, so V0 makes zero
external calls. The gate still ships, and not as ceremony: the leg it guards is
the one a V1 will reach for first.

Two independent guarantees, tested separately because either alone is one edit
from being bypassed:

* `assert_public_domain` REFUSES (D3: "it raises unless *zero* documents in the
  snapshot have `clasificacion <> 'publico'`") — default-deny, not filter;
* the payload builder's SQL selects `clasificacion = 'publico'` rows only, so
  even a caller that skipped the assert cannot emit private text.

Since the three-class rule (U1), this file covers TWO gates with deliberately
different sets, and the difference is the thing most likely to be "tidied up" by
a future reader:

* `assert_public_domain` — eval BASELINE, whole-snapshot refusal, `publico` only;
* `assert_unidades_publicas` — SERVING, per-unit exclusion, admits
  `CLASIFICACIONES_ENVIABLES = {publico, institucional}`.

Two questions, two sets, one place each. Neither replaces the other.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.domains.conocimiento.eval.privacy import (
    CLASIFICACION_PUBLICA,
    CorpusNoPublico,
    assert_public_domain,
    payload_para_servicio_externo,
)
from app.domains.conocimiento.repository import CLASIFICACIONES_ENVIABLES
from app.domains.conocimiento.service import assert_unidades_publicas

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

    def test_an_all_privado_snapshot_is_refused(self, db):
        """Docstring rewritten (task 1.10), the assertion untouched.

        It used to claim that `documento_row_from_frontmatter` writes `privado`
        for every document "with no code path that promotes one". The three-class
        rule promotes documents now, so that claim is false — but the test never
        exercised the ingestion path at all: it seeds its own rows. What it
        actually proves, and still proves, is narrower and true: an all-`privado`
        snapshot is refused for the WHOLE snapshot.
        """
        seed(db, {"ley-9750": "privado", "ley-5589": "privado"})
        with pytest.raises(CorpusNoPublico):
            assert_public_domain(db, SHA)

    def test_an_institucional_snapshot_is_also_refused(self, db):
        """1.10's missing sibling: the two gates do NOT share a set, deliberately.

        `assert_unidades_publicas` (the SERVING gate) admits
        `{publico, institucional}`. `assert_public_domain` (the eval BASELINE
        gate) stays `publico`-only, because the optional API-embedding comparison
        baseline is bounded to the public-domain corpus text and an
        `institucional` document is a consorcio instrument the owner cleared for
        the ANSWER path, not for a corpus-wide comparison against a third-party
        embedding service.

        Consequence, stated rather than discovered later: with the consorcio's
        own registro in the corpus, the API baseline stays unreachable in
        practice. That is the correct outcome, not a bug to fix.
        """
        seed(db, {"ley-9750": "publico", "consorcio-10-de-mayo": "institucional"})
        with pytest.raises(CorpusNoPublico) as excinfo:
            assert_public_domain(db, SHA)
        assert "consorcio-10-de-mayo" in str(excinfo.value)
        assert "institucional" in str(excinfo.value)

    def test_the_baseline_payload_sql_also_excludes_institucional(self, db):
        """The second, independent guarantee holds for the new class too.

        A gate that refuses `institucional` while the query beneath it would have
        selected it is one forgotten `assert` away from shipping the consorcio's
        own instruments to an embedding service.
        """
        seed(db, {"ley-9750": "publico", "consorcio-10-de-mayo": "institucional"})
        payload = payload_para_servicio_externo(db, SHA, _saltear_gate_solo_para_test=True)
        assert {clave for clave, _ in payload} == {"ley-9750#1"}

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


class TestGateDeServicioPorPedido:
    """1.9: `assert_unidades_publicas` — the PER-REQUEST gate, and its semantics.

    Deliberately NOT `assert_public_domain`'s semantics. That one refuses the
    whole snapshot, and its docstring explains why that is right for a baseline:
    a baseline computed over a filtered corpus is compared against a corpus it
    was not computed over. A served answer has no such symmetry requirement — it
    is grounded in whatever units it actually cites — so per-unit exclusion is
    correct here and snapshot-refusal is not. Both live side by side; neither
    replaces the other.
    """

    def test_it_returns_the_shippable_subset_and_never_raises(self, db):
        seed(db, {"ley-9750": "publico", "acta-interna": "privado"})
        enviables = assert_unidades_publicas(
            db, SHA, ["ley-9750#1", "acta-interna#1"]
        )
        assert enviables == frozenset({"ley-9750#1"})

    def test_an_institucional_unit_is_ADMITTED(self, db):
        """The whole point of the widening: gold items C-1 and C-8 cite units of
        the consorcio's own registro. Under a `publico`-only serving gate they
        were unanswerable by construction."""
        seed(db, {"consorcio-10-de-mayo": "institucional"})
        enviables = assert_unidades_publicas(db, SHA, ["consorcio-10-de-mayo#1"])
        assert enviables == frozenset({"consorcio-10-de-mayo#1"})

    def test_everything_non_shippable_yields_an_empty_set_not_an_exception(self, db):
        """Empty means abstención upstream — a decision the caller makes, not an
        exception the gate throws. A gate that raises here would turn a perfectly
        ordinary "no public grounding for this question" into a 500."""
        seed(db, {"acta-interna": "privado"})
        assert assert_unidades_publicas(db, SHA, ["acta-interna#1"]) == frozenset()

    def test_an_unknown_key_is_excluded_rather_than_assumed_shippable(self, db):
        """Default-deny survives the change of shape: a key with no row joins to
        nothing and is therefore not in the shippable subset."""
        seed(db, {"ley-9750": "publico"})
        enviables = assert_unidades_publicas(db, SHA, ["ley-9750#1", "no-existe#9"])
        assert enviables == frozenset({"ley-9750#1"})

    def test_it_is_snapshot_scoped(self, db):
        """A key that is shippable in another snapshot is not shippable here."""
        seed(db, {"ley-9750": "publico"})
        assert assert_unidades_publicas(db, "d" * 40, ["ley-9750#1"]) == frozenset()

    def test_no_keys_requested_is_an_empty_subset_not_the_whole_corpus(self, db):
        seed(db, {"ley-9750": "publico"})
        assert assert_unidades_publicas(db, SHA, []) == frozenset()

    def test_the_two_gates_do_not_share_a_set(self, db):
        """The asymmetry asserted head-on, in one test, so it cannot be
        "simplified" into a shared constant by a future reader who assumes the
        difference is an oversight."""
        seed(db, {"consorcio-10-de-mayo": "institucional"})
        assert assert_unidades_publicas(db, SHA, ["consorcio-10-de-mayo#1"])
        with pytest.raises(CorpusNoPublico):
            assert_public_domain(db, SHA)
        assert CLASIFICACION_PUBLICA == "publico"
        assert CLASIFICACIONES_ENVIABLES == frozenset({"publico", "institucional"})
        assert frozenset({CLASIFICACION_PUBLICA}) < CLASIFICACIONES_ENVIABLES
