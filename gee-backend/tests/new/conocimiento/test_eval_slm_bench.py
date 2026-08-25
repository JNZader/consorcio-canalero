"""Task 9.6b — the SLM bench harness: parity, refusals, and no verdict.

What the bench decides is whether the provider pin may move to a model the
deployment runs itself, which kills task 6.7's terms-verification dependency and
the external-provider surface entirely. So the harness is built around three
properties:

1. **parity** — same prompt, same corpus, same answer ids, same per-answer
   payload, two DIFFERENT pins. The only variable may be the generator;
2. **no figures without real runs** — both arms come from the GPU worker through
   the runbook, and a synthetic or empty arm is refused;
3. **no verdict** — the owner's ladder rule is transcribed and printed. Nothing
   here evaluates it, branches on it or advances a rung.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.domains.conocimiento.eval import slm_bench
from app.domains.conocimiento.eval.answers import (
    ConjuntoRespuestasNoRatificado,
    RespuestasSinteticas,
)
from app.domains.conocimiento.eval.slm_bench import (
    BenchSLMInvalido,
    cargar_bench,
    cargar_y_comparar,
    comparar,
)

SHA = "1" * 40


def _codigo_ejecutable() -> str:
    """The module's source with docstrings AND `#` comments stripped.

    Prose may name a later rung — the module's header transcribes the whole
    ladder, and it has to. What may not name one is anything that RUNS: a
    constant for rung 2 is rung 2 already committed to, before rung 1 has a
    measurement.
    """
    fuente = Path(slm_bench.__file__).read_text(encoding="utf-8")
    sin_docstrings = "".join(fuente.split('"""')[::2])
    return "\n".join(
        linea for linea in sin_docstrings.splitlines() if not linea.strip().startswith("#")
    )


def respuesta(id: str, *, texto: str, payload=("9750#1",), grados=("sostenida",)) -> dict:
    return {
        "id": id,
        "pregunta": "quién administra el canal",
        "debe_abstenerse": False,
        "estado_servido": "respuesta",
        "claves_recuperadas": list(payload),
        "claves_payload": list(payload),
        "texto": texto,
        "afirmaciones": [
            {"id": f"{id}-a{i}", "texto": "…", "clave": "9750#1", "grado": grado}
            for i, grado in enumerate(grados)
        ],
        "regrado": {},
    }


def brazo(pin: str, respuestas: list[dict], *, tps: float | None = 40.0) -> dict:
    return {
        "estado": "RATIFICADO 2026-08-24 — prueba",
        "prompt_version": 1,
        "provider_model_pin": pin,
        "corpus_sha": SHA,
        "expected_clasificacion_sha256": "a" * 64,
        "generador_sintetico": False,
        "tokens_por_segundo": tps,
        "respuestas": respuestas,
    }


LIMPIA = "El consorcio administra el canal [9750#1]."
SUCIA = "El consorcio administra el canal [9750#1] y algo más [8548#9]."


def bench_datos(**cambios) -> dict:
    base = {
        "version": 1,
        "estado": "RATIFICADO 2026-08-24 — prueba",
        "prompt_version": 1,
        "corpus_sha": SHA,
        "referencia": brazo("deepseek-v4-flash", [respuesta("R-1", texto=LIMPIA)], tps=60.0),
        "candidato": brazo(
            "Qwen3-8B-Instruct-Q5",
            [respuesta("R-1", texto=SUCIA, grados=("contradicha",))],
            tps=18.0,
        ),
    }
    base.update(cambios)
    return base


def escribir(tmp_path: Path, datos: dict) -> Path:
    ruta = tmp_path / "slm_bench.yaml"
    ruta.write_text(yaml.safe_dump(datos, allow_unicode=True), encoding="utf-8")
    return ruta


