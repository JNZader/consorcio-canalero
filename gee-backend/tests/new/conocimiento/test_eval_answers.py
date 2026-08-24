"""Answer-level eval harness — tasks 9.1 to 9.4.

What this suite defends, in the order the design states it:

* **9.1** the invented-citation universe is the POST-EXCLUSION payload, computed
  by the same `assert_unidades_publicas` call the request path uses. Scoring
  against the retrieved page would measure a different function and would err in
  the dangerous direction — a retrieved-but-excluded key would read as *correct*
  here and be *rejected* in production;
* **9.2** `n >= 30` counts ANSWERS, the claim distribution travels beside it, and
  the intra-rater agreement is `not-evaluable` below its floor of 15 claims;
* **9.3** grades are pinned to `(prompt_version, provider_model_pin, corpus_sha)`
  and a divergence REFUSES, naming both operands;
* **9.4** end-to-end abstention is its own row, measured on the served outcome,
  and a reclassification re-triggers it even with `corpus_sha` unmoved.

Plus the refusal that makes the whole thing honest: the checked-in artifact has
no answers, and a harness that published `0/0` as `0.00` would report "no
failures found" for a measurement nobody ran.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml
from sqlalchemy import text

from app.domains.conocimiento import generacion
from app.domains.conocimiento.eval import answers
from app.domains.conocimiento.eval.answers import (
    N_MINIMO_RESPUESTAS,
    PISO_REGRADO,
    ConjuntoRespuestasInvalido,
    ConjuntoRespuestasNoRatificado,
    EntradaRespuestas,
    PayloadDivergente,
    PinRespuestasDivergente,
    RespuestasSinteticas,
    cargar_conjunto_respuestas,
    cargar_y_puntuar,
    muestra_de_regrado,
    puntuar,
    verificar_pines,
)

SHA = "f" * 40


# ---------------------------------------------------------------------------
# Artifact builders
# ---------------------------------------------------------------------------


def respuesta(
    id: str,
    *,
    texto: str = "El consorcio administra el canal [9750#1].",
    recuperadas: tuple[str, ...] = ("9750#1",),
    payload: tuple[str, ...] = ("9750#1",),
    estado: str = "respuesta",
    debe_abstenerse: bool = False,
    afirmaciones: tuple[dict, ...] = (),
    regrado: dict | None = None,
) -> dict:
    return {
        "id": id,
        "pregunta": "quién administra el canal",
        "debe_abstenerse": debe_abstenerse,
        "estado_servido": estado,
        "claves_recuperadas": list(recuperadas),
        "claves_payload": list(payload),
        "texto": texto,
        "afirmaciones": [dict(a) for a in afirmaciones],
        "regrado": dict(regrado or {}),
    }


def artefacto(
    respuestas: list[dict],
    *,
    estado: str = "RATIFICADO 2026-08-24 — prueba",
    prompt_version: int = 1,
    modelo: str = "deepseek-v4-flash",
    corpus_sha: str = SHA,
    sintetico=False,
) -> dict:
    return {
        "version": 1,
        "estado": estado,
        "prompt_version": prompt_version,
        "provider_model_pin": modelo,
        "corpus_sha": corpus_sha,
        "expected_clasificacion_sha256": "a" * 64,
        "generador_sintetico": sintetico,
        "respuestas": respuestas,
    }


def escribir(tmp_path: Path, datos: dict) -> Path:
    ruta = tmp_path / "answer_set.yaml"
    ruta.write_text(yaml.safe_dump(datos, allow_unicode=True), encoding="utf-8")
    return ruta


# ---------------------------------------------------------------------------
# The shipped artifact
# ---------------------------------------------------------------------------


class TestElArtefactoQueSeCommitea:
    """The checked-in shell: schema, pins, and no fabricated answers."""

    def test_el_artefacto_existe_y_no_esta_ratificado(self):
        """It ships as a BORRADOR because there are no real runs yet.

        The answers come from the GPU worker through the runbook. A file that
        said RATIFICADO with zero answers would make every downstream figure
        `n/d` while the report claimed the set had been reviewed.
        """
        assert answers.RUTA_ANSWER_SET.is_file()
        with pytest.raises(ConjuntoRespuestasNoRatificado) as fallo:
            cargar_conjunto_respuestas()
        assert "BORRADOR" in str(fallo.value)

    def test_el_artefacto_no_trae_respuestas_inventadas(self):
        datos = yaml.safe_load(answers.RUTA_ANSWER_SET.read_text(encoding="utf-8"))
        assert datos["respuestas"] == []
        assert datos["provider_model_pin"] == "deepseek-v4-flash"

    def test_un_set_vacio_no_publica_cifras(self, tmp_path):
        """`0/0` is not `0.00`. It is a measurement that never happened."""
        ruta = escribir(tmp_path, artefacto([]))
        with pytest.raises(RespuestasSinteticas) as fallo:
            answers.assert_publicable(cargar_conjunto_respuestas(ruta))
        assert "no ocurrió" in str(fallo.value)

    def test_un_generador_sintetico_no_publica_cifras(self, tmp_path):
        """A stand-in writes text engineered to pass every mechanical check."""
        ruta = escribir(tmp_path, artefacto([respuesta("R-1")], sintetico=True))
        with pytest.raises(RespuestasSinteticas) as fallo:
            answers.assert_publicable(cargar_conjunto_respuestas(ruta))
        assert "SINTÉTICO" in str(fallo.value)


# ---------------------------------------------------------------------------
# 9.1 — the deterministic half
# ---------------------------------------------------------------------------


class TestUniversoPostExclusion:
    """9.1 — invented citations are scored against the PAYLOAD, not the page."""

    def test_una_clave_recuperada_pero_excluida_cuenta_como_inventada(self, tmp_path):
        """The correction of 2026-08-23, as an executable assertion.

        `8548#3` was retrieved and then excluded by the classification gate, so
        the model can only have got it from a unit whose text was never in the
        prompt. Production REJECTS an answer citing it; an eval scored against
        the retrieved page would score it as correct and publish `0.00` for a
        system that abstains.
        """
        ruta = escribir(
            tmp_path,
            artefacto(
                [
                    respuesta(
                        "R-1",
                        texto="El canal se rige por [9750#1] y por [8548#3].",
                        recuperadas=("9750#1", "8548#3"),
                        payload=("9750#1",),
                    )
                ]
            ),
        )
        metricas = puntuar(cargar_conjunto_respuestas(ruta))
        assert metricas.n_claves_citadas == 2
        assert metricas.n_claves_inventadas == 1
        assert metricas.tasa_cita_inventada == 0.5
        assert metricas.respuestas_con_cita_inventada == ("R-1",)

    def test_una_respuesta_limpia_puntua_cero(self, tmp_path):
        ruta = escribir(tmp_path, artefacto([respuesta("R-1")]))
        metricas = puntuar(cargar_conjunto_respuestas(ruta))
        assert metricas.tasa_cita_inventada == 0.0
        assert metricas.respuestas_con_cita_inventada == ()

    def test_la_regla_de_afirmacion_sin_cita_es_la_del_pre_serve(self, tmp_path):
        """One rule, one implementation. A second copy would drift.

        The numerator and the denominator both come from `generacion`, which is
        what the pre-serve check runs, so the published rate describes the
        function production actually has.
        """
        cuerpo = textwrap.dedent(
            """\
            El consorcio administra el canal [9750#1].
            La asamblea aprueba el presupuesto anual."""
        )
        ruta = escribir(tmp_path, artefacto([respuesta("R-1", texto=cuerpo)]))
        metricas = puntuar(cargar_conjunto_respuestas(ruta))
        assert metricas.n_lineas_sustantivas == len(generacion.lineas_sustantivas(cuerpo))
        assert metricas.n_lineas_sin_cita == len(generacion.afirmaciones_sin_cita(cuerpo))
        assert metricas.n_lineas_sin_cita == 1
        assert metricas.tasa_afirmacion_sin_cita == 0.5

    def test_una_barra_espejada_del_spec_falla_con_una_sola_clave_inventada(self, tmp_path):
        """Generation spec: "A single invented citation blocks serving"."""
        ruta = escribir(
            tmp_path,
            artefacto(
                [
                    respuesta(
                        "R-1",
                        texto="Se rige por [9750#1] y [8548#3].",
                        recuperadas=("9750#1", "8548#3"),
                        payload=("9750#1",),
                    )
                ]
            ),
        )
        metricas = puntuar(cargar_conjunto_respuestas(ruta))
        por_nombre = {b.nombre: b for b in answers.barras(metricas)}
        assert por_nombre["invented-citation rate"].pasa is False


# ---------------------------------------------------------------------------
# 9.2 — n counts answers; the intra-rater floor
# ---------------------------------------------------------------------------


class TestNCuentaRespuestas:
    def test_el_minimo_ratificado_es_treinta_respuestas(self):
        assert N_MINIMO_RESPUESTAS == 30

    def test_pocas_respuestas_es_no_evaluable_aunque_sobren_afirmaciones(self, tmp_path):
        """Six verbose answers are not thirty answers.

        This is the sample inflation the design names explicitly: "n = 30 read
        as claims would be six or seven answers wearing a bigger number".
        """
        muchas = tuple(
            {"id": f"R-1-a{i}", "texto": "…", "clave": "9750#1", "grado": "sostenida"}
            for i in range(40)
        )
        ruta = escribir(tmp_path, artefacto([respuesta("R-1", afirmaciones=muchas)]))
        metricas = puntuar(cargar_conjunto_respuestas(ruta))
        assert metricas.n_afirmaciones == 40
        assert metricas.n_respuestas == 1
        assert not metricas.evaluable
        assert any("n_respuestas = 1" in m for m in metricas.motivos_no_evaluable)

    def test_la_distribucion_por_respuesta_se_publica(self, tmp_path):
        una = ({"id": "a", "texto": "…", "clave": "9750#1", "grado": "sostenida"},)
        dos = una + ({"id": "b", "texto": "…", "clave": "9750#1", "grado": "parcial"},)
        ruta = escribir(
            tmp_path,
            artefacto(
                [
                    respuesta("R-1", afirmaciones=una),
                    respuesta("R-2", afirmaciones=dos),
                    respuesta("R-3", afirmaciones=dos),
                ]
            ),
        )
        metricas = puntuar(cargar_conjunto_respuestas(ruta))
        assert metricas.distribucion_afirmaciones == {1: 1, 2: 2}


class TestAcuerdoIntraEvaluador:
    def test_el_piso_es_quince_afirmaciones_no_el_diez_por_ciento_pelado(self):
        """`max(15, ceil(0.10 * n))` — the floor, then the fraction."""
        assert muestra_de_regrado(30) == PISO_REGRADO == 15
        assert muestra_de_regrado(90) == 15
        assert muestra_de_regrado(200) == 20
        assert muestra_de_regrado(151) == 16

    def test_por_debajo_del_piso_el_acuerdo_es_not_evaluable(self, tmp_path):
        """Never a number. An agreement over 9 items moves 0.11 per disagreement."""
        pocas = tuple(
            {"id": f"a{i}", "texto": "…", "clave": "9750#1", "grado": "sostenida"} for i in range(5)
        )
        ruta = escribir(
            tmp_path,
            artefacto([respuesta("R-1", afirmaciones=pocas, regrado={"a0": "sostenida"})]),
        )
        metricas = puntuar(cargar_conjunto_respuestas(ruta))
        assert metricas.acuerdo_intra_evaluador is None
        assert any("not-evaluable" in m for m in metricas.motivos_no_evaluable)

    def test_con_muestra_suficiente_se_publica_el_acuerdo(self, tmp_path):
        afirmaciones = tuple(
            {"id": f"a{i}", "texto": "…", "clave": "9750#1", "grado": "sostenida"}
            for i in range(20)
        )
        # 16 re-grades over 20 claims clears max(15, 2); one of them disagrees.
        regrado = {f"a{i}": "sostenida" for i in range(15)}
        regrado["a15"] = "parcial"
        ruta = escribir(
            tmp_path,
            artefacto([respuesta("R-1", afirmaciones=afirmaciones, regrado=regrado)]),
        )
        metricas = puntuar(cargar_conjunto_respuestas(ruta))
        assert metricas.n_regradadas == 16
        assert metricas.acuerdos_regrado == 15
        assert metricas.acuerdo_intra_evaluador == pytest.approx(15 / 16)

    def test_un_regrado_de_una_afirmacion_inexistente_es_un_error_de_esquema(self, tmp_path):
        ruta = escribir(tmp_path, artefacto([respuesta("R-1", regrado={"fantasma": "sostenida"})]))
        with pytest.raises(ConjuntoRespuestasInvalido) as fallo:
            puntuar(cargar_conjunto_respuestas(ruta))
        assert "fantasma" in str(fallo.value)


# ---------------------------------------------------------------------------
# 9.3 — the pins
# ---------------------------------------------------------------------------


class TestPines:
    def test_los_tres_pines_coincidentes_no_levantan_nada(self, tmp_path):
        conjunto = cargar_conjunto_respuestas(escribir(tmp_path, artefacto([respuesta("R-1")])))
        verificar_pines(
            conjunto,
            prompt_version=1,
            provider_model_pin="deepseek-v4-flash",
            corpus_sha=SHA,
        )

    @pytest.mark.parametrize(
        "kwargs,esperado",
        [
            ({"prompt_version": 2}, "prompt_version"),
            ({"provider_model_pin": "otro-modelo"}, "provider_model_pin"),
            ({"corpus_sha": "9" * 40}, "corpus_sha"),
        ],
    )
    def test_cualquier_divergencia_refusa_nombrando_ambos_operandos(
        self, tmp_path, kwargs, esperado
    ):
        """Naming both operands is the whole usability of the refusal.

        "the pins do not match" sends somebody to read two files; naming what
        the artifact holds and what this run is sends them to the one that moved.
        """
        conjunto = cargar_conjunto_respuestas(escribir(tmp_path, artefacto([respuesta("R-1")])))
        base = {
            "prompt_version": 1,
            "provider_model_pin": "deepseek-v4-flash",
            "corpus_sha": SHA,
        }
        with pytest.raises(PinRespuestasDivergente) as fallo:
            verificar_pines(conjunto, **{**base, **kwargs})
        mensaje = str(fallo.value)
        assert esperado in mensaje
        assert "RE-GRADUAR" in mensaje, "the fix is a re-grade, never a re-scoring"


# ---------------------------------------------------------------------------
# 9.4 — end-to-end abstention, and the reclassification trigger
# ---------------------------------------------------------------------------


class TestAbstencionEndToEnd:
    def test_el_par_se_mide_sobre_la_salida_servida(self, tmp_path):
        ruta = escribir(
            tmp_path,
            artefacto(
                [
                    # should abstain and did
                    respuesta("R-1", estado="abstencion", debe_abstenerse=True),
                    # should abstain and did NOT — the false-confident answer
                    respuesta("R-2", estado="respuesta", debe_abstenerse=True),
                    # answerable and answered
                    respuesta("R-3", estado="respuesta", debe_abstenerse=False),
                    # answerable and abstained — costs precision
                    respuesta("R-4", estado="abstencion", debe_abstenerse=False),
                ]
            ),
        )
        par = puntuar(cargar_conjunto_respuestas(ruta)).par_e2e
        assert (par.debian_abstenerse, par.abstuvieron, par.aciertos) == (2, 2, 1)
        assert par.recall == 0.5
        assert par.precision == 0.5

    def test_una_abstencion_por_exclusion_se_reporta_aparte(self, tmp_path):
        """The design requires the privacy gate's contribution to be visible.

        It is a TRUE abstention for recall — nothing was served — and it counts
        against precision when the corpus did hold an applicable norm in an
        excluded unit. Both facts, reported where they happen.
        """
        ruta = escribir(
            tmp_path,
            artefacto(
                [
                    respuesta(
                        "R-1",
                        estado="abstencion",
                        debe_abstenerse=False,
                        recuperadas=("8548#3",),
                        payload=(),
                        texto="",
                    )
                ]
            ),
        )
        par = puntuar(cargar_conjunto_respuestas(ruta)).par_e2e
        assert par.abstenciones_por_exclusion == 1
        assert par.precision == 0.0

    def test_el_par_e2e_no_se_fusiona_con_el_de_recuperacion(self, tmp_path):
        """Its own key in the JSON, with what it was measured on stated."""
        ruta = escribir(
            tmp_path,
            artefacto([respuesta("R-1", estado="abstencion", debe_abstenerse=True)]),
        )
        conjunto = cargar_conjunto_respuestas(ruta)
        datos = answers.json_para(EntradaRespuestas(conjunto=conjunto, metricas=puntuar(conjunto)))
        assert datos["abstencion_e2e"]["medida_en"] == "salida servida, post-exclusión"
        assert "recall" in datos["abstencion_e2e"]


class TestReclasificacionRedispara:
    """9.4 — a widened allowlist must not reuse figures from a narrower one."""

    def seed(self, db, *, clasificacion_8548: str) -> None:
        db.execute(
            text(
                "INSERT INTO rag_corpus (corpus_sha, repo_url, manifest_version, "
                "articulos_declarados, activo) VALUES (:sha, 'u', '2', 2, true)"
            ),
            {"sha": SHA},
        )
        db.execute(
            text(
                "INSERT INTO rag_documento (corpus_sha, documento_id, tipo, es_secundaria, "
                "jurisdiccion, estado_vigencia, clasificacion) VALUES "
                "(:sha, 'ley-9750', 'ley-provincial', false, 'provincial', 'vigente', "
                "'publico')"
            ),
            {"sha": SHA},
        )
        db.execute(
            text(
                "INSERT INTO rag_documento (corpus_sha, documento_id, tipo, es_secundaria, "
                "jurisdiccion, estado_vigencia, clasificacion) VALUES "
                "(:sha, 'ley-8548', 'ley-provincial', false, 'provincial', 'vigente', :clas)"
            ),
            {"sha": SHA, "clas": clasificacion_8548},
        )
        db.execute(
            text(
                "INSERT INTO rag_unidad (corpus_sha, citation_key, documento_id, tipo_chunk, "
                "texto, texto_indexado, source_file, source_offset) VALUES "
                "(:sha, :key, :doc, 'articulo', 't', 't', 'f.md', 0)"
            ),
            [
                {"sha": SHA, "key": "9750#1", "doc": "ley-9750"},
                {"sha": SHA, "key": "8548#3", "doc": "ley-8548"},
            ],
        )
        db.flush()

    def test_el_payload_registrado_se_reverifica_contra_la_clasificacion_viva(self, db, tmp_path):
        """`corpus_sha` unmoved, payload moved — and the harness catches it.

        The artifact was graded when `ley-8548` was `privado`, so `8548#3` was
        excluded. Reclassifying it to `publico` widens every payload without
        touching a single corpus byte, and every invented-citation score in the
        artifact was computed against a universe that no longer exists.
        """
        self.seed(db, clasificacion_8548="publico")
        ruta = escribir(
            tmp_path,
            artefacto(
                [
                    respuesta(
                        "R-1",
                        recuperadas=("9750#1", "8548#3"),
                        payload=("9750#1",),  # graded under the NARROWER allowlist
                    )
                ]
            ),
        )
        with pytest.raises(PayloadDivergente) as fallo:
            answers.verificar_payload(db, cargar_conjunto_respuestas(ruta))
        mensaje = str(fallo.value)
        assert "8548#3" in mensaje
        assert "El corpus no se movió" in mensaje

    def test_un_payload_que_coincide_no_levanta_nada(self, db, tmp_path):
        self.seed(db, clasificacion_8548="privado")
        ruta = escribir(
            tmp_path,
            artefacto([respuesta("R-1", recuperadas=("9750#1", "8548#3"), payload=("9750#1",))]),
        )
        answers.verificar_payload(db, cargar_conjunto_respuestas(ruta))

    def test_cargar_y_puntuar_encadena_las_cuatro_verificaciones(self, db, tmp_path):
        self.seed(db, clasificacion_8548="privado")
        ruta = escribir(
            tmp_path,
            artefacto([respuesta("R-1", recuperadas=("9750#1", "8548#3"), payload=("9750#1",))]),
        )
        entrada = cargar_y_puntuar(
            db,
            ruta=ruta,
            prompt_version=1,
            provider_model_pin="deepseek-v4-flash",
            corpus_sha=SHA,
        )
        assert entrada.metricas is not None
        assert entrada.metricas.n_respuestas == 1


# ---------------------------------------------------------------------------
# Schema refusals
# ---------------------------------------------------------------------------


class TestEsquema:
    def test_un_payload_que_no_es_subconjunto_de_lo_recuperado_es_invalido(self, tmp_path):
        ruta = escribir(
            tmp_path,
            artefacto([respuesta("R-1", recuperadas=("9750#1",), payload=("9750#1", "8548#3"))]),
        )
        with pytest.raises(ConjuntoRespuestasInvalido) as fallo:
            cargar_conjunto_respuestas(ruta)
        assert "subset" in str(fallo.value)

    def test_una_respuesta_servida_vacia_es_invalida(self, tmp_path):
        """Every mechanical check passes vacuously on empty text."""
        ruta = escribir(tmp_path, artefacto([respuesta("R-1", texto="   ")]))
        with pytest.raises(ConjuntoRespuestasInvalido) as fallo:
            cargar_conjunto_respuestas(ruta)
        assert "empty text" in str(fallo.value)

    def test_ids_duplicados_son_invalidos(self, tmp_path):
        ruta = escribir(tmp_path, artefacto([respuesta("R-1"), respuesta("R-1")]))
        with pytest.raises(ConjuntoRespuestasInvalido):
            cargar_conjunto_respuestas(ruta)

    def test_un_grado_desconocido_es_invalido(self, tmp_path):
        ruta = escribir(
            tmp_path,
            artefacto(
                [
                    respuesta(
                        "R-1",
                        afirmaciones=(
                            {"id": "a", "texto": "…", "clave": "9750#1", "grado": "mas_o_menos"},
                        ),
                    )
                ]
            ),
        )
        with pytest.raises(ConjuntoRespuestasInvalido) as fallo:
            cargar_conjunto_respuestas(ruta)
        assert "mas_o_menos" in str(fallo.value)


# ---------------------------------------------------------------------------
# The report seam
# ---------------------------------------------------------------------------


class TestBloqueDelReporte:
    def test_sin_entrada_el_bloque_dice_por_que(self):
        bloque = "\n".join(answers.bloque_para(None))
        assert "not-evaluable" in bloque
        assert "worker con GPU" in bloque

    def test_una_entrada_incompleta_es_inconstruible(self):
        with pytest.raises(ConjuntoRespuestasInvalido):
            EntradaRespuestas(metricas=None, conjunto=None)

    def test_el_bloque_publica_n_respuestas_y_n_afirmaciones(self, tmp_path):
        una = ({"id": "a", "texto": "…", "clave": "9750#1", "grado": "sostenida"},)
        conjunto = cargar_conjunto_respuestas(
            escribir(tmp_path, artefacto([respuesta("R-1", afirmaciones=una)]))
        )
        bloque = "\n".join(
            answers.bloque_para(EntradaRespuestas(conjunto=conjunto, metricas=puntuar(conjunto)))
        )
        assert "n_respuestas = 1" in bloque
        assert "n_afirmaciones = 1" in bloque
        assert "deepseek-v4-flash" in bloque

    def test_la_barra_de_fidelidad_no_dicta_veredicto(self, tmp_path):
        """`fully-supported >= 0.95` is a PROPOSAL, printed and never scored."""
        una = ({"id": "a", "texto": "…", "clave": "9750#1", "grado": "sostenida"},)
        conjunto = cargar_conjunto_respuestas(
            escribir(tmp_path, artefacto([respuesta("R-1", afirmaciones=una)]))
        )
        metricas = puntuar(conjunto)
        por_nombre = {b.nombre: b for b in answers.barras(metricas)}
        assert por_nombre["fully-supported claim rate"].ratificada is False
        assert por_nombre["fully-supported claim rate"].pasa is None
        bloque = "\n".join(
            answers.bloque_para(EntradaRespuestas(conjunto=conjunto, metricas=metricas))
        )
        assert "barra_no_ratificada" in bloque
