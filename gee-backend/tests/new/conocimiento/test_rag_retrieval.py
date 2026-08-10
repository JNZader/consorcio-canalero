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
from app.domains.conocimiento.embedding import (
    DEFAULT_MODEL_ID,
    DETERMINISTIC_MODEL_ID,
    EMBEDDING_DIMENSIONS,
    DeterministicEmbedder,
    vector_literal,
)
from app.domains.conocimiento.repository import VectorSupportUnavailable, registrar_procedencia

SHA = "e" * 40


class EmbedderRealSimulado:
    """A stand-in that reports BGE-M3's identity and computes fake numbers.

    BGE-M3 is a 2.2 GB download and its stack is not installable here (slice
    deviation #1), so the only thing a test can honestly exercise about "the real
    embedder" is the part the provenance gate actually compares: `model_id`. The
    arithmetic is delegated to the deterministic fake, and every test that uses
    this double asserts a REFUSAL or an identity — never a retrieval quality,
    which this object has no standing to say anything about.
    """

    model_id = DEFAULT_MODEL_ID
    revision = "c" * 40
    sintetico = False

    def __init__(self) -> None:
        self._fake = DeterministicEmbedder()
        self.dims = self._fake.dims

    def count_tokens(self, texto: str) -> int:
        return self._fake.count_tokens(texto)

    def encode(self, textos):
        return self._fake.encode(textos)


def registrar_modelo(db, *, modelo: str, sintetico: bool) -> None:
    """Stamp the snapshot as if `rag_load_vectors.py` had loaded that model."""
    registrar_procedencia(
        db,
        SHA,
        modelo=modelo,
        revision_hf=None if sintetico else "c" * 40,
        sintetico=sintetico,
        artifact_sha256="9" * 64,
    )
    db.flush()


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


class TestEmbedderProvenanceGate:
    """RAG3-001, in the shape CI runs: does the query embedder match the rows?

    `verificar_embedder` reads `rag_corpus` and nothing else, so the whole
    four-case matrix is exercisable without pgvector — which matters, because the
    scenario it kills (an eval report computed over hash noise) is the reason
    this initiative exists, and leaving it covered only under `make test-rag`
    would leave it uncovered in the shape that actually gates merges.
    """

    def test_synthetic_rows_refuse_a_real_embedder(self, corpus_basico):
        """The fabricated-eval path: real questions, real model, noise vectors."""
        registrar_modelo(corpus_basico, modelo=DETERMINISTIC_MODEL_ID, sintetico=True)

        with pytest.raises(service.EmbedderMismatch) as abort:
            service.verificar_embedder(corpus_basico, SHA, EmbedderRealSimulado())

        mensaje = str(abort.value)
        assert DETERMINISTIC_MODEL_ID in mensaje
        assert DEFAULT_MODEL_ID in mensaje

    def test_synthetic_rows_accept_the_synthetic_embedder(self, corpus_basico):
        """The smoke path stays open: the pipeline must be exercisable end to end."""
        registrar_modelo(corpus_basico, modelo=DETERMINISTIC_MODEL_ID, sintetico=True)
        service.verificar_embedder(corpus_basico, SHA, DeterministicEmbedder())

    def test_real_rows_refuse_the_synthetic_embedder(self, corpus_basico):
        """The mirror image, and the one an asymmetric gate would have missed.

        Querying real BGE-M3 vectors with the hash fake produces a ranked list of
        pure noise with full provenance attached — the same fabricated
        measurement as the first case, with the operands swapped.
        """
        registrar_modelo(corpus_basico, modelo=DEFAULT_MODEL_ID, sintetico=False)

        with pytest.raises(service.EmbedderMismatch):
            service.verificar_embedder(corpus_basico, SHA, DeterministicEmbedder())

    def test_real_rows_accept_the_real_embedder(self, corpus_basico):
        registrar_modelo(corpus_basico, modelo=DEFAULT_MODEL_ID, sintetico=False)
        service.verificar_embedder(corpus_basico, SHA, EmbedderRealSimulado())

    def test_a_never_embedded_snapshot_is_refused_not_silently_empty(self, corpus_basico):
        """Slices 1-2 ship exactly this state, so it is the likeliest of all.

        The vector leg over an unembedded snapshot returns `[]` — indistinguish-
        able from "nothing matched" — and a hybrid run would then publish an FTS
        result under a fused label.
        """
        with pytest.raises(service.EmbeddingsNoCargadas, match="never embedded"):
            service.verificar_embedder(corpus_basico, SHA, DeterministicEmbedder())

    def test_an_unknown_snapshot_is_refused(self, corpus_basico):
        with pytest.raises(service.EmbeddingsNoCargadas, match="not in rag_corpus"):
            service.verificar_embedder(corpus_basico, "0" * 40, DeterministicEmbedder())

    def test_fts_mode_is_unaffected_by_embedding_provenance(self, corpus_basico):
        """The FTS leg never touched a vector and must not start needing one."""
        resultado = service.recuperar(corpus_basico, SHA, "canal", modo="fts")
        assert resultado.hits


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


