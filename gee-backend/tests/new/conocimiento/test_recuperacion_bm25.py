"""The ratified B50 retrieval path: real BM25 candidates + cross-encoder ranking.

Every assertion here traces to a MEASURED finding of the campaign
(`docs/rag/candidate-recall-campaign-2026-08-23.md`,
`docs/rag/reranker-experiment-2026-08-23.md`) rather than to taste, because the
whole point of this unit is that the architecture stopped being a preference on
2026-08-23 and became a measurement:

* BM25 with IDF, not `ts_rank_cd` — 0.759 against 0.655 hit@5;
* norma-only candidates — with fuentes secundarias in the pool the reranker's
  norma-vs-secundaria separation collapses to 0.483;
* the cross-encoder score alone orders the page — every measured blend was worse,
  monotonically in the blend weight;
* no per-document cap — it buys 0.793 hit@5 and pays with vigencia-correctness
  0.333, which is the one bar that cannot be traded.

The real reranker is a 2.2 GB model that needs a GPU (measured CPU: 98.9 s per
query at depth 50), so the ranking CONTRACT is exercised with explicit fakes. A
fake can prove ordering, exclusion, pool composition and determinism; it can
prove nothing about retrieval quality, and no test here pretends otherwise —
quality is the eval harness's job on the GPU box.
"""

from __future__ import annotations

import datetime as dt
import inspect
import json

import pytest
from sqlalchemy import event, text

from app.domains.conocimiento import service
from app.domains.conocimiento.eval import harness, metrics
from app.domains.conocimiento.eval.metrics import HitEvaluado, PreguntaEvaluada
from app.domains.conocimiento.eval.report import (
    EvalSinteticoNoEsEval,
    escribir_reporte,
    nombre_de_archivo,
    renderizar_markdown,
)
from app.domains.conocimiento.recuperacion import bm25 as modulo_bm25
from app.domains.conocimiento.recuperacion import reranker as modulo_reranker
from app.domains.conocimiento.recuperacion.bm25 import (
    BM25_B,
    BM25_K1,
    PESO_A,
    PROFUNDIDAD_CANDIDATOS,
    IndiceVacio,
    construir_indice,
    lexemas_de_consulta,
    limpiar_cache_indices,
    obtener_indice,
    parse_tsv,
)
from app.domains.conocimiento.recuperacion.reranker import (
    Candidato,
    RerankerDeterministico,
    RerankerNoDisponible,
    ordenar_por_ce,
)
from app.domains.conocimiento.schemas import ResultadoRecuperacion

SHA = "b" * 40

#: Time is an argument to the report, never read from a clock (`report.py` point 3).
MOMENTO = dt.datetime(2026, 8, 23, 16, 30, tzinfo=dt.timezone.utc)

#: `(tipo, es_secundaria)` per seeded document. Only the two shapes this unit
#: cares about: a norm and a fuente secundaria.
DOCUMENTOS = {
    "ley-9750": ("ley-provincial", False),
    "ley-8548": ("ley-provincial", False),
    "informe-f3": ("informe-operativo", True),
}


@pytest.fixture(autouse=True)
def indice_limpio():
    """The index cache is process-wide; a test must never inherit another's."""
    limpiar_cache_indices()
    yield
    limpiar_cache_indices()


def seed(db, unidades: list[tuple[str, str, str]], *, epigrafes: dict[str, str] | None = None):
    """`unidades` is `[(documento_id, citation_key, texto_indexado)]`."""
    epigrafes = epigrafes or {}
    db.execute(
        text(
            "INSERT INTO rag_corpus (corpus_sha, repo_url, manifest_version, "
            "articulos_declarados, activo) VALUES (:sha, 'u', '2', :n, true)"
        ),
        {"sha": SHA, "n": len(unidades)},
    )
    usados = sorted({documento_id for documento_id, _, _ in unidades})
    db.execute(
        text(
            "INSERT INTO rag_documento (corpus_sha, documento_id, tipo, es_secundaria, "
            "jurisdiccion, estado_vigencia, clasificacion) VALUES (:sha, :documento_id, "
            ":tipo, :es_secundaria, 'provincial', 'vigente', 'publico')"
        ),
        [
            {
                "sha": SHA,
                "documento_id": documento_id,
                "tipo": DOCUMENTOS[documento_id][0],
                "es_secundaria": DOCUMENTOS[documento_id][1],
            }
            for documento_id in usados
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
                "epigrafe": epigrafes.get(citation_key),
                "texto": texto,
            }
            for documento_id, citation_key, texto in unidades
        ],
    )
    db.flush()
    return db


