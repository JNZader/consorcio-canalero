"""Three-mode eval harness over the gold set (tasks 4.6-4.9).

Split by what each test needs, following the slice-3 precedent:

* gold-set loading, the n>=20 precondition, the go/no-go arithmetic and the
  service-layer import boundary are pure and run in the CI shape;
* one-mode runs against a seeded snapshot need real PostgreSQL but no pgvector,
  so they also run in the CI shape (`fts`);
* the three-mode ablation and the fused hybrid path are `pgvector`-marked;
* the real 52-item gold set is validated against the real corpus under the
  `corpus` marker — every expected citation key must be a unit that exists,
  because a gold set that cites a key the corpus does not have measures the
  typo, not the retrieval.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from sqlalchemy import text

from app.domains.conocimiento.abstention import AbstentionPolicy, SenalAbstencion
from app.domains.conocimiento.embedding import DETERMINISTIC_MODEL_ID, DeterministicEmbedder
from app.domains.conocimiento.eval import harness
from app.domains.conocimiento.eval.harness import (
    GoldItem,
    GoldSet,
    GoldSetInvalido,
    cargar_gold_set,
    correr_modo,
    decidir_go_no_go,
    evaluar,
    senales_desde,
)
from app.domains.conocimiento.repository import registrar_procedencia

from .conftest import real_corpus_path, requires_real_corpus

SHA = "d" * 40


# ---------------------------------------------------------------------------
# A seeded mini-snapshot: two vigencia traps and one plain article.
# ---------------------------------------------------------------------------

VIGENCIA_2032 = (
    "Vigencia de los fondos. El plazo del artículo 17 fue prorrogado hasta el "
    "31 de diciembre de 2032 por el artículo 61 de la Ley 11089."
)
ART17 = (
    "Artículo 17.- Créase la Contribución Especial FDA, que regirá hasta el 31 "
    "de diciembre de 2023 para financiar obras de drenaje."
)
ART_8548 = "Artículo 1.- Organización del servicio de agua y saneamiento provincial."
ART_QUORUM = (
    "Artículo 14.- El quórum de la asamblea es la mitad más uno de los "
    "consorcistas en condiciones de votar."
)

DOCUMENTOS = {
    "ley-10679": {
        "tipo": "ley-provincial",
        "es_secundaria": False,
        "jurisdiccion": "provincial",
        "estado_vigencia": "vigente con modificaciones",
        "relevancia_consorcio": None,
    },
    "ley-8548": {
        "tipo": "ley-provincial",
        "es_secundaria": False,
        "jurisdiccion": "provincial",
        "estado_vigencia": "derogada",
        "relevancia_consorcio": None,
    },
    "ley-9750": {
        "tipo": "ley-provincial",
        "es_secundaria": False,
        "jurisdiccion": "provincial",
        "estado_vigencia": "vigente",
        "relevancia_consorcio": None,
    },
    "informe-f3": {
        "tipo": "informe-operativo",
        "es_secundaria": True,
        "jurisdiccion": "provincial",
        "estado_vigencia": None,
        "relevancia_consorcio": None,
    },
}

UNIDADES = [
    ("ley-10679", "10679#17", "articulo", ART17),
    ("ley-10679", "10679#vigencia-de-los-fondos", "nota-vigencia", VIGENCIA_2032),
    ("ley-8548", "8548#1", "articulo", ART_8548),
    ("ley-9750", "9750#14", "articulo", ART_QUORUM),
    ("informe-f3", "informe-f3#sec-3", "seccion-secundaria", "El informe comenta el quórum."),
]


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
            "jurisdiccion, estado_vigencia, relevancia_consorcio, clasificacion) VALUES "
            "(:sha, :documento_id, :tipo, :es_secundaria, :jurisdiccion, :estado_vigencia, "
            ":relevancia_consorcio, 'privado')"
        ),
        [
            {"sha": SHA, "documento_id": documento_id, **campos}
            for documento_id, campos in DOCUMENTOS.items()
        ],
    )
    db.execute(
        text(
            "INSERT INTO rag_unidad (corpus_sha, citation_key, documento_id, tipo_chunk, "
            "epigrafe, texto, texto_indexado, source_file, source_offset) VALUES "
            "(:sha, :key, :documento_id, :tipo_chunk, :key, :texto, :texto, 'f.md', 0)"
        ),
        [
            {
                "sha": SHA,
                "key": citation_key,
                "documento_id": documento_id,
                "tipo_chunk": tipo_chunk,
                "texto": texto,
            }
            for documento_id, citation_key, tipo_chunk, texto in UNIDADES
        ],
    )
    db.flush()


@pytest.fixture
def snapshot(db):
    seed(db)
    return db


def gold_item(
    id: str,
    pregunta: str,
    clase: str,
    citas: tuple[str, ...] = (),
    citas_vigencia: tuple[str, ...] = (),
) -> GoldItem:
    return GoldItem(
        id=id,
        pregunta=pregunta,
        pregunta_ref=None,
        clase=clase,
        subclase="directa",
        citas_esperadas=citas,
        citas_vigencia=citas_vigencia,
        fuente="fixture",
        validado_por="owner",
        dificultad="facil",
        origen="publico",
    )


def gold_set(*items: GoldItem, corpus_sha: str = SHA) -> GoldSet:
    return GoldSet(version=1, corpus_sha=corpus_sha, ratificado="2026-08-10", items=tuple(items))


PREGUNTAS = gold_set(
    gold_item("g-quorum", "quórum de la asamblea consorcistas", "answerable", ("9750#14",)),
    gold_item(
        "g-fda",
        "vigencia de los fondos del artículo 17",
        "trampa-vigencia",
        ("10679#17", "10679#vigencia-de-los-fondos"),
        ("10679#vigencia-de-los-fondos",),
    ),
    gold_item("g-hueco", "cuántos metros de ancho tiene la zona de camino", "unanswerable"),
)


# ---------------------------------------------------------------------------
# The design rule from D4/A1: the harness may not reach past the service layer.
# ---------------------------------------------------------------------------


class TestServiceLayerBoundary:
    """A1 (ledger RAG3-R01), and it is a real hazard rather than tidiness.

    `repository.vector_search` raises ONLY `VectorSupportUnavailable`. The two
    refusals that keep a published measurement honest — `EmbeddingsNoCargadas`
    and `EmbedderMismatch` — live in `service.verificar_embedder`, because the
    repository receives a query vector and has no way to know which model
    produced the column. A harness that called the leg directly would rank a real
    BGE-M3 corpus with the deterministic smoke embedder and publish the result.
    """

    @staticmethod
    def _nombres_importados(nodo) -> list[str]:
        """Every module path an import statement can name.

        `from app.domains.conocimiento import repository` was the hole: the
        `ImportFrom` branch only looked at `node.module`, which is
        `app.domains.conocimiento` — it does not end in `.repository`, so the
        check passed while the module was fully in scope under the plain name
        `repository`. The bound aliases have to be joined onto the module for the
        walk to see what the import actually brings in.
        """
        import ast

        if isinstance(nodo, ast.Import):
            return [alias.name for alias in nodo.names]
        if isinstance(nodo, ast.ImportFrom) and nodo.module:
            return [nodo.module] + [f"{nodo.module}.{alias.name}" for alias in nodo.names]
        return []

    def _modulos_importados_por_el_paquete_eval(self) -> list[tuple[str, int, str]]:
        import ast

        paquete = Path(harness.__file__).parent
        encontrados: list[tuple[str, int, str]] = []
        for archivo in sorted(paquete.rglob("*.py")):
            arbol = ast.parse(archivo.read_text(encoding="utf-8"))
            for nodo in ast.walk(arbol):
                for nombre in self._nombres_importados(nodo):
                    encontrados.append((archivo.name, nodo.lineno, nombre))
        return encontrados

    def test_the_eval_package_never_imports_the_repository(self):
        ofensores = [
            f"{archivo}:{linea} -> {nombre}"
            for archivo, linea, nombre in self._modulos_importados_por_el_paquete_eval()
            if nombre.endswith("conocimiento.repository") or ".repository" in nombre
        ]
        assert ofensores == []

    def test_the_eval_package_never_imports_importlib(self):
        """The escape hatch the AST walk cannot follow, closed at the door.

        `importlib.import_module("…repository")` builds the module name at run
        time, so no static walk over import statements can see it. Nothing in
        this package has a legitimate use for dynamic imports, so the honest
        guard is to forbid the tool rather than to pretend the walk covers it.
        """
        ofensores = [
            f"{archivo}:{linea} -> {nombre}"
            for archivo, linea, nombre in self._modulos_importados_por_el_paquete_eval()
            if nombre == "importlib" or nombre.startswith("importlib.")
        ]
        assert ofensores == []

    def test_retrieval_really_goes_through_recuperar(self, snapshot, monkeypatch):
        """Not just an import check: the calls are observed, both ways round.

        Two independent layers, and each covers what the other misses. The AST
        walk catches a direct import of the leg; it cannot see
        `importlib.import_module` (hence the test above). The spy catches a call
        through the module attribute; it cannot see a call made through a name
        imported at module load — which is what the AST walk is for.

        The spy also asserts what the original version did NOT: that no
        ADDITIONAL call reached `repository.vector_search`. Going through
        `service.recuperar` and ALSO poking the leg directly would have satisfied
        the old assertion perfectly, and the direct call is where both provenance
        refusals are lost.
        """
        from app.domains.conocimiento import repository

        llamadas: list[str] = []
        legs: list[str] = []
        original = harness.service.recuperar

        def espia(*args, **kwargs):
            llamadas.append(kwargs.get("modo", "?"))
            return original(*args, **kwargs)

        def espia_leg(*_args, **_kwargs):
            legs.append("vector_search")
            raise AssertionError("the harness reached the vector leg directly")

        monkeypatch.setattr(harness.service, "recuperar", espia)
        monkeypatch.setattr(repository, "vector_search", espia_leg)
        correr_modo(snapshot, SHA, PREGUNTAS, modo="fts")
        assert llamadas == ["fts", "fts", "fts"]
        assert legs == []


# ---------------------------------------------------------------------------
# 4.6 — the gold-set precondition
# ---------------------------------------------------------------------------


class TestPrecondition:
    """4.6: `test_n_lt_20_blocks_scoring`."""

    def test_n_lt_20_blocks_scoring(self, snapshot):
        corrida = correr_modo(snapshot, SHA, PREGUNTAS, modo="fts")
        decision = decidir_go_no_go(corrida, PREGUNTAS)
        assert decision.evaluable is False
        assert any("20" in motivo for motivo in decision.motivos_no_evaluable)
        # Not-evaluable is NOT a failure verdict: it must not read as "measured
        # and failed", which is a different and much more useful fact.
        assert decision.pasa is False
        assert decision.veredicto == "NO EVALUABLE"

    def test_a_draft_item_blocks_scoring_even_at_n_over_20(self):
        items = [gold_item(f"a{i}", f"pregunta {i}", "answerable", ("9750#14",)) for i in range(25)]
        items.append(
            GoldItem(
                id="sin-validar",
                pregunta="una pregunta que el dueño no miró",
                pregunta_ref=None,
                clase="answerable",
                subclase="directa",
                citas_esperadas=("9750#14",),
                citas_vigencia=(),
                fuente="fixture",
                validado_por="draft",
                dificultad=None,
                origen="publico",
            )
        )
        conjunto = gold_set(*items)
        precondicion = conjunto.precondicion()
        assert precondicion.evaluable is False
        assert "sin-validar" in " ".join(precondicion.motivos)

    def test_an_unresolved_private_item_blocks_scoring(self):
        """The privacy split must not become a quiet way to shrink the set."""
        items = [gold_item(f"a{i}", f"pregunta {i}", "answerable", ("9750#14",)) for i in range(25)]
        items.append(
            GoldItem(
                id="A-17",
                pregunta=None,
                pregunta_ref="auditoria-obras-zona-10-de-mayo.md#§5.E.17",
                clase="unanswerable",
                subclase="abstencion",
                citas_esperadas=(),
                citas_vigencia=(),
                fuente="auditoria",
                validado_por="owner",
                dificultad=None,
                origen="privado",
            )
        )
        precondicion = gold_set(*items).precondicion()
        assert precondicion.evaluable is False
        assert "A-17" in " ".join(precondicion.motivos)

    def test_a_fully_owner_validated_set_of_20_is_evaluable(self):
        items = [gold_item(f"a{i}", f"pregunta {i}", "answerable", ("9750#14",)) for i in range(20)]
        items += [gold_item(f"x{i}", f"hueco {i}", "unanswerable") for i in range(3)]
        precondicion = gold_set(*items).precondicion()
        assert precondicion.evaluable is True
        assert precondicion.n_respondibles == 20


# ---------------------------------------------------------------------------
# 4.7 — the three modes, abstention, and a hit above threshold
# ---------------------------------------------------------------------------


class TestOneModeInTheCIShape:
    def test_unanswerable_question_triggers_abstention(self, snapshot):
        """The hueco question matches nothing in this snapshot, so the fused top
        score is 0.0 and any threshold above it abstains."""
        corrida = correr_modo(snapshot, SHA, PREGUNTAS, modo="fts")
        senal = {s.id: s for s in corrida.senales}["g-hueco"]
        assert senal.score_top1 == 0.0
        assert AbstentionPolicy(min_score=0.01).abstiene(senal) is True

    def test_answerable_question_above_threshold_returns_hit(self, snapshot):
        corrida = correr_modo(snapshot, SHA, PREGUNTAS, modo="fts")
        detalle = {d.id: d for d in corrida.detalles}["g-quorum"]
        assert "9750#14" in detalle.claves_devueltas
        senal = {s.id: s for s in corrida.senales}["g-quorum"]
        assert senal.score_top1 > 0.0
        assert AbstentionPolicy(min_score=0.01).abstiene(senal) is False

    def test_a_question_that_returned_nothing_scores_zero_not_none(self, snapshot):
        corrida = correr_modo(snapshot, SHA, PREGUNTAS, modo="fts")
        detalle = {d.id: d for d in corrida.detalles}["g-hueco"]
        assert detalle.claves_devueltas == ()
        assert detalle.score_top1 == 0.0

    def test_a_natural_language_gold_question_reaches_the_fts_leg(self, snapshot):
        """RAG4-001 FIXED, pinned here because it decides what the ablation MEANS.

        This test used to assert the opposite, and the flip is the finding.
        `websearch_to_tsquery` ANDs, so gold item D-1 — the easiest question in
        the ratified set — compiled to ELEVEN conjunctive lexemes:

            'convoc' & 'asamble' & 'hor' & 'arranc' & 'lleg' & 'mit' & 'soci'
            & 'pod' & 'empez' & 'igual' & 'suspend'

        `9750#14` is three lines about quórum: it carries 'asamble' and 'soci'
        and none of the other nine, so the leg returned ZERO rows — not a bad
        ranking, no rows at all, because the conjunction sits in the WHERE clause
        and `ts_rank_cd` never runs. Measured against the real pinned corpus, six
        of six sampled gold questions came back empty. The FTS-only arm of the
        ablation therefore measured the query builder, and `hybrid` degenerated
        into vector-only while keeping the fused label.

        `repository.FTS_SEARCH_SQL` now ORs the lexemes (`FTS_OPERADOR`), so the
        colloquial phrasing retrieves the article. Same question, same index,
        same corpus — only the operator changed, which is what makes the leg a
        measurement of the INDEX rather than of `websearch`'s grammar.
        """
        natural = gold_set(
            gold_item(
                "g-natural",
                "Convocamos la asamblea y a la hora de arrancar no llegamos ni a la "
                "mitad de los socios. ¿La podemos empezar igual o hay que suspenderla?",
                "answerable",
                ("9750#14",),
            )
        )
        corrida = correr_modo(snapshot, SHA, natural, modo="fts")
        assert "9750#14" in corrida.detalles[0].claves_devueltas
        assert corrida.detalles[0].n_fts > 0

        # The article's own words still retrieve it, and still rank it FIRST.
        # The page is longer than it was — `informe-f3#sec-3` ("El informe comenta
        # el quórum") now shares a lexeme and enters the candidate set — and that
        # is the disjunction's real cost, stated rather than hidden: a wider net
        # brings in secondary sources, which is precisely what
        # `separacion_norma_secundaria` is a hard `== 1.00` bar about. Rank, not
        # membership, is what the metric grades.
        recortada = gold_set(
            gold_item("g-recortada", "quórum de la asamblea", "answerable", ("9750#14",))
        )
        devueltas = correr_modo(snapshot, SHA, recortada, modo="fts").detalles[0].claves_devueltas
        assert devueltas[0] == "9750#14"
        assert "informe-f3#sec-3" in devueltas

    def test_the_run_reports_per_leg_coverage_so_an_empty_leg_cannot_hide(self, snapshot):
        """A mode whose leg returned nothing for most questions is not a
        measurement of that leg, and the report must not be able to print its
        metrics without printing that fact next to them.

        The empty half is now a genuine VOCABULARY gap rather than an artefact of
        the operator: nothing in this snapshot talks about metres or roadways, so
        no lexeme of the question appears anywhere. That is the residue the OR fix
        cannot remove and the vector leg exists to cover.
        """
        mezcla = gold_set(
            gold_item("g-hueco", "cuántos metros de ancho tiene la zona de camino", "answerable"),
            gold_item("g-recortada", "quórum de la asamblea", "answerable", ("9750#14",)),
        )
        cobertura = correr_modo(snapshot, SHA, mezcla, modo="fts").cobertura
        assert cobertura.n_preguntas == 2
        assert cobertura.sin_candidatos_fts == 1
        assert cobertura.fraccion_sin_candidatos_fts == 0.5
        assert cobertura.leg_fts_degradada is False  # 0.5 is not a majority

    def test_a_mode_whose_fts_leg_is_mostly_empty_is_flagged_degraded(self, snapshot):
        vacia = gold_set(
            gold_item("g-hueco", "cuántos metros de ancho tiene la zona de camino", "answerable")
        )
        assert correr_modo(snapshot, SHA, vacia, modo="fts").cobertura.leg_fts_degradada is True

    def test_a_leg_the_mode_never_ran_is_not_called_degraded(self, snapshot):
        """ "It returned nothing" and "it was never asked" are different facts.

        Found on a real 52-question run against the pinned corpus: `--modo fts`
        printed `LEG DEGRADADA (vector)` beside a perfectly healthy lexical leg,
        because the vector leg trivially returned nothing for all 52 — it never
        ran. A warning that fires on every single-leg run is how a reader learns
        to skip the block that carries the RAG4-001 finding.
        """
        corrida = correr_modo(snapshot, SHA, PREGUNTAS, modo="fts")
        assert corrida.cobertura.legs_corridas == ("fts",)
        assert corrida.cobertura.sin_candidatos_vector == 3  # every question, trivially
        assert corrida.cobertura.fraccion_sin_candidatos_vector == 1.0
        assert corrida.cobertura.leg_vector_degradada is False

    def test_a_hybrid_whose_lexical_leg_died_on_most_questions_is_degenerate(self, snapshot):
        """The `all(...)` hole, closed (lens finding on RAG4-001's mitigation).

        `hibrido_degenerado` used to fire only when a leg contributed nothing on
        EVERY question, so one surviving question out of fifty switched the
        loudest warning in the report off. It now shares `leg_fts_degradada`'s
        strict-majority threshold: two of three questions with an empty lexical
        leg is a fused label over a single leg, and it says so.

        Built directly rather than run, because the fused mode needs pgvector and
        the predicate under test is arithmetic over the coverage counts.
        """
        detalles = [
            harness.DetallePregunta(
                id=id,
                clase="answerable",
                pregunta="…",
                citas_esperadas=(),
                claves_devueltas=(),
                score_top1=0.0,
                margen=0.0,
                n_fts=n_fts,
                n_vector=5,
            )
            for id, n_fts in (("a", 0), ("b", 0), ("c", 7))
        ]
        corrida = harness.ResultadoModo(
            modo="hybrid",
            k=10,
            preguntas=(),
            senales=(),
            detalles=tuple(detalles),
            metricas=harness.metricas_recuperacion([]),
        )
        assert corrida.cobertura.sin_candidatos_fts == 2
        assert corrida.hibrido_degenerado is True

        # One empty leg out of three is a miss, not a degenerate hybrid.
        sano = harness.ResultadoModo(
            modo="hybrid",
            k=10,
            preguntas=(),
            senales=(),
            detalles=tuple(detalles[1:]),
            metricas=harness.metricas_recuperacion([]),
        )
        assert sano.cobertura.sin_candidatos_fts == 1
        assert sano.hibrido_degenerado is False

    def test_the_run_is_deterministic_over_the_same_snapshot(self, snapshot):
        primera = correr_modo(snapshot, SHA, PREGUNTAS, modo="fts")
        segunda = correr_modo(snapshot, SHA, PREGUNTAS, modo="fts")
        assert [d.claves_devueltas for d in primera.detalles] == [
            d.claves_devueltas for d in segunda.detalles
        ]
        assert [s.score_top1 for s in primera.senales] == [s.score_top1 for s in segunda.senales]


class TestVigenciaTrap:
    """4.8: `test_vigencia_trap_surfaces_true_current_state`."""

    def test_vigencia_trap_surfaces_true_current_state(self, snapshot):
        corrida = correr_modo(snapshot, SHA, PREGUNTAS, modo="fts")
        detalle = {d.id: d for d in corrida.detalles}["g-fda"]
        # The article alone is the 2023 text. The nota-vigencia unit is what
        # makes the answer true today, and it must be in the page.
        assert "10679#vigencia-de-los-fondos" in detalle.claves_devueltas
        pregunta = {p.id: p for p in corrida.preguntas}["g-fda"]
        from app.domains.conocimiento.eval.metrics import vigencia_correctness

        assert vigencia_correctness(pregunta) == 1.0

    def test_a_derogated_law_hit_carries_its_state_rather_than_reading_as_live(self, snapshot):
        derogada = gold_set(
            gold_item(
                "g-8548",
                "organización del servicio de agua y saneamiento provincial",
                "trampa-vigencia",
                ("8548#1",),
                ("8548#1",),
            )
        )
        corrida = correr_modo(snapshot, SHA, derogada, modo="fts")
        pregunta = corrida.preguntas[0]
        assert pregunta.hits[0].citation_key == "8548#1"
        assert pregunta.hits[0].estado_vigencia == "derogada"

    def test_a_run_that_misses_the_caveat_unit_scores_zero(self, snapshot):
        """The failure this canary exists for: a byte-exact citation of the
        historic text, with nothing saying it is historic."""
        sin_caveat = gold_set(
            gold_item(
                "g-fda-solo-articulo",
                "quórum de la asamblea consorcistas",
                "trampa-vigencia",
                ("9750#14",),
                ("10679#vigencia-de-los-fondos",),
            )
        )
        corrida = correr_modo(snapshot, SHA, sin_caveat, modo="fts")
        from app.domains.conocimiento.eval.metrics import vigencia_correctness

        assert vigencia_correctness(corrida.preguntas[0]) == 0.0


# ---------------------------------------------------------------------------
# 4.9 — go/no-go is decided by the held-out pair and nothing else
# ---------------------------------------------------------------------------


def senales_sinteticas(**por_id: tuple[bool, float]) -> tuple[SenalAbstencion, ...]:
    return tuple(
        SenalAbstencion(
            id=id,
            debe_abstenerse=debe,
            score_top1=score,
            margen=0.0,
            ambas_piernas=False,
        )
        for id, (debe, score) in por_id.items()
    )


class TestGoNoGo:
    def test_false_confident_answer_fails_go_no_go_regardless_of_other_metrics(self, snapshot):
        """ONE unanswerable question answered -> NO-GO, everything else perfect.

        The fixture is built so that recall is the ONLY failing bar, which is
        what "regardless of other metrics" actually claims. Hand-traced:

          unanswerable u1..u5 at 0.10-0.14, u6 at 0.99 (outscores the set)
          answerable   a1..a5 at 0.50-0.54

        No threshold on the observed grid makes u6 abstain, so every fold that
        still contains it falls back to the highest-recall candidate (0.50 or
        0.51, abstaining u1..u5 with precision 1.00). The fold that HOLDS OUT u6
        reaches recall 1.00 at 0.50 and then answers u6 (0.99) — the single
        false-confident answer. The fold that holds out a1 is the only one whose
        grid starts at 0.51, so it abstains on a1 (0.50) by one step.

          held-out abstentions = u1..u5 (correct) + a1 (wrong) = 6
          recall    = 5/6 = 0.833  -> FAILS the strict 1.00
          precision = 5/6 = 0.833  -> clears 0.80
        """
        corrida = correr_modo(snapshot, SHA, PREGUNTAS, modo="fts")
        perfecta = harness.ResultadoModo(
            modo="fts",
            k=10,
            preguntas=corrida.preguntas,
            senales=senales_sinteticas(
                u1=(True, 0.10),
                u2=(True, 0.11),
                u3=(True, 0.12),
                u4=(True, 0.13),
                u5=(True, 0.14),
                a1=(False, 0.50),
                a2=(False, 0.51),
                a3=(False, 0.52),
                a4=(False, 0.53),
                a5=(False, 0.54),
                u6=(True, 0.99),
            ),
            detalles=corrida.detalles,
            metricas=harness.MetricasRecuperacion(
                n_respondibles=25,
                hit_rate_at_5=1.0,
                mrr=1.0,
                citation_precision=1.0,
                separacion_norma_secundaria=1.0,
                vigencia_correctness=1.0,
                n_vigencia=3,
                n_separacion=25,
            ),
        )
        assert perfecta.loocv.recall == pytest.approx(5 / 6)
        assert perfecta.loocv.precision == pytest.approx(5 / 6)

        decision = decidir_go_no_go(perfecta, PREGUNTAS, forzar_evaluable=True)
        assert decision.pasa is False
        assert decision.veredicto == "NO-GO"
        # Exactly one bar failed, and it is the strict one.
        assert decision.barras_fallidas == ("abstention recall",)

    def test_same_sample_fit_cannot_carry_go_no_go(self, snapshot):
        """The leakage fixture from `test_rag_abstention.py`, wired end to end:
        same-sample reads (1.00, 0.67) and the held-out pair reads (0.50, 0.33).
        The verdict follows the second."""
        corrida = correr_modo(snapshot, SHA, PREGUNTAS, modo="fts")
        con_fuga = harness.ResultadoModo(
            modo="fts",
            k=10,
            preguntas=corrida.preguntas,
            senales=senales_sinteticas(
                u1=(True, 0.10),
                a3=(False, 0.15),
                u2=(True, 0.20),
                a1=(False, 0.30),
                a2=(False, 0.40),
            ),
            detalles=corrida.detalles,
            metricas=harness.MetricasRecuperacion(
                n_respondibles=25,
                hit_rate_at_5=1.0,
                mrr=1.0,
                citation_precision=1.0,
                separacion_norma_secundaria=1.0,
                vigencia_correctness=1.0,
                n_vigencia=3,
                n_separacion=25,
            ),
        )
        decision = decidir_go_no_go(con_fuga, PREGUNTAS, forzar_evaluable=True)

        assert con_fuga.loocv.same_sample_recall == 1.0
        assert con_fuga.loocv.same_sample_precision == pytest.approx(2 / 3)
        assert con_fuga.loocv.recall == 0.5
        assert decision.pasa is False

        recall = {barra.nombre: barra for barra in decision.barras}["abstention recall"]
        assert recall.valor == 0.5, "the bar must read the held-out figure, not the fit"
        assert recall.fuente == "LOOCV held-out"

    def test_a_verdict_over_a_degraded_fused_leg_states_its_scope(self, snapshot):
        """`GO` printed above a `LEG DEGRADADA` block is a line somebody quotes
        without the block (lens finding on RAG4-001's mitigation).

        A degraded leg does NOT make the run unevaluable — the ablation still
        informs, and refusing to score would throw its finding away. What changes
        is that the verdict can no longer travel context-free: it says which leg
        it is really about, and the JSON carries a boolean so a machine reader
        does not have to parse the sentence.
        """
        corrida = correr_modo(snapshot, SHA, PREGUNTAS, modo="fts")
        degradado = harness.ResultadoModo(
            modo="hybrid",
            k=10,
            preguntas=corrida.preguntas,
            senales=corrida.senales,
            detalles=tuple(
                harness.DetallePregunta(
                    id=d.id,
                    clase=d.clase,
                    pregunta=d.pregunta,
                    citas_esperadas=d.citas_esperadas,
                    claves_devueltas=d.claves_devueltas,
                    score_top1=d.score_top1,
                    margen=d.margen,
                    n_fts=0,
                    n_vector=5,
                )
                for d in corrida.detalles
            ),
            metricas=corrida.metricas,
        )
        decision = decidir_go_no_go(degradado, PREGUNTAS, forzar_evaluable=True)

        assert decision.evaluable is True, "a degraded leg narrows the scope, it does not void it"
        assert decision.legs_degradadas == ("FTS",)
        assert decision.veredicto_calificado is True
        assert decision.veredicto in decision.veredicto_con_alcance
        assert "FTS" in decision.veredicto_con_alcance
        assert "vectorial" in decision.veredicto_con_alcance

    def test_a_healthy_verdict_is_the_bare_word(self, snapshot):
        corrida = correr_modo(snapshot, SHA, PREGUNTAS, modo="fts")
        decision = decidir_go_no_go(corrida, PREGUNTAS, forzar_evaluable=True)
        assert decision.legs_degradadas == ()
        assert decision.veredicto_calificado is False
        assert decision.veredicto_con_alcance == decision.veredicto

    def test_a_single_leg_mode_is_never_qualified(self, snapshot):
        """In `fts` the degradation IS the measurement, not a caveat on it — the
        mode never claimed to be about two legs."""
        vacia = gold_set(
            gold_item("g-hueco", "cuántos metros de ancho tiene la zona de camino", "answerable")
        )
        corrida = correr_modo(snapshot, SHA, vacia, modo="fts")
        assert corrida.cobertura.leg_fts_degradada is True
        decision = decidir_go_no_go(corrida, vacia, forzar_evaluable=True)
        assert decision.legs_degradadas == ()
        assert decision.veredicto_con_alcance == decision.veredicto

    def test_every_bar_is_named_with_its_source_so_the_report_cannot_mislabel_one(self, snapshot):
        corrida = correr_modo(snapshot, SHA, PREGUNTAS, modo="fts")
        decision = decidir_go_no_go(corrida, PREGUNTAS, forzar_evaluable=True)
        assert [barra.nombre for barra in decision.barras] == [
            "hit-rate@5",
            "MRR",
            "citation-precision",
            "norma-vs-secundaria",
            "vigencia-correctness",
            "abstention recall",
            "abstention precision",
        ]
        assert {barra.fuente for barra in decision.barras} == {
            "answerable subset",
            "LOOCV held-out",
        }


class TestThreeModes:
    def test_three_modes_same_questions_separate_metric_blocks_fts_only(self, snapshot):
        """The CI-shape half: the ablation's SHAPE is asserted without pgvector.

        `evaluar` with `modos=('fts',)` proves the per-mode block structure and
        that the same questions reach each mode; the full three-mode run needs
        the vector image and is the pgvector-marked test below.
        """
        resultado = evaluar(snapshot, SHA, PREGUNTAS, modos=("fts",))
        assert list(resultado.modos) == ["fts"]
        assert resultado.por_modo["fts"].metricas.n_respondibles == 2

    def test_asking_for_a_vector_mode_without_an_embedder_raises(self, snapshot):
        from app.domains.conocimiento.service import EmbedderRequerido

        with pytest.raises(EmbedderRequerido):
            correr_modo(snapshot, SHA, PREGUNTAS, modo="hybrid")


@pytest.mark.pgvector
class TestThreeModesForReal:
    """4.7: `test_three_modes_same_questions_separate_metric_blocks`."""

    def test_three_modes_same_questions_separate_metric_blocks(self, snapshot, pgvector_db):
        embedder = DeterministicEmbedder()
        registrar_procedencia(
            snapshot,
            SHA,
            modelo=DETERMINISTIC_MODEL_ID,
            revision_hf=None,
            sintetico=True,
            artifact_sha256="0" * 64,
        )
        snapshot.execute(
            text(
                "UPDATE rag_unidad SET embedding = CAST(:v AS vector) "
                "WHERE corpus_sha = :sha AND citation_key = :k"
            ),
            [
                {
                    "sha": SHA,
                    "k": citation_key,
                    "v": _literal(embedder, texto),
                }
                for _, citation_key, _, texto in UNIDADES
            ],
        )
        snapshot.flush()

        resultado = evaluar(snapshot, SHA, PREGUNTAS, embedder=embedder)

        assert list(resultado.modos) == ["fts", "vector", "hybrid"]
        # Same questions, three separate blocks — the whole point of an ablation.
        for modo in resultado.modos:
            assert [p.id for p in resultado.por_modo[modo].preguntas] == [
                "g-quorum",
                "g-fda",
                "g-hueco",
            ]
        # And the blocks are genuinely independent measurements, not one number
        # copied three times: the fused mode sees both legs.
        assert resultado.por_modo["hybrid"].detalles[0].n_vector > 0
        assert resultado.por_modo["fts"].detalles[0].n_vector == 0


def _literal(embedder, texto: str) -> str:
    from app.domains.conocimiento.embedding import vector_literal

    (vector,) = embedder.encode([texto])
    return vector_literal(vector)


# ---------------------------------------------------------------------------
# The over-ceiling exemption (RJDA-003 / RJDB-006)
# ---------------------------------------------------------------------------

#: `8548#1` stands in for gold D-8's `8560#5`: the item's ONLY expected citation
#: is a unit that, by ratified design, has no vector. Everything else is embedded.
SIN_VECTOR = "8548#1"

GOLD_D8 = gold_set(
    gold_item("g-quorum", "quórum de la asamblea consorcistas", "answerable", ("9750#14",)),
    gold_item(
        "d8-shaped",
        "organización del servicio de agua y saneamiento provincial",
        "answerable",
        (SIN_VECTOR,),
    ),
    gold_item("g-hueco", "cuántos metros de ancho tiene la zona de camino", "unanswerable"),
)


class TestExencionOverCeilingEnModoLexico:
    """`fts` exempts NOTHING, and never asks the database whether it should.

    This runs in the CI shape on the vector-less image, where the `embedding`
    column does not exist at all — so it is also the proof that the exemption
    query is scoped to the modes that need it. A `correr_modo(modo='fts')` that
    reached for `embedding IS NULL` would not merely mis-score here, it would
    raise `UndefinedColumn`.
    """

    def test_fts_scores_the_unreachable_item_normally(self, snapshot):
        corrida = correr_modo(snapshot, SHA, GOLD_D8, modo="fts")
        assert corrida.exencion.aplica is False
        assert corrida.exencion.claves == ()
        assert corrida.exencion.preguntas == ()
        # BOTH answerable items are in the denominator: the lexical leg reaches
        # the unit, so whatever it scored is a measurement.
        assert corrida.metricas.n_respondibles == 2
        assert corrida.metricas.n_citation_precision == 2
        assert all(p.precision_no_evaluable is False for p in corrida.preguntas)


@pytest.mark.pgvector
class TestExencionOverCeiling:
    """The vector arm cannot rank a unit that has no vector — and says so.

    Gold D-8's only expected citation `8560#5` is one of the three units over
    the 8192-token ceiling: ingested whole, FTS-retrievable, never embedded
    (design.md D3). Left in the denominator it pinned the vector arm's
    citation-precision below the hard `= 1.00` bar permanently, and the report
    explained nothing — a bar that can never be cleared is as unfalsifiable as
    one that can never be failed (the RAG4-004 defect, sign flipped).
    """

    def _snapshot_parcialmente_embebido(self, snapshot):
        embedder = DeterministicEmbedder()
        registrar_procedencia(
            snapshot,
            SHA,
            modelo=DETERMINISTIC_MODEL_ID,
            revision_hf=None,
            sintetico=True,
            artifact_sha256="0" * 64,
        )
        snapshot.execute(
            text(
                "UPDATE rag_unidad SET embedding = CAST(:v AS vector) "
                "WHERE corpus_sha = :sha AND citation_key = :k"
            ),
            [
                {"sha": SHA, "k": citation_key, "v": _literal(embedder, texto)}
                for _, citation_key, _, texto in UNIDADES
                if citation_key != SIN_VECTOR
            ],
        )
        snapshot.flush()
        return embedder

    def test_vector_mode_drops_the_unreachable_item_and_discloses_why(self, snapshot, pgvector_db):
        embedder = self._snapshot_parcialmente_embebido(snapshot)
        corrida = correr_modo(snapshot, SHA, GOLD_D8, modo="vector", embedder=embedder)

        assert corrida.exencion.aplica is True
        assert corrida.exencion.claves == (SIN_VECTOR,)
        assert corrida.exencion.preguntas == ("d8-shaped",)
        assert corrida.exencion.n_preguntas_exentas == 1

        por_id = {p.id: p for p in corrida.preguntas}
        assert por_id["d8-shaped"].precision_no_evaluable is True
        # The reachable item stays in, and so does the unanswerable one's status:
        # the exemption is about ONE metric's denominator, not about the run.
        assert por_id["g-quorum"].precision_no_evaluable is False
        assert por_id["g-hueco"].precision_no_evaluable is False

        assert corrida.metricas.n_respondibles == 2
        assert corrida.metricas.n_citation_precision == 1

    def test_hybrid_scores_the_same_item_normally(self, snapshot, pgvector_db):
        """The mode difference IS the ablation's finding, not noise."""
        embedder = self._snapshot_parcialmente_embebido(snapshot)
        corrida = correr_modo(snapshot, SHA, GOLD_D8, modo="hybrid", embedder=embedder)

        assert corrida.exencion.aplica is False
        assert corrida.exencion.claves == ()
        assert corrida.metricas.n_citation_precision == 2
        assert all(p.precision_no_evaluable is False for p in corrida.preguntas)

    def test_a_partially_reachable_item_is_never_exempt(self, snapshot, pgvector_db):
        """Two expected keys, one embedded: the score is capped but REAL.

        Exempting it would hide a genuine half-miss behind a design decision.
        """
        embedder = self._snapshot_parcialmente_embebido(snapshot)
        parcial = gold_set(
            gold_item(
                "compuesta",
                "organización del servicio y quórum de la asamblea",
                "answerable",
                (SIN_VECTOR, "9750#14"),
            ),
        )
        corrida = correr_modo(snapshot, SHA, parcial, modo="vector", embedder=embedder)
        assert corrida.exencion.preguntas == ()
        assert corrida.metricas.n_citation_precision == 1
        assert corrida.preguntas[0].precision_no_evaluable is False


# ---------------------------------------------------------------------------
# The committed gold set itself
# ---------------------------------------------------------------------------


class TestElGoldSetRatificado:
    def test_loads_with_the_ratified_denominators(self):
        conjunto = cargar_gold_set()
        assert len(conjunto.items) == 52
        assert conjunto.n_respondibles == 29
        assert conjunto.n_unanswerable == 23

    def test_every_item_is_owner_validated(self):
        conjunto = cargar_gold_set()
        assert [item.id for item in conjunto.items if item.validado_por != "owner"] == []

    def test_ids_are_unique(self):
        conjunto = cargar_gold_set()
        ids = [item.id for item in conjunto.items]
        assert len(ids) == len(set(ids))

    def test_trampa_vigencia_counts_as_answerable_and_declares_its_caveat_key(self):
        conjunto = cargar_gold_set()
        trampas = [item for item in conjunto.items if item.clase == "trampa-vigencia"]
        assert [item.id for item in trampas] == ["T-1", "T-2", "T-5"]
        for item in trampas:
            assert item.es_respondible is True
            assert item.citas_vigencia, f"{item.id} declares no caveat key"
            assert set(item.citas_vigencia).issubset(set(item.citas_esperadas))

    def test_the_t3_deadline_item_is_scored_as_ratified(self):
        """T-3 turns on art. 47 (all terms in días hábiles), which is what makes
        "31 de marzo" the wrong answer. Dropping `9750#47` from the expected set
        would quietly turn the trap into an ordinary question."""
        item = {i.id: i for i in cargar_gold_set().items}["T-3"]
        assert item.citas_esperadas == ("9750#19", "9750#12", "9750#47")
        assert item.clase == "answerable"
        assert item.subclase == "trampa-superada"

    def test_the_two_ingester_canaries_are_present_and_keyed_exactly(self):
        por_id = {item.id: item for item in cargar_gold_set().items}
        assert "10679#vigencia-de-los-fondos" in por_id["T-1"].citas_esperadas
        assert "10679#vigencia-de-los-fondos" in por_id["T-2"].citas_esperadas
        assert por_id["D-7"].citas_esperadas == ("8803#6",)

    def test_unanswerable_items_declare_no_expected_citation(self):
        for item in cargar_gold_set().items:
            if item.clase == "unanswerable":
                assert item.citas_esperadas == ()

    def test_no_private_question_text_is_committed_to_this_public_repo(self):
        """The rule from `gold_set.yaml`'s header, asserted rather than trusted.

        Every item transcribed from a `clasificacion = 'privado'` document must
        carry `pregunta_ref` and no text. A future edit that pastes the text in
        fails here, which is where that decision should be made deliberately.
        """
        crudo = yaml.safe_load(
            (Path(harness.__file__).parent / "gold_set.yaml").read_text(encoding="utf-8")
        )
        privados = [item for item in crudo["items"] if item["origen"] == "privado"]
        assert len(privados) == 26
        for item in privados:
            assert "pregunta" not in item, f"{item['id']} leaks its text into a public repo"
            assert item["pregunta_ref"]

    def test_private_items_are_unresolved_without_the_owner_side_file(self, monkeypatch):
        monkeypatch.delenv("RAG_GOLD_PRIVADO_PATH", raising=False)
        conjunto = cargar_gold_set()
        assert len(conjunto.no_resueltas) == 26
        assert conjunto.precondicion().evaluable is False

    def test_the_gold_set_and_the_snapshot_must_be_the_same_corpus_revision(self):
        """RAG4-003: the reconciliation that had no code behind it.

        `citas_esperadas` are keys of ONE corpus revision. Scored against a
        different snapshot, a key that does not exist there looks exactly like a
        retrieval miss — every metric drops and the report blames the retriever.
        """
        conjunto = cargar_gold_set()
        harness.verificar_corpus_sha(conjunto, conjunto.corpus_sha)  # matching: silent

        with pytest.raises(harness.CorpusShaMismatch) as abort:
            harness.verificar_corpus_sha(conjunto, "0" * 40)
        mensaje = str(abort.value)
        assert conjunto.corpus_sha in mensaje
        assert "0" * 40 in mensaje

    def test_a_private_file_pinned_to_another_revision_refuses_to_resolve(
        self, tmp_path, monkeypatch
    ):
        privado = tmp_path / "privado.yaml"
        privado.write_text(
            yaml.safe_dump(
                {"version": 1, "para": "gold_set.yaml", "corpus_sha": "0" * 40, "preguntas": {}},
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("RAG_GOLD_PRIVADO_PATH", str(privado))
        with pytest.raises(harness.CorpusShaMismatch, match="0" * 40):
            cargar_gold_set()

    def test_a_private_file_for_another_gold_set_refuses_to_resolve(self, tmp_path, monkeypatch):
        """`para:` is the file saying which set it belongs to, and reading it is
        the only thing between a stale owner-side copy and 26 questions resolved
        from the wrong place."""
        privado = tmp_path / "privado.yaml"
        privado.write_text(
            yaml.safe_dump(
                {"version": 1, "para": "otro-gold-set.yaml", "preguntas": {}}, allow_unicode=True
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("RAG_GOLD_PRIVADO_PATH", str(privado))
        with pytest.raises(GoldSetInvalido, match="otro-gold-set.yaml"):
            cargar_gold_set()

    def test_an_absent_private_file_is_not_an_error(self, tmp_path, monkeypatch):
        """Unresolved items are already a hard blocker in `precondicion()`. Only a
        file that IS there and contradicts the set it serves may raise."""
        monkeypatch.setenv("RAG_GOLD_PRIVADO_PATH", str(tmp_path / "no-existe.yaml"))
        conjunto = cargar_gold_set()
        assert len(conjunto.no_resueltas) == 26

    def test_the_committed_private_file_contract_matches_the_owner_side_one(
        self, tmp_path, monkeypatch
    ):
        """A file declaring the right `para:` and the right `corpus_sha` resolves."""
        privado = tmp_path / "privado.yaml"
        privado.write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "para": "gold_set.yaml",
                    "corpus_sha": cargar_gold_set().corpus_sha,
                    "preguntas": {"A-1": "sólo una"},
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("RAG_GOLD_PRIVADO_PATH", str(privado))
        assert "A-1" not in cargar_gold_set().no_resueltas

    def test_the_owner_side_file_resolves_them(self, tmp_path, monkeypatch):
        privado = tmp_path / "privado.yaml"
        privado.write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "preguntas": {
                        item["id"]: f"texto de {item['id']}"
                        for item in yaml.safe_load(
                            (Path(harness.__file__).parent / "gold_set.yaml").read_text(
                                encoding="utf-8"
                            )
                        )["items"]
                        if item["origen"] == "privado"
                    },
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("RAG_GOLD_PRIVADO_PATH", str(privado))
        conjunto = cargar_gold_set()
        assert conjunto.no_resueltas == ()
        assert conjunto.precondicion().evaluable is True
        assert conjunto.precondicion().n_respondibles == 29

    def test_a_private_file_missing_one_id_leaves_that_item_unresolved(self, tmp_path, monkeypatch):
        privado = tmp_path / "parcial.yaml"
        privado.write_text(
            yaml.safe_dump({"version": 1, "preguntas": {"A-1": "sólo una"}}, allow_unicode=True),
            encoding="utf-8",
        )
        monkeypatch.setenv("RAG_GOLD_PRIVADO_PATH", str(privado))
        conjunto = cargar_gold_set()
        assert "A-1" not in conjunto.no_resueltas
        assert "A-18" in conjunto.no_resueltas


class TestSenalesDesde:
    def test_senal_carries_the_margin_and_the_both_legs_flag(self, snapshot):
        corrida = correr_modo(snapshot, SHA, PREGUNTAS, modo="fts")
        por_id = {s.id: s for s in corrida.senales}
        assert por_id["g-quorum"].ambas_piernas is False
        assert por_id["g-quorum"].margen >= 0.0
        assert callable(senales_desde)


@requires_real_corpus
class TestGoldSetContraElCorpusReal:
    """Every expected citation key must be a unit that actually exists.

    A gold set that cites `res-dnv-908-2026#anexo2#norma10` when the corpus keys
    it `#anexo-ii#norma10` does not measure retrieval — it measures a typo, and
    it measures it as a permanent, unfixable miss.
    """

    def test_every_expected_citation_key_exists_in_the_pinned_corpus(self):
        from app.domains.conocimiento.service import load_corpus

        corpus = load_corpus(real_corpus_path())
        existentes = {
            unidad.citation_key for documento in corpus.documentos for unidad in documento.unidades
        }
        faltantes = sorted(
            {
                clave
                for item in cargar_gold_set().items
                for clave in item.citas_esperadas
                if clave not in existentes
            }
        )
        assert faltantes == []

    def test_the_gold_set_pins_the_same_corpus_sha_the_expectations_do(self):
        from app.domains.conocimiento.expectations import load_expectations

        assert cargar_gold_set().corpus_sha == load_expectations().corpus_sha
