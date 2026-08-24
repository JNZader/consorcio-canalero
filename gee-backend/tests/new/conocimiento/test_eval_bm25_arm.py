"""Task 9.1b — the `bm25_ce` arm is scorable, and it publishes beside the baseline.

The amended V1 serving gate (`specs/knowledge-hybrid-retrieval/spec.md:88`) asks
the report to publish the `bm25_ce` arm "side by side with the recorded FTS-only
baselines so the margin is visible rather than asserted". Before this unit the
harness could not produce that arm at all:

* `correr_modo` took no `reranker` and passed none to `service.recuperar`, so a
  `bm25_ce` run raised `RerankerRequerido`; and
* `LEGS_POR_MODO` had no `bm25_ce` entry, so `legs_corridas` fell back to `()`
  and the coverage block reported the fused legs of a mode that runs neither.

Three refusals travel with the arm and each one has its own test below:

1. an arm ranked by a stand-in publishes as a SMOKE RUN, never as a margin
   (U2's `report._gate_sintetico`, which the new wiring must not route around);
2. the arm carries no fused score, so its abstention pair stays
   `SenalAbstencionNoRatificada` until owner decision 0.1 closes; and
3. the baseline block prints the RECORDED figures, never a recomputed one.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text

from app.domains.conocimiento.eval import harness, report
from app.domains.conocimiento.eval.harness import (
    LEGS_POR_MODO,
    GoldItem,
    GoldSet,
    SenalAbstencionNoRatificada,
    correr_modo,
    evaluar,
)
from app.domains.conocimiento.recuperacion.bm25 import limpiar_cache_indices
from app.domains.conocimiento.recuperacion.reranker import RerankerDeterministico
from app.domains.conocimiento.service import ProcedenciaEmbeddings

SHA = "e" * 40
MOMENTO = dt.datetime(2026, 8, 24, 12, 0, tzinfo=dt.timezone.utc)


@pytest.fixture(autouse=True)
def indice_limpio():
    limpiar_cache_indices()
    yield
    limpiar_cache_indices()


def seed(db) -> None:
    db.execute(
        text(
            "INSERT INTO rag_corpus (corpus_sha, repo_url, manifest_version, "
            "articulos_declarados, activo) VALUES (:sha, 'u', '2', 3, true)"
        ),
        {"sha": SHA},
    )
    db.execute(
        text(
            "INSERT INTO rag_documento (corpus_sha, documento_id, tipo, es_secundaria, "
            "jurisdiccion, estado_vigencia, clasificacion) VALUES "
            "(:sha, 'ley-9750', 'ley-provincial', false, 'provincial', 'vigente', 'publico')"
        ),
        {"sha": SHA},
    )
    db.execute(
        text(
            "INSERT INTO rag_unidad (corpus_sha, citation_key, documento_id, tipo_chunk, "
            "texto, texto_indexado, source_file, source_offset) VALUES "
            "(:sha, :key, 'ley-9750', 'articulo', :texto, :texto, 'f.md', 0)"
        ),
        [
            {"sha": SHA, "key": "9750#1", "texto": "El consorcio administra el canal de riego."},
            {"sha": SHA, "key": "9750#2", "texto": "La asamblea aprueba el presupuesto anual."},
            {"sha": SHA, "key": "9750#3", "texto": "El padrón registra a cada consorcista."},
        ],
    )
    db.flush()


def gold_minimo() -> GoldSet:
    return GoldSet(
        version=1,
        corpus_sha=SHA,
        ratificado="prueba",
        items=(
            GoldItem(
                id="B-1",
                pregunta="quién administra el canal",
                pregunta_ref=None,
                clase="legal",
                subclase="",
                citas_esperadas=("9750#1",),
                citas_vigencia=(),
                fuente="",
                validado_por="owner",
                dificultad=None,
                origen="publico",
            ),
        ),
    )


class TestElArmCorre:
    """9.1b — `correr_modo` accepts a reranker and `bm25_ce` becomes scorable."""

    def test_legs_por_modo_conoce_bm25_ce(self):
        """Its one candidate leg is BM25, NOT `fts`.

        A missing entry made `legs_corridas` empty, which turned every coverage
        annotation into "this leg does not run in this mode" — including for the
        leg that does.
        """
        assert LEGS_POR_MODO["bm25_ce"] == ("bm25",)

    def test_correr_modo_pasa_el_reranker(self, db):
        seed(db)
        corrida = correr_modo(
            db,
            SHA,
            gold_minimo(),
            modo="bm25_ce",
            reranker=RerankerDeterministico(),
        )
        assert corrida.modo == "bm25_ce"
        assert corrida.ranker_sintetico is True
        assert corrida.cobertura.legs_corridas == ("bm25",)
        assert corrida.cobertura.n_preguntas == 1

    def test_evaluar_tambien_lo_hilvana(self, db):
        seed(db)
        resultado = evaluar(
            db,
            SHA,
            gold_minimo(),
            modos=("bm25_ce",),
            reranker=RerankerDeterministico(),
        )
        assert set(resultado.por_modo) == {"bm25_ce"}

    def test_la_cobertura_cuenta_candidatos_bm25(self, db):
        seed(db)
        corrida = correr_modo(
            db, SHA, gold_minimo(), modo="bm25_ce", reranker=RerankerDeterministico()
        )
        # One of the three seeded units shares a lexeme with the question, so the
        # pool is one deep. The number that matters is that it is the POOL size
        # and not `k` — `n_bm25` counts what BM25 selected, before the CE cut.
        assert corrida.detalles[0].n_bm25 == 1
        assert corrida.cobertura.sin_candidatos_bm25 == 0

    def test_una_pregunta_sin_lexemas_deja_la_pierna_bm25_vacia(self, db):
        """An empty candidate pool is a real outcome and it is counted as one.

        `fts` and `vector` each have a counter for it; without one for BM25 the
        arm that is actually being gated is the only arm whose empty leg is
        invisible.
        """
        seed(db)
        gold = gold_minimo()
        vacia = GoldSet(
            version=1,
            corpus_sha=SHA,
            ratificado="prueba",
            items=(
                GoldItem(
                    id="B-2",
                    pregunta="zzzz",
                    pregunta_ref=None,
                    clase="legal",
                    subclase="",
                    citas_esperadas=("9750#1",),
                    citas_vigencia=(),
                    fuente="",
                    validado_por="owner",
                    dificultad=None,
                    origen="publico",
                ),
            ),
        )
        assert gold.items[0].id != vacia.items[0].id
        corrida = correr_modo(db, SHA, vacia, modo="bm25_ce", reranker=RerankerDeterministico())
        assert corrida.detalles[0].n_bm25 == 0
        assert corrida.cobertura.sin_candidatos_bm25 == 1


class TestElArmNoInventaAbstencion:
    """The abstention row stays `not-evaluable` while decision 0.1 is open."""

    def test_la_senal_sigue_siendo_no_ratificada(self, db):
        """`senales_desde` must still refuse for a mode with no fused score.

        Threading a reranker through the harness is a retrieval-margin feature.
        If it also gave `bm25_ce` an abstention grid it would have decided a
        go/no-go the owner has not decided.
        """
        seed(db)
        from app.domains.conocimiento import service

        resultado = service.recuperar(
            db, SHA, "canal", modo="bm25_ce", k=5, reranker=RerankerDeterministico()
        )
        with pytest.raises(SenalAbstencionNoRatificada):
            harness.senales_desde(gold_minimo().items[0], resultado)


class TestElMargenSePublica:
    """The baseline block: recorded figures beside the measured arm."""

    def test_las_baselines_son_las_registradas(self):
        assert report.BASELINE_FTS == {
            "hit-rate@5": 0.138,
            "MRR": 0.091,
            "citation-precision": 0.040,
        }

    def test_el_bloque_nombra_las_tres_baselines(self, db):
        seed(db)
        resultado = evaluar(
            db,
            SHA,
            gold_minimo(),
            modos=("bm25_ce",),
            reranker=RerankerDeterministico(),
        )
        bloque = "\n".join(report.bloque_margen_baseline(resultado))
        assert "0.138" in bloque and "0.091" in bloque and "0.040" in bloque
        assert "bm25_ce" in bloque
        # The honesty rider the spec requires next to the margin.
        assert "0.034" in bloque

    def test_sin_el_arm_el_bloque_lo_dice(self, db):
        """No `bm25_ce` run means no margin — stated, never silently omitted."""
        seed(db)
        resultado = evaluar(db, SHA, gold_minimo(), modos=("fts",))
        bloque = "\n".join(report.bloque_margen_baseline(resultado))
        assert "no se corrió" in bloque

    def test_un_ranker_sintetico_no_publica_margen(self, db):
        """The U2 gate must not be routed around by the new wiring.

        This is the whole reason `ranker_sintetico` is carried up from the
        results: an arm ordered by `RerankerDeterministico` is shaped exactly
        like a margin and is none.
        """
        seed(db)
        resultado = evaluar(
            db,
            SHA,
            gold_minimo(),
            modos=("bm25_ce",),
            reranker=RerankerDeterministico(),
        )
        procedencia = ProcedenciaEmbeddings(
            corpus_sha=SHA,
            modelo="BAAI/bge-m3",
            revision_hf="abc",
            sintetico=False,
            artifact_sha256="f" * 64,
            loaded_at=MOMENTO,
        )
        with pytest.raises(report.EvalSinteticoNoEsEval):
            report.renderizar_markdown(
                resultado,
                procedencia,
                generado_en=MOMENTO,
                device_consulta="cpu",
            )