class RerankerFijo:
    """A ranker whose score for each unit is stated by the test, not computed.

    Every ordering assertion below needs the CE score to be a known quantity that
    DISAGREES with the lexical order — that disagreement is exactly what proves
    the lexical order did not survive into the ranking.
    """

    model_id = "fijo-de-prueba"
    revision = None
    sintetico = True

    def __init__(self, por_texto: dict[str, float], defecto: float = 0.0) -> None:
        self.por_texto = por_texto
        self.defecto = defecto
        self.llamadas: list[tuple[str, tuple[str, ...]]] = []

    def puntuar(self, pregunta, textos):
        self.llamadas.append((pregunta, tuple(textos)))
        return [self.por_texto.get(texto, self.defecto) for texto in textos]


class TestBM25EsBM25:
    """2.1 — textbook BM25 with IDF present, and `ts_rank_cd` is NOT the scorer."""

    def test_los_parametros_son_los_medidos(self):
        assert (BM25_K1, BM25_B) == (1.2, 0.75)
        assert PROFUNDIDAD_CANDIDATOS == 50

    def test_el_modulo_no_usa_ts_rank_cd(self):
        """The measured alternative, refused in code and not only in prose.

        `ts_rank_cd` has no IDF term at all: it scores term density inside a
        document and is blind to how rare the term is across the corpus. It cost
        0.104 hit@5 against BM25 on the same pool, the same reranker and the same
        gold set — three gold questions
        (`docs/rag/candidate-recall-campaign-2026-08-23.md:374-390`).
        """
        fuente = inspect.getsource(modulo_bm25)
        codigo = "\n".join(
            linea for linea in fuente.splitlines() if not linea.strip().startswith("#")
        )
        # The docstring names it (that is the point of the docstring); no
        # executable line may call it.
        cuerpo = codigo.split('"""')
        ejecutable = "".join(cuerpo[::2])
        assert "ts_rank_cd" not in ejecutable

    def test_idf_esta_presente_un_termino_raro_gana(self, db):
        """The signal `ts_rank_cd` does not have, isolated so a mutant dies on it.

        The corpus is built so that IDF is the ONLY thing that can decide the
        order. Every unit matches exactly one query term, once, and every unit has
        the same length — so term frequency and length normalisation are constant
        across the whole pool and contribute nothing. `canal` is in six of seven
        units, `expropiación` in one. Strip the IDF factor and every score becomes
        identical, the tie breaks on `citation_key`, and `8548#1` tops the pool.

        This shape matters: the obvious version of this test ("a unit matching two
        terms beats a unit repeating one") passes with the IDF factor deleted,
        because summing two saturated terms already beats one. It would have
        asserted nothing.
        """
        seed(
            db,
            [("ley-8548", f"8548#{i}", "canal de riego") for i in range(1, 6)]
            + [
                ("ley-9750", "9750#1", "canal de riego"),
                ("ley-9750", "9750#2", "expropiación de riego"),
            ],
        )
        indice = construir_indice(db, SHA)
        hits = indice.buscar(lexemas_de_consulta(db, "canal expropiación"))

        assert hits[0].citation_key == "9750#2"
        # And decisively, not by a rounding margin: the rare term's IDF is an
        # order of magnitude above the near-ubiquitous one's.
        assert hits[0].valor > 5 * hits[1].valor
        assert len({round(hit.valor, 9) for hit in hits[1:]}) == 1

    def test_un_lexema_ausente_del_corpus_no_aporta_nada(self, db):
        """No IDF for an unseen term — not an infinite one, and not a crash."""
        seed(db, [("ley-9750", "9750#1", "canal de riego")])
        indice = construir_indice(db, SHA)

        assert indice.buscar(lexemas_de_consulta(db, "helicóptero")) == []
        assert indice.buscar(lexemas_de_consulta(db, "canal helicóptero"))[0].citation_key == (
            "9750#1"
        )

    def test_el_peso_A_del_epigrafe_se_conserva(self):
        """The generated `tsv` weights the epígrafe 'A'; BM25 must see that.

        Discarding the weight would silently change the measured configuration:
        a lexeme in an article's epigraph is worth `PESO_A` occurrences, which is
        how "Art. 5 — Expropiación" outranks a body that mentions it in passing.
        """
        assert PESO_A == 2.0
        tf = parse_tsv("'canal':1A,3B 'riego':7")
        assert tf["canal"] == PESO_A + 1.0
        assert tf["riego"] == 1.0

    def test_una_comilla_en_el_lexema_se_lee_entera(self):
        """`tsvector` doubles an embedded quote; a naive split would truncate it."""
        assert parse_tsv("'o''hara':4") == {"o'hara": 1.0}


