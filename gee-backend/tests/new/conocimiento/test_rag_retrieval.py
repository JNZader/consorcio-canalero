"""Hybrid retrieval: two legs, RRF fusion, full provenance (tasks 3.6-3.8).

Split by what each test actually needs, not by convenience:

* the FTS leg, its tie determinism, the provenance surface and the
  `VectorSupportUnavailable` contract need NO pgvector and run on the default
  vector-less image — which is where CI lives, so they are covered there;
* the vector leg and the fused hybrid path are `pgvector`-marked and run under
  `make test-rag`.

The provenance tests deliberately run in BOTH shapes: in `fts` mode on the
default image (task 3.8 specified `pgvector`; running them unmarked as well is
strictly more coverage) and again through the fused hybrid path, because
assembling a citation correctly from one leg proves nothing about what survives
fusion.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.domains.conocimiento import repository, service
from app.domains.conocimiento.embedding import EMBEDDING_DIMENSIONS, DeterministicEmbedder
from app.domains.conocimiento.repository import VectorSupportUnavailable

SHA = "e" * 40

#: A near-verbatim slice of the collision class the design names: 45 articles of
#: the Anexo of Res. 4/2026 whose entire body is the words "Sin Reglamentar"
#: (`MANIFEST.md:658-660`). Identical text means identical `ts_rank_cd`.
SIN_REGLAMENTAR = "Sin Reglamentar."

DOCUMENTOS = {
    "ley-9750": {
        "tipo": "ley-provincial",
        "es_secundaria": False,
        "jurisdiccion": "provincial",
        "estado_vigencia": "vigente",
        "relevancia_consorcio": None,
        "verificacion": "verificado contra SAIJ",
        "fuente_url": "https://saij.gob.ar/9750",
    },
    "resolucion-4-2026": {
        "tipo": "resolucion-ministerial",
        "es_secundaria": False,
        "jurisdiccion": "provincial",
        "estado_vigencia": "vigente",
        "relevancia_consorcio": (
            "RÉGIMEN HERMANO — CONTEXTO COMPARATIVO, NO DERECHO APLICABLE AL "
            "CONSORCIO CANALERO. NO debe citarse como fundamento de ninguna "
            "obligación ni facultad de un consorcio canalero."
        ),
        "verificacion": "verificado contra BO",
        "fuente_url": "https://bo.cba.gov.ar/res-4-2026",
    },
    "informe-f3": {
        "tipo": "informe-operativo",
        "es_secundaria": True,
        "jurisdiccion": "provincial",
        "estado_vigencia": None,
        "relevancia_consorcio": None,
        "verificacion": None,
        "fuente_url": None,
    },
}


def seed_corpus(db, unidades: list[tuple[str, str, str]]) -> None:
    """`unidades` is `[(documento_id, citation_key, texto)]`."""
    db.execute(
        text(
            "INSERT INTO rag_corpus (corpus_sha, repo_url, manifest_version, "
            "articulos_declarados, activo) VALUES (:sha, 'u', '2', :n, true)"
        ),
        {"sha": SHA, "n": len(unidades)},
    )
    usados = {documento_id for documento_id, _, _ in unidades}
    db.execute(
        text(
            "INSERT INTO rag_documento (corpus_sha, documento_id, tipo, es_secundaria, "
            "jurisdiccion, estado_vigencia, relevancia_consorcio, verificacion, "
            "clasificacion, fuente_url) VALUES (:sha, :documento_id, :tipo, "
            ":es_secundaria, :jurisdiccion, :estado_vigencia, :relevancia_consorcio, "
            ":verificacion, 'privado', :fuente_url)"
        ),
        [
            {"sha": SHA, "documento_id": documento_id, **DOCUMENTOS[documento_id]}
            for documento_id in sorted(usados)
        ],
    )
    db.execute(
        text(
            "INSERT INTO rag_unidad (corpus_sha, citation_key, documento_id, tipo_chunk, "
            "epigrafe, texto, texto_indexado, source_file, source_offset) VALUES "
            "(:sha, :key, :documento_id, 'articulo', :epigrafe, :texto, :texto, 'f.md', 0)"
        ),
        [
            {
                "sha": SHA,
                "key": citation_key,
                "documento_id": documento_id,
                "epigrafe": f"Art. {citation_key}",
                "texto": texto,
            }
            for documento_id, citation_key, texto in unidades
        ],
    )
    db.flush()


CANAL = "Los consorcios canaleros mantienen el canal y la obra de riego."
EXPROPIACION = "La expropiación se rige por la ley de expropiaciones provincial."


@pytest.fixture
def corpus_basico(db):
    seed_corpus(
        db,
        [
            ("ley-9750", "9750#3", CANAL),
            ("ley-9750", "9750#4", EXPROPIACION),
            ("resolucion-4-2026", "res4-2026#anexo#art9", f"{CANAL} Régimen hermano."),
            ("informe-f3", "informe-f3#sec-3", f"{CANAL} Según el informe técnico."),
        ],
    )
    return db


class TestVectorSupportContract:
    """3.7: on a vector-less database the vector leg RAISES. It never degrades."""

    def test_vector_leg_raises_when_unsupported(self, corpus_basico):
        if repository.vector_support(corpus_basico):
            pytest.skip("this database HAS pgvector; the contract under test is its absence")

        with pytest.raises(VectorSupportUnavailable):
            repository.vector_search(corpus_basico, SHA, [0.0] * EMBEDDING_DIMENSIONS)

    def test_hybrid_mode_raises_rather_than_silently_becoming_fts(self, corpus_basico):
        """The failure that would make the whole ablation meaningless.

        A hybrid run that fell back to FTS would report a fused comparison it
        never performed — and the report would look exactly like a real one,
        which is the point of the whole change.
        """
        if repository.vector_support(corpus_basico):
            pytest.skip("this database HAS pgvector; the contract under test is its absence")

        with pytest.raises(VectorSupportUnavailable):
            service.recuperar(
                corpus_basico,
                SHA,
                "canal",
                modo="hybrid",
                embedder=DeterministicEmbedder(),
            )

    def test_fts_mode_still_works_on_a_vector_less_database(self, corpus_basico):
        """The FTS-only leg is what keeps slices 1-2 independently useful."""
        resultado = service.recuperar(corpus_basico, SHA, "canal", modo="fts")
        assert resultado.hits
        assert resultado.n_vector == 0

    def test_vector_mode_without_an_embedder_is_a_usage_error_not_a_fallback(self, corpus_basico):
        with pytest.raises(service.EmbedderRequerido):
            service.recuperar(corpus_basico, SHA, "canal", modo="vector")

    def test_unknown_mode_is_rejected(self, corpus_basico):
        with pytest.raises(ValueError, match="modo"):
            service.recuperar(corpus_basico, SHA, "canal", modo="magia")

    def test_empty_result_is_not_the_same_as_no_support(self, corpus_basico):
        """An FTS query matching nothing returns [], and that is an ANSWER."""
        resultado = service.recuperar(corpus_basico, SHA, "criptomonedas", modo="fts")
        assert resultado.hits == []


class TestFtsLeg:
    def test_fts_leg_finds_the_expected_units(self, corpus_basico):
        hits = repository.fts_search(corpus_basico, SHA, "canal")
        assert {hit.citation_key for hit in hits} >= {"9750#3", "res4-2026#anexo#art9"}
        assert all(hit.rango == i for i, hit in enumerate(hits))

    def test_fts_leg_is_snapshot_scoped(self, corpus_basico):
        assert repository.fts_search(corpus_basico, "f" * 40, "canal") == []

    def test_fts_leg_sorts_ties_by_citation_key_deterministically(self, db):
        """The "Sin Reglamentar" collision class, on the image CI actually runs.

        Six units with byte-identical text tie on `ts_rank_cd`. PostgreSQL leaves
        tied rows unordered, so without the secondary sort an arbitrary order
        decides which of them survives the `LIMIT` — flipping fused ranks and
        therefore gold outcomes between runs over identical data.
        """
        claves = [f"res4-2026#anexo#art{n}" for n in (9, 4, 7, 2, 8, 1)]
        seed_corpus(db, [("resolucion-4-2026", clave, SIN_REGLAMENTAR) for clave in claves])

        corridas = [
            [hit.citation_key for hit in repository.fts_search(db, SHA, "reglamentar", limite=3)]
            for _ in range(5)
        ]

        assert corridas[0] == sorted(claves)[:3]
        assert all(corrida == corridas[0] for corrida in corridas)

    def test_limit_is_honoured(self, corpus_basico):
        assert len(repository.fts_search(corpus_basico, SHA, "canal", limite=1)) == 1


class TestProvenanceOnTheFtsPath:
    """3.8 on the default image — the spec's provenance scenarios, CI-covered."""

    def test_hit_carries_full_provenance(self, corpus_basico):
        resultado = service.recuperar(corpus_basico, SHA, "expropiación", modo="fts")
        hit = next(h for h in resultado.hits if h.citation_key == "9750#4")

        assert hit.texto == EXPROPIACION
        assert hit.tipo == "ley-provincial"
        assert hit.es_secundaria is False
        assert hit.jurisdiccion == "provincial"
        assert hit.estado_vigencia == "vigente"
        assert hit.verificacion == "verificado contra SAIJ"
        assert hit.fuente_url == "https://saij.gob.ar/9750"
        assert hit.relevancia_consorcio is None

    def test_texto_is_the_verbatim_field_not_the_indexed_one(self, db):
        """A citation is `texto`, never `texto_indexado` — enrichment cannot leak."""
        seed_corpus(db, [("ley-9750", "9750#3", CANAL)])
        db.execute(
            text(
                "UPDATE rag_unidad SET texto_indexado = :enriquecido "
                "WHERE corpus_sha = :sha AND citation_key = '9750#3'"
            ),
            {"sha": SHA, "enriquecido": f"TITULO ENRIQUECIDO\n\n{CANAL}"},
        )
        db.flush()

        resultado = service.recuperar(db, SHA, "canal", modo="fts")
        assert resultado.hits[0].texto == CANAL
        assert "ENRIQUECIDO" not in resultado.hits[0].texto

    def test_secundaria_hit_distinguishable_from_norma(self, corpus_basico):
        resultado = service.recuperar(corpus_basico, SHA, "canal", modo="fts", k=10)
        por_clave = {hit.citation_key: hit for hit in resultado.hits}

        assert por_clave["9750#3"].es_secundaria is False
        assert por_clave["informe-f3#sec-3"].es_secundaria is True
        assert por_clave["informe-f3#sec-3"].tipo == "informe-operativo"

    def test_do_not_cite_warning_reaches_consumer_res4_2026(self, corpus_basico):
        """The failure this whole initiative exists to prevent.

        Res. 4/2026 is `tipo: resolucion-ministerial` — derecho aplicable, so
        `es_secundaria` is False, exactly like Ley 9750. `tipo` and
        `es_secundaria` alone rank the two as equivalent grounds. Only
        `relevancia_consorcio` records that this one must NOT be cited as the
        basis of any canalero obligation.
        """
        resultado = service.recuperar(corpus_basico, SHA, "canal", modo="fts", k=10)
        hermano = next(h for h in resultado.hits if h.citation_key == "res4-2026#anexo#art9")

        assert hermano.es_secundaria is False
        assert hermano.tipo == "resolucion-ministerial"
        assert "NO DERECHO APLICABLE AL CONSORCIO CANALERO" in hermano.relevancia_consorcio
        assert "NO debe citarse como fundamento" in hermano.relevancia_consorcio

    def test_relevancia_is_carried_verbatim_never_reduced_to_a_boolean(self, corpus_basico):
        resultado = service.recuperar(corpus_basico, SHA, "canal", modo="fts", k=10)
        hermano = next(h for h in resultado.hits if h.citation_key == "res4-2026#anexo#art9")
        assert (
            hermano.relevancia_consorcio == DOCUMENTOS["resolucion-4-2026"]["relevancia_consorcio"]
        )

    def test_per_leg_scores_are_exposed_for_the_eval(self, corpus_basico):
        """The report has to be able to show what each leg saw (design.md D6)."""
        resultado = service.recuperar(corpus_basico, SHA, "canal", modo="fts")
        hit = resultado.hits[0]

        assert hit.rango_fts == 0
        assert hit.valor_fts is not None and hit.valor_fts > 0
        assert hit.rango_vector is None and hit.distancia_vector is None
        assert hit.score_rrf == pytest.approx(1 / 61, rel=1e-12)

    def test_k_truncates_the_fused_list_not_the_legs(self, corpus_basico):
        resultado = service.recuperar(corpus_basico, SHA, "canal", modo="fts", k=1)
        assert len(resultado.hits) == 1
        assert resultado.n_fts == 3

    def test_same_query_same_state_gives_an_identical_ranked_list(self, corpus_basico):
        corridas = [
            [
                h.citation_key
                for h in service.recuperar(corpus_basico, SHA, "canal", modo="fts").hits
            ]
            for _ in range(5)
        ]
        assert all(corrida == corridas[0] for corrida in corridas)