class TestElArtefactoQueSeCommitea:
    def test_ship_como_borrador_sin_corridas(self):
        """Neither arm can be produced by this machine, so neither is faked."""
        assert slm_bench.RUTA_BENCH.is_file()
        with pytest.raises(ConjuntoRespuestasNoRatificado) as fallo:
            cargar_bench()
        assert "GPU worker" in str(fallo.value)

    def test_el_shell_declara_los_dos_pines_del_primer_peldano(self):
        datos = yaml.safe_load(slm_bench.RUTA_BENCH.read_text(encoding="utf-8"))
        assert datos["referencia"]["provider_model_pin"] == slm_bench.PIN_REFERENCIA
        assert slm_bench.CANDIDATO_RUNG_1 in datos["candidato"]["provider_model_pin"]
        assert datos["referencia"]["respuestas"] == []
        assert datos["candidato"]["respuestas"] == []

    def test_los_peldanos_posteriores_no_estan_en_el_codigo(self):
        """Naming `Qwen3-1.7B` as a constant would put rung 2 before rung 1 ran.

        The ladder's whole rule is that a rung is reached only by clearing the
        one below it, and a constant in the module is a rung already committed to.
        """
        assert "1.7B" not in _codigo_ejecutable()
        assert "Qwen3-1.7B" not in _codigo_ejecutable()


class TestParidad:
    def test_un_bench_parejo_carga(self, tmp_path):
        bench = cargar_bench(escribir(tmp_path, bench_datos()))
        assert bench.referencia.pin == "deepseek-v4-flash"
        assert bench.candidato.tokens_por_segundo == 18.0

    def test_prompt_versions_distintas_refusan(self, tmp_path):
        datos = bench_datos()
        datos["candidato"]["prompt_version"] = 2
        with pytest.raises(BenchSLMInvalido) as fallo:
            cargar_bench(escribir(tmp_path, datos))
        assert "prompt" in str(fallo.value)

    def test_preguntas_distintas_refusan(self, tmp_path):
        """Two arms over different questions are two measurements of two things."""
        datos = bench_datos()
        datos["candidato"]["respuestas"] = [respuesta("R-9", texto=LIMPIA)]
        with pytest.raises(BenchSLMInvalido) as fallo:
            cargar_bench(escribir(tmp_path, datos))
        assert "R-1" in str(fallo.value) or "R-9" in str(fallo.value)

    def test_payloads_distintos_refusan(self, tmp_path):
        """A model handed less context is not a worse model."""
        datos = bench_datos()
        datos["candidato"]["respuestas"] = [
            respuesta("R-1", texto=LIMPIA, payload=("9750#1", "9750#2"))
        ]
        with pytest.raises(BenchSLMInvalido) as fallo:
            cargar_bench(escribir(tmp_path, datos))
        assert "payloads distintos" in str(fallo.value)

    def test_el_mismo_pin_en_los_dos_brazos_refusa(self, tmp_path):
        """A model benched against itself measures sampling variance."""
        datos = bench_datos()
        datos["candidato"]["provider_model_pin"] = "deepseek-v4-flash"
        with pytest.raises(BenchSLMInvalido) as fallo:
            cargar_bench(escribir(tmp_path, datos))
        assert "mismo pin" in str(fallo.value)

    def test_un_solo_brazo_refusa(self, tmp_path):
        datos = bench_datos()
        datos["candidato"] = None
        with pytest.raises(BenchSLMInvalido) as fallo:
            cargar_bench(escribir(tmp_path, datos))
        assert "un solo brazo" in str(fallo.value)


class TestSinCorridasRealesNoPublica:
    def test_un_brazo_sintetico_refusa_nombrando_cual(self, tmp_path):
        datos = bench_datos()
        datos["candidato"]["generador_sintetico"] = True
        with pytest.raises(RespuestasSinteticas) as fallo:
            cargar_y_comparar(escribir(tmp_path, datos))
        assert "candidato" in str(fallo.value)

    def test_un_brazo_vacio_refusa(self, tmp_path):
        """Parity holds for two empty arms, which is exactly the trap.

        Both cover "the same" (empty) question set, so `verificar_paridad`
        passes — and every rate would come out `n/d` beside a table that looks
        like a comparison. The emptiness check is what closes it.
        """
        datos = bench_datos()
        datos["referencia"]["respuestas"] = []
        datos["candidato"]["respuestas"] = []
        with pytest.raises(RespuestasSinteticas) as fallo:
            cargar_y_comparar(escribir(tmp_path, datos))
        assert "referencia" in str(fallo.value)