class TestConstruccionDelIndice:
    """2.2 — one index per snapshot, query stemming stays in Postgres, top-50."""

    def test_el_indice_se_construye_una_vez_por_corpus_sha(self, db):
        seed(db, [("ley-9750", "9750#1", "canal de riego")])

        primero = obtener_indice(db, SHA)
        sentencias: list[str] = []

        def espia(conn, cursor, statement, parameters, context, executemany):
            sentencias.append(statement)

        event.listen(db.get_bind(), "before_cursor_execute", espia)
        try:
            segundo = obtener_indice(db, SHA)
        finally:
            event.remove(db.get_bind(), "before_cursor_execute", espia)

        assert segundo is primero
        assert sentencias == [], "a cached index must not re-read the snapshot"

    def test_refrescar_reconstruye(self, db):
        seed(db, [("ley-9750", "9750#1", "canal de riego")])
        primero = obtener_indice(db, SHA)
        assert obtener_indice(db, SHA, refrescar=True) is not primero

    def test_el_stemming_de_la_consulta_ocurre_en_postgres(self, db):
        """One analyzer for both sides, which is what stops silent drift.

        A Python stemmer here would be a SECOND analyzer. The measured failure
        mode is not hypothetical: `intervenir` indexes as `interven`, and a
        double-stemmed `interv` matches zero of the units that carry it, with no
        error anywhere.
        """
        seed(db, [("ley-9750", "9750#1", "los canales de riego provinciales")])
        indice = construir_indice(db, SHA)

        # Plural, accented, inflected: the Spanish dictionary reduces all three
        # to lexemes the column already holds.
        assert indice.buscar(lexemas_de_consulta(db, "canales"))[0].citation_key == "9750#1"
        assert lexemas_de_consulta(db, "canales").keys() == {"canal"}

    def test_la_profundidad_por_defecto_es_cincuenta(self, db):
        seed(db, [("ley-9750", f"9750#{i}", "canal de riego") for i in range(60)])
        indice = construir_indice(db, SHA)

        assert len(indice.buscar(lexemas_de_consulta(db, "canal"))) == PROFUNDIDAD_CANDIDATOS
        assert len(indice.buscar(lexemas_de_consulta(db, "canal"), limite=10)) == 10

    def test_los_empates_se_rompen_por_citation_key(self, db):
        """45 articles of this corpus read exactly "Sin Reglamentar"."""
        seed(db, [("ley-9750", f"9750#{i:02d}", "Sin Reglamentar.") for i in range(5)])
        indice = construir_indice(db, SHA)
        hits = indice.buscar(lexemas_de_consulta(db, "reglamentar"))

        assert [hit.citation_key for hit in hits] == sorted(hit.citation_key for hit in hits)

    def test_un_snapshot_sin_normas_es_una_negativa_no_un_indice_vacio(self, db):
        seed(db, [("informe-f3", "informe-f3#sec-1", "canal de riego")])
        with pytest.raises(IndiceVacio):
            construir_indice(db, SHA)


class TestFiltroSecundariaEsPortante:
    """2.3 — no fuente secundaria may enter the candidate pool. Ever."""

    @pytest.fixture
    def corpus_mixto(self, db):
        # The secundaria unit is deliberately the BEST lexical match: it repeats
        # every query term. If the filter were advisory it would top the pool.
        return seed(
            db,
            [
                ("informe-f3", "informe-f3#sec-3", "canal expropiación canal expropiación"),
                ("ley-9750", "9750#1", "canal de riego"),
                ("ley-9750", "9750#2", "expropiación de la traza"),
            ],
        )

    def test_el_indice_no_contiene_ninguna_unidad_secundaria(self, corpus_mixto):
        indice = construir_indice(corpus_mixto, SHA)
        assert set(indice.claves) == {"9750#1", "9750#2"}

    def test_la_secundaria_no_entra_al_pool_aunque_sea_el_mejor_match_lexico(self, corpus_mixto):
        """Without this filter the reranker's norma-vs-secundaria collapses to 0.483.

        That number is what a consultant's report being served as if it were the
        law looks like from the outside, and it is the exact failure this corpus
        exists to prevent.
        """
        indice = construir_indice(corpus_mixto, SHA)
        hits = indice.buscar(lexemas_de_consulta(corpus_mixto, "canal expropiación"), limite=50)

        assert [hit.citation_key for hit in hits]
        assert all(not hit.citation_key.startswith("informe-f3") for hit in hits)

    def test_tampoco_llega_por_la_via_del_servicio(self, corpus_mixto):
        resultado = service.recuperar(
            corpus_mixto,
            SHA,
            "canal expropiación",
            modo="bm25_ce",
            reranker=RerankerDeterministico(),
        )
        assert resultado.hits
        assert all(hit.documento_id != "informe-f3" for hit in resultado.hits)
        assert all(hit.es_secundaria is False for hit in resultado.hits)