class TestFtsOperador:
    """RAG4-001: the leg ORs its lexemes, and every shape of that is pinned here.

    `websearch_to_tsquery` builds a CONJUNCTION. Against the real pinned corpus
    that made six of six sampled gold questions return ZERO rows — the `&` sits
    in the WHERE clause, so `ts_rank_cd` never runs and the FTS-only arm of the
    ablation measured the query grammar rather than the index. The leg now
    partitions that parse and ORs the positive terms.

    These tests are the operator's contract. They exist because the transform is
    string surgery on a tsquery, and string surgery that nobody pinned is one
    refactor away from being silently wrong in a way no metric would show.
    """

    def test_a_multi_word_question_no_longer_needs_every_word_present(self, corpus_basico):
        """The whole finding, in one assertion.

        `9750#4` is one sentence about expropiación. The question adds five words
        it does not contain, so under the conjunction the leg returned nothing at
        all — not a low rank, no rows.
        """
        hits = repository.fts_search(
            corpus_basico,
            SHA,
            "¿Quién paga la expropiación de la franja para el canal nuevo?",
        )
        assert {hit.citation_key for hit in hits} >= {"9750#4"}

    def test_the_lexemes_are_not_stemmed_twice(self, corpus_basico):
        """The trap in the obvious implementation, and it is silent.

        Round-tripping the parse through `to_tsquery('spanish', …)` re-applies the
        dictionary to already-stemmed lexemes, and the Snowball stemmer is not
        idempotent: measured against the real corpus, `intervenir` indexes as
        `interven` (13 units) and stems again to `interv` (ZERO). The cast to
        `tsquery` applies no dictionary, so the round trip is exact.

        `mantienen` → `manten` here: a second pass yields `mant`, which matches
        nothing, so this assertion fails under the double-stemming construction
        while every single-word test in this file still passes.
        """
        hits = repository.fts_search(corpus_basico, SHA, "quiénes mantienen el canal")
        assert {hit.citation_key for hit in hits} >= {"9750#3"}

        solo = repository.fts_search(corpus_basico, SHA, "mantienen")
        assert {hit.citation_key for hit in solo} >= {"9750#3"}

    @pytest.mark.parametrize(
        "consulta",
        ["", "   ", "de la y que el", "¿? . , !", "-canal"],
        ids=["vacía", "espacios", "solo-stopwords", "solo-puntuación", "solo-exclusión"],
    )
    def test_a_question_that_reduces_to_nothing_returns_zero_rows_without_raising(
        self, corpus_basico, consulta
    ):
        """Degrade to an empty answer, never to an exception and never to
        everything. `-canal` alone is "everything except canal", which is not a
        retrieval — ORing that in would have returned the whole corpus."""
        assert repository.fts_search(corpus_basico, SHA, consulta) == []

    def test_an_exclusion_still_excludes(self, corpus_basico):
        """`websearch`'s `-palabra` survives the transform.

        ORing the negation in would match every document NOT containing the word
        — a recall explosion wearing the fix's name. The terms are partitioned:
        positives ORed, exclusions kept ANDed.
        """
        con = {h.citation_key for h in repository.fts_search(corpus_basico, SHA, "canal riego")}
        sin = {h.citation_key for h in repository.fts_search(corpus_basico, SHA, "canal -riego")}
        assert "9750#3" in con
        assert "9750#3" not in sin, "the ORed positives swallowed the exclusion"

    @pytest.mark.parametrize(
        "consulta",
        [
            '"zona de camino" canal',
            "e-mail del consorcio",
            "ver http://a.com/x?y&z ahora",
            "canal'); DROP TABLE rag_unidad; --",
            "l'eau del canal",
            "canal \\ riego",
            "canal or riego",
            "canal or riego -lluvia",
            "🚜 canal ñandú",
            "canal " * 200,
        ],
        ids=[
            "frase-entrecomillada",
            "guionado",
            "url",
            "sql-ish",
            "comilla-interna",
            "backslash",
            "operador-or",
            "or-más-exclusión",
            "unicode",
            "muy-larga",
        ],
    )
    def test_the_query_builder_never_raises_on_hostile_input(self, corpus_basico, consulta):
        """The user's text reaches SQL only as the bound parameter of
        `websearch_to_tsquery`, which is total and whose output is a quoted,
        escaped lexeme list. Nothing that comes back out is user text — but the
        transform then edits that output, so every shape it can produce is
        exercised rather than reasoned about.
        """
        hits = repository.fts_search(corpus_basico, SHA, consulta)
        assert isinstance(hits, list)
        # And the table is still there, which is the point of the sql-ish case.
        assert repository.count_unidades(corpus_basico, SHA) == 4

    def test_the_operator_is_named_so_the_report_can_print_it(self):
        assert "OR" in repository.FTS_OPERADOR
        assert "websearch_to_tsquery" in repository.FTS_OPERADOR


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
        # The fixture writes vectors, so it must also record what wrote them —
        # exactly as `rag_load_vectors.py` does inside its load transaction. A
        # fixture that skipped this would be simulating a state the loader can no
        # longer produce (migration conocimiento_004).
        registrar_modelo(pgvector_db, modelo=DETERMINISTIC_MODEL_ID, sintetico=True)
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

    def test_hybrid_refuses_a_mismatched_embedder_end_to_end(self, corpus_embebido):
        """The gate on the real path, not just on the helper.

        `corpus_embebido` holds synthetic vectors, so a query with the real
        model's identity must be refused before either leg runs — including the
        FTS one, which would otherwise hand back a lexical result set for a
        question that asked to be fused.
        """
        with pytest.raises(service.EmbedderMismatch):
            service.recuperar(
                corpus_embebido, SHA, "canal", modo="hybrid", embedder=EmbedderRealSimulado()
            )

    def test_hybrid_runs_when_the_embedder_matches_the_stored_vectors(self, corpus_embebido):
        resultado = service.recuperar(
            corpus_embebido, SHA, "canal", modo="hybrid", embedder=DeterministicEmbedder()
        )
        assert resultado.n_vector > 0

    def test_vector_mode_on_an_unembedded_snapshot_refuses(self, pgvector_db):
        """pgvector present, column present, corpus ingested, no artifact loaded.

        Everything about the DATABASE is fine; it is the snapshot that has no
        vectors. Returning `[]` here would be a retrieval answer to a question
        about capability.
        """
        seed_corpus(pgvector_db, [("ley-9750", "9750#3", CANAL)])

        with pytest.raises(service.EmbeddingsNoCargadas):
            service.recuperar(
                pgvector_db, SHA, "canal", modo="vector", embedder=DeterministicEmbedder()
            )


