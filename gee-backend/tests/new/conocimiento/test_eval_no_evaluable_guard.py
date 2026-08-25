"""The `NO EVALUABLE` machinery of the `bm25_ce` arm, under a guard.

The U9 verify found this whole mechanism unprotected: three separate mutations
of `harness.decidir_go_no_go` / `GoNoGo` survived the suite, and each one turns
an OPEN owner decision (0.1, the abstention bar nobody has ratified for this
arm) into a published verdict about the retriever:

* **M4** — drop `or self.barras_no_evaluables` from `GoNoGo.veredicto`. The two
  unmeasured abstention bars have `valor=None`, so `pasa` is False, so the
  verdict reads **`NO-GO`**: the arm was measured and fell short. It was not.
* **M5** — drop `and not barra.no_evaluable` from `GoNoGo.barras_fallidas`. The
  unmeasured bars are then listed under "fallan:", which tells an operator the
  retriever missed a target it was never scored against — and that gets "fixed"
  by lowering something.
* **M6** — pass `no_evaluable=False` for the abstention pair. Both of the above
  at once, plus a denominator printed beside a measurement that never happened.

The scenario the amended gate names (`specs/knowledge-hybrid-retrieval`,
`spec:131`) is the other half and is asserted here too: the six re-ratified
retrieval bars ARE scored in this mode. `not-evaluable` is scoped to the
abstention pair — turning it into a blanket refusal would throw away the
measurement the arm exists to produce.

Every assertion below is written so that a bar which really was measured and
really fell short still surfaces as a failure. A guard that hid real failures
would be a worse defect than the one it protects against.
"""

from __future__ import annotations

from app.domains.conocimiento.eval import report
from app.domains.conocimiento.eval.harness import (
    BARRA_CITATION_PRECISION,
    BARRA_HIT_RATE,
    BARRA_HIT_RATE_10,
    BARRA_MRR,
    BARRA_SEPARACION,
    BARRA_VIGENCIA,
    GoldItem,
    GoldSet,
    ResultadoModo,
    decidir_go_no_go,
)
from app.domains.conocimiento.eval.metrics import MetricasRecuperacion

SHA = "d" * 40

#: The two bars owner decision 0.1 leaves open for this arm.
PAR_ABSTENCION = ("abstention recall", "abstention precision")

#: The six the spec re-ratified. They are measured in `bm25_ce` like anywhere else.
SEIS_RERATIFICADAS = (
    "hit-rate@5",
    "hit-rate@10",
    "MRR",
    "citation-precision",
    "norma-vs-secundaria",
    "vigencia-correctness",
)


def metricas(*, hit_5: float = 0.90) -> MetricasRecuperacion:
    """Every re-ratified bar clears, except whatever the caller lowers.

    Values well above each floor, so the only `NO` in the table is the one a
    test asked for. A fixture that failed several bars at once could not tell
    "the failing bar is reported" from "everything is reported as failing".
    """
    return MetricasRecuperacion(
        n_respondibles=29,
        hit_rate_at_5=hit_5,
        hit_rate_at_10=0.95,
        mrr=0.80,
        citation_precision=0.60,
        separacion_norma_secundaria=1.0,
        vigencia_correctness=1.0,
        n_vigencia=7,
        n_separacion=29,
        n_citation_precision=29,
    )


def corrida_bm25_ce(**cambios) -> ResultadoModo:
    """A `bm25_ce` run with no signals at all — which is the real shape.

    `senales=()` is not a shortcut: `senales_desde` REFUSES for this mode
    (`SenalAbstencionNoRatificada`), because the arm carries no fused score to
    sweep a threshold over. That refusal is exactly why the pair is unmeasured.
    """
    return ResultadoModo(
        modo="bm25_ce",
        k=5,
        preguntas=(),
        senales=(),
        detalles=(),
        metricas=metricas(**cambios),
    )


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


def go_no_go(**cambios):
    """Scored with `forzar_evaluable`, to isolate the BAR-level refusal.

    The one-item gold set is below `MINIMO_RESPONDIBLES`, which would make the
    run `not-evaluable` for a second, unrelated reason and hide whether the
    abstention pair did anything at all.
    """
    return decidir_go_no_go(corrida_bm25_ce(**cambios), gold_minimo(), forzar_evaluable=True)


class TestElParDeAbstencionNoSeMide:
    """(a) — two rows, no value, no denominator. Kills M6."""

    def test_las_dos_filas_son_no_evaluables(self):
        decision = go_no_go()
        assert decision.barras_no_evaluables == PAR_ABSTENCION

    def test_ninguna_de_las_dos_trae_valor(self):
        """`valor=None` renders `n/d`. A `0.000` there is a measurement."""
        por_nombre = {barra.nombre: barra for barra in go_no_go().barras}
        for nombre in PAR_ABSTENCION:
            assert por_nombre[nombre].valor is None
            assert por_nombre[nombre].pasa is False, "unmeasured is never a pass either"

    def test_la_tabla_imprime_raya_en_la_columna_n(self):
        """`0` would be a count and `n_respondibles` the count of another sample."""
        corrida = corrida_bm25_ce()
        filas = report._tabla_metricas(corrida, go_no_go())
        del_par = [f for f in filas if any(f.startswith(f"| {n} ") for n in PAR_ABSTENCION)]
        assert len(del_par) == 2
        for fila in del_par:
            assert "| — |" in fila
            assert "| n/d |" in fila
            assert fila.rstrip().endswith("| not-evaluable |")