class TestElOrdenEsDelCrossEncoderSolo:
    """2.4 + 2.5 — the CE score orders the page; nothing lexical, and no cap."""

    def test_el_orden_final_contradice_al_orden_lexico(self, db):
        """The load-bearing disagreement.

        BM25 puts `9750#1` first; the ranker scores it last. If any lexical term
        survived into the ranking score — RRF over the two orders, or a
        multiplicative blend — `9750#1` would be pulled back up. Both were
        measured and both were worse: RRF −0.035/−0.069, CE×lexical
        −0.104/−0.207, monotone in the blend weight (`design.md:1136-1138`).
        """
        seed(
            db,
            [
                ("ley-9750", "9750#1", "canal canal canal"),
                ("ley-9750", "9750#2", "canal de riego"),
                ("ley-8548", "8548#1", "canal accesorio"),
            ],
        )
        indice = construir_indice(db, SHA)
        lexico = [hit.citation_key for hit in indice.buscar(lexemas_de_consulta(db, "canal"))]
        assert lexico[0] == "9750#1"

        reranker = RerankerFijo(
            {"canal canal canal": 0.1, "canal de riego": 0.9, "canal accesorio": 0.5}
        )
        resultado = service.recuperar(db, SHA, "canal", modo="bm25_ce", reranker=reranker)

        assert [hit.citation_key for hit in resultado.hits] == ["9750#2", "8548#1", "9750#1"]
        assert [hit.score_ce for hit in resultado.hits] == [0.9, 0.5, 0.1]

    def test_el_score_publicado_es_el_logit_crudo_sin_mezcla(self, db):
        seed(db, [("ley-9750", "9750#1", "canal de riego")])
        reranker = RerankerFijo({"canal de riego": -3.25})
        resultado = service.recuperar(db, SHA, "canal", modo="bm25_ce", reranker=reranker)

        hit = resultado.hits[0]
        assert hit.score_ce == -3.25
        assert hit.score_rrf is None, "bm25_ce fuses nothing; an RRF number would be fiction"
        # The lexical evidence is carried for disclosure and is NOT the order.
        assert hit.rango_bm25 == 0
        assert hit.valor_bm25 is not None and hit.valor_bm25 > 0

    def test_no_hay_tope_por_documento(self, db):
        """The cap is REJECTED, and the test states what it cost.

        Capping a document's contribution lifts hit@5 to 0.793 — the best number
        of the whole campaign — and collapses vigencia-correctness from 1.00 to
        0.333 (`design.md:1138-1139`): it evicts the article that says the norm
        is derogated. Six units of ONE document score highest here, and all six
        must be served.
        """
        seed(
            db,
            [("ley-9750", f"9750#{i}", f"canal articulo {i}") for i in range(6)]
            + [("ley-8548", "8548#1", "canal ajeno")],
        )
        reranker = RerankerFijo(
            {f"canal articulo {i}": 1.0 + i for i in range(6)} | {"canal ajeno": 0.0}
        )
        resultado = service.recuperar(db, SHA, "canal", modo="bm25_ce", k=6, reranker=reranker)

        assert [hit.documento_id for hit in resultado.hits] == ["ley-9750"] * 6

    def test_los_empates_del_ce_se_rompen_por_citation_key(self):
        pares = ordenar_por_ce(
            RerankerFijo({}, defecto=1.0),
            "canal",
            [Candidato("z#1", "a"), Candidato("a#1", "b"), Candidato("m#1", "c")],
        )
        assert [clave for clave, _ in pares] == ["a#1", "m#1", "z#1"]

    def test_un_ranking_parcial_es_una_negativa(self):
        class Tacaño:
            model_id = "tacaño"
            revision = None
            sintetico = True

            def puntuar(self, pregunta, textos):
                return [1.0]

        with pytest.raises(RerankerNoDisponible):
            ordenar_por_ce(Tacaño(), "canal", [Candidato("a#1", "a"), Candidato("b#1", "b")])

    def test_se_puntua_el_texto_indexado_no_el_verbatim(self, db):
        """What the campaign scored, and therefore what must be scored.

        `texto_indexado` carries the epigraph and the structural path — the
        fields that say WHICH article this is. Ranking the verbatim `texto`
        instead would hide that from the cross-encoder.
        """
        seed(db, [("ley-9750", "9750#1", "canal de riego")])
        reranker = RerankerFijo({"canal de riego": 1.0})
        service.recuperar(db, SHA, "canal", modo="bm25_ce", reranker=reranker)

        assert reranker.llamadas == [("canal", ("canal de riego",))]

    def test_el_port_real_esta_fijado_a_un_modelo_y_una_revision(self):
        assert modulo_reranker.MODELO_RERANKER == "BAAI/bge-reranker-v2-m3"
        assert len(modulo_reranker.REVISION_RERANKER) == 40
        assert modulo_reranker.MAX_LENGTH == 1024