@pytest.mark.pgvector
class TestVectorAndHybrid:
    """3.6/3.8 under the vector image: both legs, fused, still fully attributed."""

    @pytest.fixture
    def corpus_embebido(self, pgvector_db):
        unidades = [
            ("ley-9750", "9750#3", CANAL),
            ("ley-9750", "9750#4", EXPROPIACION),
            ("resolucion-4-2026", "res4-2026#anexo#art9", f"{CANAL} Régimen hermano."),
            ("informe-f3", "informe-f3#sec-3", f"{CANAL} Según el informe técnico."),
        ]
        seed_corpus(pgvector_db, unidades)

        embedder = DeterministicEmbedder()
        for _, citation_key, texto in unidades:
            (vector,) = embedder.encode([texto])
            pgvector_db.execute(
                text(
                    "UPDATE rag_unidad SET embedding = CAST(:v AS vector) "
                    "WHERE corpus_sha = :sha AND citation_key = :key"
                ),
                {
                    "v": "[" + ",".join(repr(x) for x in vector) + "]",
                    "sha": SHA,
                    "key": citation_key,
                },
            )
        pgvector_db.flush()
        return pgvector_db

    def test_fts_and_vector_legs_sort_deterministically(self, pgvector_db):
        """Repeated identical queries over tied rows return the same leg order.

        Both legs, both tie classes: identical text ties `ts_rank_cd`, and
        identical text also produces IDENTICAL vectors, so the cosine distances
        are bit-equal — the hardest possible tie, and the one the corpus actually
        contains.
        """
        claves = [f"res4-2026#anexo#art{n}" for n in (9, 4, 7, 2, 8, 1)]
        seed_corpus(pgvector_db, [("resolucion-4-2026", k, SIN_REGLAMENTAR) for k in claves])

        embedder = DeterministicEmbedder()
        (vector,) = embedder.encode([SIN_REGLAMENTAR])
        literal = "[" + ",".join(repr(x) for x in vector) + "]"
        pgvector_db.execute(
            text("UPDATE rag_unidad SET embedding = CAST(:v AS vector) WHERE corpus_sha = :sha"),
            {"v": literal, "sha": SHA},
        )
        pgvector_db.flush()

        fts = [
            [
                h.citation_key
                for h in repository.fts_search(pgvector_db, SHA, "reglamentar", limite=3)
            ]
            for _ in range(5)
        ]
        vec = [
            [h.citation_key for h in repository.vector_search(pgvector_db, SHA, vector, limite=3)]
            for _ in range(5)
        ]

        assert fts[0] == sorted(claves)[:3]
        assert vec[0] == sorted(claves)[:3]
        assert all(c == fts[0] for c in fts)
        assert all(c == vec[0] for c in vec)

    def test_hybrid_fuses_both_legs_and_exposes_each(self, corpus_embebido):
        resultado = service.recuperar(
            corpus_embebido, SHA, "canal", modo="hybrid", embedder=DeterministicEmbedder()
        )

        assert resultado.modo == "hybrid"
        assert resultado.n_fts > 0 and resultado.n_vector > 0
        principal = resultado.hits[0]
        assert principal.rango_fts is not None or principal.rango_vector is not None
        # No blended score exists: the fused number is a sum of 1/(k+rank+1).
        assert principal.score_rrf <= 2 / 61 + 1e-12

    def test_hit_carries_full_provenance_through_fusion(self, corpus_embebido):
        resultado = service.recuperar(
            corpus_embebido,
            SHA,
            "canal",
            modo="hybrid",
            k=10,
            embedder=DeterministicEmbedder(),
        )
        por_clave = {hit.citation_key: hit for hit in resultado.hits}

        hermano = por_clave["res4-2026#anexo#art9"]
        assert hermano.es_secundaria is False
        assert "NO debe citarse como fundamento" in hermano.relevancia_consorcio
        assert por_clave["informe-f3#sec-3"].es_secundaria is True
        assert por_clave["9750#3"].estado_vigencia == "vigente"

    def test_vector_mode_ignores_units_without_an_embedding(self, corpus_embebido):
        """Over-ceiling units are FTS-only by design — they must not appear here."""
        corpus_embebido.execute(
            text(
                "UPDATE rag_unidad SET embedding = NULL WHERE corpus_sha = :sha "
                "AND citation_key = '9750#4'"
            ),
            {"sha": SHA},
        )
        corpus_embebido.flush()

        hits = repository.vector_search(
            corpus_embebido, SHA, DeterministicEmbedder().encode([EXPROPIACION])[0]
        )
        assert "9750#4" not in {hit.citation_key for hit in hits}

    def test_over_ceiling_unit_is_still_reachable_by_fts(self, corpus_embebido):
        """…and the whole reason the ceiling does not abort ingestion."""
        corpus_embebido.execute(
            text(
                "UPDATE rag_unidad SET embedding = NULL WHERE corpus_sha = :sha "
                "AND citation_key = '9750#4'"
            ),
            {"sha": SHA},
        )
        corpus_embebido.flush()

        resultado = service.recuperar(corpus_embebido, SHA, "expropiación", modo="fts")
        assert "9750#4" in {hit.citation_key for hit in resultado.hits}

    def test_wrong_dimension_query_vector_is_refused(self, corpus_embebido):
        with pytest.raises(ValueError, match="dimensions"):
            repository.vector_search(corpus_embebido, SHA, [0.0, 1.0])