@pytest.mark.pgvector
class TestVectorLegDepth:
    """RAG3-002: the leg's depth is `LEG_LIMIT`, not whatever the index budgets.

    Measured on this image before the pin was written (1 400 seeded vectors,
    `consorcio-postgres:16-vector`, pgvector 0.8.6):

    * the leg's real query — `ORDER BY embedding <=> $1, citation_key` — plans as
      `Seq Scan` + `top-N heapsort`, 1 400 rows scanned, 50 returned, ~11 ms. The
      HNSW index is not used and cannot be: `citation_key` as a secondary sort
      key is not something an ordered index scan can supply, and even
      `enable_seqscan = off` did not switch it;
    * the same query WITHOUT the tie-break, forced onto the index, returns
      **`rows=40`** at pgvector's default `hnsw.ef_search = 40` and `rows=50`
      once it is raised. That is the truncation this pin exists for, reproduced
      below rather than asserted from the documentation.
    """

    UNIDADES_A_ESCALA = 1400

    @pytest.fixture
    def corpus_a_escala(self, pgvector_db):
        """~1,400 embedded units — the pinned corpus's real order of magnitude."""
        seed_corpus(
            pgvector_db,
            [
                ("ley-9750", f"9750#{i:05d}", f"Artículo {i} sobre el canal y la obra de riego.")
                for i in range(self.UNIDADES_A_ESCALA)
            ],
        )
        # One shared 1023-value tail sent once, plus a per-row leading component,
        # so seeding 1 400 vectors costs one statement and ~7 kB instead of 1 400
        # literals of 1 024 values each.
        (base,) = DeterministicEmbedder().encode(["semilla de escala"])
        cola = ",".join(repr(x) for x in base[1:])
        pgvector_db.execute(
            text(
                "WITH numeradas AS (SELECT citation_key, row_number() OVER "
                "(ORDER BY citation_key) AS n FROM rag_unidad WHERE corpus_sha = :sha) "
                "UPDATE rag_unidad u SET embedding = CAST("
                "'[' || (numeradas.n::float8 / 10000)::text || ',' || :cola || ']' AS vector) "
                "FROM numeradas WHERE u.corpus_sha = :sha "
                "AND u.citation_key = numeradas.citation_key"
            ),
            {"sha": SHA, "cola": cola},
        )
        pgvector_db.flush()
        return pgvector_db

    def test_the_leg_returns_exactly_leg_limit_candidates_at_corpus_scale(self, corpus_a_escala):
        (qvec,) = DeterministicEmbedder().encode(["canal de riego"])

        hits = repository.vector_search(corpus_a_escala, SHA, qvec)

        assert len(hits) == repository.LEG_LIMIT
        assert [hit.rango for hit in hits] == list(range(repository.LEG_LIMIT))

    def test_the_leg_pins_hnsw_ef_search_for_the_transaction(self, corpus_a_escala):
        """The pin itself, asserted where it is observable.

        Without the `set_config` call this reads pgvector's default 40 — below
        `LEG_LIMIT`, and therefore a leg that would be silently 20 % shallower
        than the number the eval report prints the moment the plan changes.
        """
        (qvec,) = DeterministicEmbedder().encode(["canal de riego"])
        repository.vector_search(corpus_a_escala, SHA, qvec)

        pinned = corpus_a_escala.execute(
            text("SELECT current_setting('hnsw.ef_search')")
        ).scalar_one()

        assert int(pinned) == repository.HNSW_EF_SEARCH
        assert repository.HNSW_EF_SEARCH >= repository.LEG_LIMIT

    def test_an_ef_search_below_the_leg_limit_is_refused(self, corpus_a_escala):
        (qvec,) = DeterministicEmbedder().encode(["canal de riego"])

        with pytest.raises(ValueError, match="ef_search"):
            repository.vector_search(corpus_a_escala, SHA, qvec, ef_search=repository.LEG_LIMIT - 1)

    #: pgvector's own default. Written out rather than read from the server so a
    #: silent upstream change to the default is a FAILURE here, not an
    #: automatically-absorbed shift in what the test believes it is proving.
    EF_SEARCH_POR_DEFECTO = 40

    def test_pgvectors_default_ef_search_really_does_truncate_an_index_scan(self, corpus_a_escala):
        """The external contract the pin depends on, pinned by a test.

        This asserts pgvector's behaviour, not ours, on purpose: the pin is only
        worth its round trip if `ef_search` really is a hard candidate ceiling.
        If a future pgvector changes that — or ships `hnsw.iterative_scan` on by
        default — this is where we find out, instead of discovering it as an
        unexplained recall change in an eval report.

        Getting the index scan requires forcing it, and the forcing is itself
        evidence. `enable_seqscan = off` alone is NOT enough: the planner then
        picks a bitmap scan over `ix_rag_unidad_documento` plus a top-N sort and
        still returns all 50. Only with `enable_sort = off` — no sort node
        available, so the ordering must come from the index — does the HNSW scan
        run, and it returns 40. The plan is asserted below rather than assumed,
        because a test that silently measured a sort instead of an index scan
        would "pass" while proving nothing.
        """
        (qvec,) = DeterministicEmbedder().encode(["canal de riego"])
        # Distance-only ORDER BY: the leg's `citation_key` tie-break is precisely
        # what an ordered index scan cannot supply, so reproducing the truncation
        # means asking for the plan the tie-break excludes.
        consulta = text(
            "SELECT citation_key FROM rag_unidad WHERE corpus_sha = :sha "
            "AND embedding IS NOT NULL ORDER BY embedding <=> CAST(:qvec AS vector) "
            "LIMIT :limite"
        )
        params = {"sha": SHA, "qvec": vector_literal(qvec), "limite": repository.LEG_LIMIT}

        corpus_a_escala.execute(text("SET LOCAL enable_seqscan = off"))
        corpus_a_escala.execute(text("SET LOCAL enable_sort = off"))
        try:
            plan = "\n".join(
                fila[0]
                for fila in corpus_a_escala.execute(text("EXPLAIN " + str(consulta)), params).all()
            )
            corpus_a_escala.execute(
                text("SELECT set_config('hnsw.ef_search', :ef, true)"),
                {"ef": str(self.EF_SEARCH_POR_DEFECTO)},
            )
            con_default = corpus_a_escala.execute(consulta, params).all()

            corpus_a_escala.execute(
                text("SELECT set_config('hnsw.ef_search', :ef, true)"),
                {"ef": str(repository.HNSW_EF_SEARCH)},
            )
            con_pin = corpus_a_escala.execute(consulta, params).all()
        finally:
            corpus_a_escala.execute(text("SET LOCAL enable_seqscan = on"))
            corpus_a_escala.execute(text("SET LOCAL enable_sort = on"))

        assert "ix_rag_unidad_embedding_hnsw" in plan, (
            f"this test only means something over an HNSW index scan; got:\n{plan}"
        )
        assert len(con_default) == self.EF_SEARCH_POR_DEFECTO, (
            "pgvector's default ef_search is a hard candidate ceiling, below LEG_LIMIT"
        )
        assert len(con_pin) == repository.LEG_LIMIT, "…and the pin is what lifts it"