class TestModoBm25CeEnElServicio:
    """2.6 — wired into `service.recuperar`; the legacy fused path is untouched."""

    @pytest.fixture
    def corpus(self, db):
        return seed(
            db,
            [
                ("ley-9750", "9750#1", "canal de riego"),
                ("ley-9750", "9750#2", "expropiación de la traza"),
            ],
        )

    def test_el_modo_esta_declarado(self):
        assert "bm25_ce" in service.MODOS
        assert set(service.MODOS_RRF) == {"fts", "vector", "hybrid"}

    def test_sin_reranker_es_una_negativa_no_el_orden_bm25(self, corpus):
        """BM25 alone is candidate generation; it was never measured as ranking."""
        with pytest.raises(service.RerankerRequerido):
            service.recuperar(corpus, SHA, "canal", modo="bm25_ce")

    def test_el_resultado_declara_quien_rankeo(self, corpus):
        resultado = service.recuperar(
            corpus, SHA, "canal", modo="bm25_ce", reranker=RerankerDeterministico()
        )
        assert isinstance(resultado, ResultadoRecuperacion)
        assert resultado.modo == "bm25_ce"
        assert resultado.reranker_modelo == "deterministico"
        assert resultado.reranker_sintetico is True
        assert resultado.n_bm25 >= len(resultado.hits)

    def test_el_hit_llega_con_toda_su_procedencia(self, corpus):
        resultado = service.recuperar(
            corpus, SHA, "canal", modo="bm25_ce", reranker=RerankerFijo({"canal de riego": 1.0})
        )
        hit = resultado.hits[0]
        assert hit.citation_key == "9750#1"
        assert (hit.tipo, hit.es_secundaria, hit.jurisdiccion) == (
            "ley-provincial",
            False,
            "provincial",
        )
        assert hit.estado_vigencia == "vigente"
        assert hit.texto == "canal de riego"

    def test_la_via_fusionada_sigue_viva(self, corpus):
        """The V0 ablation is the baseline B50 is quoted against; it must still run."""
        resultado = service.recuperar(corpus, SHA, "canal", modo="fts")
        assert resultado.hits
        assert resultado.hits[0].score_rrf is not None
        assert resultado.hits[0].score_ce is None

    def test_un_modo_desconocido_sigue_siendo_un_error(self, corpus):
        with pytest.raises(ValueError):
            service.recuperar(corpus, SHA, "canal", modo="bm25")


class TestCeroLecturasVectoriales:
    """2.7 — in `bm25_ce` the stored vector column is never read. Spied, not assumed."""

    def test_ninguna_sentencia_toca_la_columna_embedding(self, db):
        """The vector leg is out of candidate generation, and this proves it.

        The persisted BGE-M3 vectors, the pgvector column and index,
        `rag_load_vectors.py` and runbook step 9 are all KEPT — the amendment
        removed the vector leg from candidate generation, not the artifacts
        (`design.md:1129-1131`). Post-amendment no serving consumer of the stored
        corpus vectors remains: the router's query-side centroid (G1) is computed
        by the sidecar and reads no stored column. They stay for eval re-runs and
        future re-measurement. This test is what keeps that claim literal instead
        of aspirational.
        """
        seed(db, [("ley-9750", "9750#1", "canal de riego")])
        sentencias: list[str] = []

        def espia(conn, cursor, statement, parameters, context, executemany):
            sentencias.append(statement)

        event.listen(db.get_bind(), "before_cursor_execute", espia)
        try:
            service.recuperar(db, SHA, "canal", modo="bm25_ce", reranker=RerankerDeterministico())
        finally:
            event.remove(db.get_bind(), "before_cursor_execute", espia)

        assert sentencias, "the spy attached to nothing; the assertion below is vacuous"
        culpables = [s for s in sentencias if "embedding" in s.lower() or "<=>" in s]
        assert culpables == []

    def test_tampoco_exige_un_embedder(self, db):
        """No embedder, no pgvector, no provenance row — and it still answers.

        `bm25_ce` runs on the CI-safe, vector-less image. If it needed any of the
        vector apparatus, this test would fail on exactly the database the
        deployment box has.
        """
        seed(db, [("ley-9750", "9750#1", "canal de riego")])
        resultado = service.recuperar(
            db, SHA, "canal", modo="bm25_ce", reranker=RerankerDeterministico()
        )
        assert resultado.hits