class TestLaTabla:
    def test_las_siete_filas_del_owner_estan(self, tmp_path):
        bench = cargar_bench(escribir(tmp_path, bench_datos()))
        filas, _, _ = comparar(bench)
        nombres = [fila.metrica for fila in filas]
        assert "invented-citation rate" in nombres
        assert "uncited-claim rate" in nombres
        assert any("groundedness" in n for n in nombres)
        assert any("citation-precision" in n for n in nombres)
        assert "abstención e2e recall" in nombres
        assert "abstención e2e precision" in nombres
        assert "tokens/s" in nombres

    def test_el_delta_se_calcula_candidato_menos_referencia(self, tmp_path):
        """The candidate here invents a key and the reference does not."""
        bench = cargar_bench(escribir(tmp_path, bench_datos()))
        filas, _, _ = comparar(bench)
        por_metrica = {fila.metrica: fila for fila in filas}
        inventadas = por_metrica["invented-citation rate"]
        assert inventadas.referencia == 0.0
        assert inventadas.candidato == 0.5
        assert inventadas.delta == 0.5
        assert inventadas.mayor_es_mejor is False

    def test_groundedness_es_el_complemento_de_contradichas(self, tmp_path):
        bench = cargar_bench(escribir(tmp_path, bench_datos()))
        filas, ref, can = comparar(bench)
        por_metrica = {fila.metrica: fila for fila in filas}
        fila = por_metrica["groundedness (1 - contradichas)"]
        assert fila.referencia == 1.0 - (ref.tasa_contradicha or 0.0)
        assert fila.candidato == 1.0 - (can.tasa_contradicha or 0.0)
        assert fila.candidato == 0.0, "the candidate's one claim was graded contradicha"

    def test_tokens_por_segundo_se_transporta_nunca_se_mide_aca(self, tmp_path):
        """This process has no GPU; timing a report would time the report."""
        datos = bench_datos()
        datos["candidato"]["tokens_por_segundo"] = None
        bench = cargar_bench(escribir(tmp_path, datos))
        filas, _, _ = comparar(bench)
        fila = {f.metrica: f for f in filas}["tokens/s"]
        assert fila.candidato is None
        assert fila.delta is None


class TestNoEmiteVeredicto:
    def test_la_regla_de_escalera_se_transcribe_y_se_imprime(self, tmp_path):
        bench = cargar_bench(escribir(tmp_path, bench_datos()))
        bloque = "\n".join(slm_bench.bloque_para(bench))
        assert "nunca saltea un peldaño" in bloque
        assert "task 6.7" in bloque or "6.7" in bloque
        assert "no emite veredicto" in bloque

    def test_el_piso_de_seguridad_viaja_con_las_cifras(self, tmp_path):
        """Why a weaker generator is admissible at all is part of the table."""
        bench = cargar_bench(escribir(tmp_path, bench_datos()))
        bloque = "\n".join(slm_bench.bloque_para(bench))
        assert "POST-HOC" in bloque
        assert "fabricación silenciosamente confiada" in bloque

    def test_el_json_no_trae_veredicto(self, tmp_path):
        bench = cargar_bench(escribir(tmp_path, bench_datos()))
        datos = slm_bench.json_para(bench)
        assert datos["veredicto"] is None
        assert datos["regla_escalera"] == slm_bench.REGLA_ESCALERA

    def test_sin_bench_el_bloque_dice_por_que_y_repite_la_regla(self):
        bloque = "\n".join(slm_bench.bloque_para(None))
        assert "not-evaluable" in bloque
        assert "worker con GPU" in bloque
        assert "escalera" in bloque

    def test_ninguna_rama_del_modulo_decide_mover_el_pin(self):
        """A structural assertion, because this is the failure that would be silent.

        The module may PRINT the ladder; it may not act on it. A branch here that
        advanced a rung would move the provider pin — the single highest-impact
        decision in this change — without the owner in the loop.
        """
        codigo = _codigo_ejecutable()
        for prohibido in ("mover_pin", "PIN_NUEVO", "aprobar", "promover"):
            assert prohibido not in codigo


def test_los_dos_artefactos_comparten_esquema_de_brazo():
    """The arms are parsed by `answers.py`'s loader, not by a second parser.

    A parallel parser would be a second set of schema rules, and the ones in
    `answers.py` are what the invented-citation and uncited-claim scores rest on
    — so a bench with its own parser would be a way to get a figure past them.
    """
    fuente = Path(slm_bench.__file__).read_text(encoding="utf-8")
    assert "cargar_conjunto_respuestas" in fuente
    assert "yaml.safe_load" in fuente  # only for the bench's own envelope