class TestElVeredictoNoEsNoGo:
    """(b) — `NO EVALUABLE`, never `NO-GO`. Kills M4."""

    def test_el_veredicto_dice_no_evaluable(self):
        assert go_no_go().veredicto == "NO EVALUABLE"

    def test_no_dice_no_go(self):
        """`NO-GO` claims the arm was measured and fell short. It was not.

        Quoted about `bm25_ce` that sentence attributes to the retriever — whose
        retrieval figures may be perfectly fine — a gap that belongs to an open
        owner decision.
        """
        assert go_no_go().veredicto != "NO-GO"

    def test_tampoco_es_un_pase(self):
        assert go_no_go().pasa is False

    def test_sigue_siendo_no_evaluable_aunque_todo_lo_medido_pase(self):
        """Every measured bar clearing must not upgrade the verdict to `GO`."""
        decision = go_no_go()
        medidas = [b for b in decision.barras if not b.no_evaluable]
        assert all(barra.pasa for barra in medidas)
        assert decision.veredicto == "NO EVALUABLE"

    def test_el_motivo_nombra_la_decision_abierta(self):
        motivos = " ".join(go_no_go().motivos_no_evaluable)
        assert "abstención" in motivos
        assert "ABIERTA" in motivos


class TestUnaFallaRealSigueSaliendo:
    """(c) — the guard must not become a place real failures hide. Kills M5."""

    def test_una_barra_de_recuperacion_caida_aparece_en_barras_fallidas(self):
        decision = go_no_go(hit_5=BARRA_HIT_RATE - 0.10)
        assert "hit-rate@5" in decision.barras_fallidas

    def test_el_par_no_evaluable_no_se_cuela_entre_las_fallidas(self):
        """Listing an unmeasured bar under "fallan:" invents a defect."""
        decision = go_no_go(hit_5=BARRA_HIT_RATE - 0.10)
        assert decision.barras_fallidas == ("hit-rate@5",)
        for nombre in PAR_ABSTENCION:
            assert nombre not in decision.barras_fallidas

    def test_sin_fallas_reales_la_lista_queda_vacia(self):
        assert go_no_go().barras_fallidas == ()

    def test_la_tabla_marca_NO_en_la_barra_realmente_caida(self):
        corrida = corrida_bm25_ce(hit_5=BARRA_HIT_RATE - 0.10)
        filas = report._tabla_metricas(corrida, go_no_go(hit_5=BARRA_HIT_RATE - 0.10))
        fila = next(f for f in filas if f.startswith("| hit-rate@5 "))
        assert fila.rstrip().endswith("| NO |")
        assert "| 29 |" in fila, "a measured bar keeps its denominator"


class TestLasSeisReRatificadasSePuntuan:
    """(d) — spec:131. `not-evaluable` is scoped to the pair, never the arm."""

    def test_las_seis_estan_y_ninguna_es_no_evaluable(self):
        por_nombre = {barra.nombre: barra for barra in go_no_go().barras}
        for nombre in SEIS_RERATIFICADAS:
            assert nombre in por_nombre
            assert por_nombre[nombre].no_evaluable is False

    def test_las_seis_llevan_el_valor_medido_y_su_barra(self):
        por_nombre = {barra.nombre: barra for barra in go_no_go().barras}
        esperado = {
            "hit-rate@5": (0.90, BARRA_HIT_RATE),
            "hit-rate@10": (0.95, BARRA_HIT_RATE_10),
            "MRR": (0.80, BARRA_MRR),
            "citation-precision": (0.60, BARRA_CITATION_PRECISION),
            "norma-vs-secundaria": (1.0, BARRA_SEPARACION),
            "vigencia-correctness": (1.0, BARRA_VIGENCIA),
        }
        for nombre, (valor, minimo) in esperado.items():
            assert por_nombre[nombre].valor == valor
            assert por_nombre[nombre].minimo == minimo
            assert por_nombre[nombre].pasa is True

    def test_la_tabla_las_puntua_con_si_o_NO_nunca_not_evaluable(self):
        corrida = corrida_bm25_ce()
        filas = report._tabla_metricas(corrida, go_no_go())
        for nombre in SEIS_RERATIFICADAS:
            fila = next(f for f in filas if f.startswith(f"| {nombre} "))
            assert "not-evaluable" not in fila
            assert fila.rstrip().endswith("| sí |")