class TestBarrasReRatificadas:
    """2.8 — the report scores the re-ratified bars, and no other."""

    def test_las_constantes_son_las_ratificadas(self):
        assert harness.BARRA_HIT_RATE == 0.72
        assert harness.BARRA_HIT_RATE_10 == 0.80
        assert harness.BARRA_MRR == 0.55
        assert harness.BARRA_CITATION_PRECISION == 0.33
        # The two that did NOT move, and must not.
        assert harness.BARRA_SEPARACION == 1.0
        assert harness.BARRA_VIGENCIA == 1.0

    def test_hit_rate_at_10_se_calcula_y_se_publica(self):
        pregunta = PreguntaEvaluada(
            id="X-1",
            clase="normativa",
            citas_esperadas=("9750#9",),
            citas_vigencia=(),
            hits=tuple(
                HitEvaluado(
                    citation_key=f"9750#{i}", es_secundaria=False, estado_vigencia="vigente"
                )
                for i in range(1, 11)
            ),
        )
        m = metrics.metricas_recuperacion([pregunta])

        assert m.hit_rate_at_5 == 0.0
        assert m.hit_rate_at_10 == 1.0

    def test_citation_precision_es_un_piso_no_una_igualdad(self):
        """1.00 is unreachable by construction on this gold set.

        Several gold items expect two citations where the corpus offers a third,
        equally correct one. A bar nothing can clear does not protect quality; it
        guarantees a NO-GO that gets waived, which is worse than a lower bar that
        is honoured.
        """
        barra = next(
            b for b in _barras_de_prueba(citation_precision=0.5) if b.nombre == "citation-precision"
        )
        assert barra.comparador == ">="
        assert barra.pasa

    def test_un_hit_rate_bajo_la_barra_no_pasa(self):
        assert not _barra("hit-rate@5", hit_rate=0.71).pasa

    def test_una_citation_precision_bajo_el_piso_no_pasa(self):
        """The floor is a floor. `>=` with no failing case is `True` with extra steps."""
        assert not _barra("citation-precision", citation_precision=0.20).pasa
        assert _barra("citation-precision", citation_precision=0.34).pasa

    def test_hit_rate_at_10_discrimina_en_ambas_direcciones(self):
        """The new bar is scored, not merely published.

        `hit-rate@10` arrived with the amendment, and a bar that has never been
        seen to FAIL is indistinguishable from a bar that is not wired to
        anything — which is exactly how the old `hybrid` gate survived being
        pointed at an arm nobody ran.
        """
        assert not _barra("hit-rate@10", hit_rate_at_10=0.79).pasa
        assert _barra("hit-rate@10", hit_rate_at_10=0.81).pasa

    @pytest.mark.parametrize(
        ("nombre", "parametro", "minimo"),
        [
            ("hit-rate@5", "hit_rate", harness.BARRA_HIT_RATE),
            ("hit-rate@10", "hit_rate_at_10", harness.BARRA_HIT_RATE_10),
            ("citation-precision", "citation_precision", harness.BARRA_CITATION_PRECISION),
        ],
    )
    def test_el_valor_exacto_de_la_barra_pasa(self, nombre, parametro, minimo):
        """`>=`, not `>`. The boundary is INSIDE the bar.

        This is the mutation `>=` → `>` that no amount of testing 1.0 against
        0.72 can kill, and the one that matters: the B50 family reads ≈0.72–0.76
        on a 29-question set where one question is worth 0.034, so the measured
        arm can land exactly on its own minimum.
        """
        assert _barra(nombre, **{parametro: minimo}).pasa

    def test_la_senal_de_abstencion_de_bm25_ce_no_se_improvisa(self):
        """Owner decision 0.1 is OPEN, and no code may pick a side.

        Reranker confidence measured WORSE than cosine (LOOCV precision 0.489 at
        recall 1.000). Defaulting to whatever number a run happens to carry would
        set the gate to whatever the system already does — which is how a
        threshold stops being a threshold.
        """
        resultado = ResultadoRecuperacion(
            corpus_sha=SHA,
            pregunta="canal",
            modo="bm25_ce",
            k=1,
            hits=[],
        )
        resultado.hits.append(_cita_sin_rrf())
        with pytest.raises(harness.SenalAbstencionNoRatificada):
            harness._escala_de_senal(resultado)

    def test_la_negativa_tambien_cubre_la_pagina_VACIA(self):
        """The leak the shape-keyed guard had, and the case it mattered most in.

        The refusal used to be keyed on `any(hit.score_rrf is None ...)`, which
        over zero hits is `False` — so a `bm25_ce` question that retrieved
        nothing fell through to the RRF branch and produced `top1 = 0.0` labelled
        `RRF fusionado`, from a fusion that never ran. An empty page is the
        single most load-bearing point of an abstention grid (it is what
        "abstain" looks like), so the guard was open on precisely the input it
        exists for. It is now keyed on the MODE.
        """
        resultado = ResultadoRecuperacion(
            corpus_sha=SHA, pregunta="canal", modo="bm25_ce", k=10, hits=[]
        )
        with pytest.raises(harness.SenalAbstencionNoRatificada):
            harness._escala_de_senal(resultado)

    def test_una_pagina_vacia_de_un_modo_RRF_sigue_dando_senal(self):
        """The fix must not turn every empty page into a refusal.

        `fts` retrieving nothing is a legitimate `0.0` on a ratified scale — that
        is the whole `senales_desde` contract — and breaking it would silently
        drop the published baseline out of the abstention table.
        """
        vacio = ResultadoRecuperacion(corpus_sha=SHA, pregunta="canal", modo="fts", k=10, hits=[])
        scores, fuente = harness._escala_de_senal(vacio)
        assert scores == []
        assert fuente == harness.FUENTE_FTS


class TestRankerSinteticoNoAbreLaCompuerta:
    """spec `knowledge-hybrid-retrieval` — "A synthetic ranker cannot open the gate".

    RAG3-001 refused a report rendered over synthetic EMBEDDINGS. Under `bm25_ce`
    that refusal covered nothing: the arm reads no vector column, so its snapshot
    provenance is honest while a `RerankerDeterministico` fabricates the entire
    order — the cross-encoder score is the ranking in full. The scenario existed
    in the spec with no code behind it; these are the two directions.
    """

    def test_un_ranker_sintetico_cierra_la_compuerta(self):
        resultado = _eval_de_prueba(
            _corrida_de_prueba(ranker_modelo="deterministico", ranker_sintetico=True)
        )
        with pytest.raises(EvalSinteticoNoEsEval) as excinfo:
            renderizar_markdown(resultado, None, generado_en=MOMENTO, device_consulta="cpu")
        mensaje = str(excinfo.value)
        assert "deterministico" in mensaje
        assert "bm25_ce" in mensaje

    def test_el_smoke_run_permitido_no_lleva_veredicto_ni_nombre_de_eval(self):
        """Same treatment as synthetic embeddings: no verdict, `SINTETICO-` infix."""
        resultado = _eval_de_prueba(
            _corrida_de_prueba(ranker_modelo="deterministico", ranker_sintetico=True)
        )
        markdown = renderizar_markdown(
            resultado,
            None,
            generado_en=MOMENTO,
            device_consulta="cpu",
            permitir_sintetico=True,
        )
        assert "SMOKE RUN" in markdown
        assert "NOT AN EVAL" in markdown
        assert "NO EVALUABLE" in markdown
        assert "ranker SINTÉTICO" in markdown
        assert nombre_de_archivo(SHA, MOMENTO, sintetico=True).startswith(
            "retrieval-eval-SINTETICO-"
        )

    def test_el_ranker_real_no_interfiere(self):
        """A real ranker over real provenance renders as an eval, unchanged."""
        resultado = _eval_de_prueba(
            _corrida_de_prueba(
                ranker_modelo=modulo_reranker.MODELO_RERANKER, ranker_sintetico=False
            )
        )
        markdown = renderizar_markdown(resultado, None, generado_en=MOMENTO, device_consulta="cpu")
        assert "SMOKE RUN" not in markdown
        assert "ranker SINTÉTICO" not in markdown

    def test_un_modo_sin_ranker_no_dispara_la_compuerta(self):
        """The RRF ablation orders by fusion and has no ranker: `None`, not False.

        Guards against the obvious over-correction — treating "no ranker
        recorded" as "synthetic" would refuse to publish the very baseline B50 is
        quoted against.
        """
        corrida = _corrida_de_prueba()
        assert corrida.ranker_sintetico is None
        markdown = renderizar_markdown(
            _eval_de_prueba(corrida), None, generado_en=MOMENTO, device_consulta="cpu"
        )
        assert "SMOKE RUN" not in markdown

    def test_el_json_publica_la_identidad_del_ranker(self, tmp_path):
        """A machine reader must not have to parse the Spanish banner."""
        resultado = _eval_de_prueba(
            _corrida_de_prueba(ranker_modelo="deterministico", ranker_sintetico=True)
        )
        escrito = escribir_reporte(
            resultado,
            None,
            destino=tmp_path,
            generado_en=MOMENTO,
            device_consulta="cpu",
            permitir_sintetico=True,
        )
        assert escrito.markdown.name.startswith("retrieval-eval-SINTETICO-")
        datos = json.loads(escrito.json.read_text(encoding="utf-8"))
        assert datos["sintetico"] is True
        assert datos["modos"]["bm25_ce"]["ranker"] == {
            "modelo": "deterministico",
            "sintetico": True,
        }
        assert datos["modos"]["bm25_ce"]["go_no_go"]["veredicto"] == "NO EVALUABLE"


def _cita_sin_rrf():
    from app.domains.conocimiento.schemas import CitaRecuperada

    return CitaRecuperada(
        citation_key="9750#1",
        documento_id="ley-9750",
        tipo_chunk="articulo",
        texto="canal",
        tipo="ley-provincial",
        es_secundaria=False,
        jurisdiccion="provincial",
        source_file="f.md",
        source_offset=0,
        score_ce=1.0,
    )


def _corrida_de_prueba(
    *,
    hit_rate: float = 1.0,
    hit_rate_at_10: float = 1.0,
    citation_precision: float = 1.0,
    ranker_modelo: str | None = None,
    ranker_sintetico: bool | None = None,
) -> harness.ResultadoModo:
    """One `bm25_ce` `ResultadoModo`, without a 52-item fixture or a database."""
    return harness.ResultadoModo(
        modo="bm25_ce",
        k=10,
        preguntas=(),
        senales=(),
        detalles=(),
        metricas=metrics.MetricasRecuperacion(
            n_respondibles=29,
            hit_rate_at_5=hit_rate,
            mrr=1.0,
            citation_precision=citation_precision,
            separacion_norma_secundaria=1.0,
            vigencia_correctness=1.0,
            n_vigencia=29,
            hit_rate_at_10=hit_rate_at_10,
        ),
        ranker_modelo=ranker_modelo,
        ranker_sintetico=ranker_sintetico,
    )


def _barras_de_prueba(
    *,
    hit_rate: float = 1.0,
    hit_rate_at_10: float = 1.0,
    citation_precision: float = 1.0,
):
    """The bar tuple `decidir_go_no_go` builds, without a 52-item fixture.

    `forzar_evaluable` is the harness's own test seam for exactly this: the bar
    ARITHMETIC is what is under test here, not the n>=20 precondition.

    Every scored metric is a parameter so each bar can be driven in BOTH
    directions. A bar exercised only above its minimum proves the comparison
    fires, never that it discriminates: `valor >= minimo` and `True` are
    indistinguishable from that side.
    """
    corrida = _corrida_de_prueba(
        hit_rate=hit_rate,
        hit_rate_at_10=hit_rate_at_10,
        citation_precision=citation_precision,
    )
    gold = harness.GoldSet(version=1, corpus_sha=SHA, ratificado="owner", items=())
    return harness.decidir_go_no_go(corrida, gold, forzar_evaluable=True).barras


def _barra(nombre: str, **valores):
    return next(b for b in _barras_de_prueba(**valores) if b.nombre == nombre)


def _eval_de_prueba(corrida: harness.ResultadoModo) -> harness.ResultadoEval:
    return harness.ResultadoEval(
        corpus_sha=SHA,
        modos=("bm25_ce",),
        por_modo={"bm25_ce": corrida},
        gold=harness.GoldSet(version=1, corpus_sha=SHA, ratificado="owner", items=()),
    )
