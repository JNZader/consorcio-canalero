"""SLM candidate bench: the same graded set, two generators, one table.

Task 9.6b (owner-requested, 2026-08-23).

The question is whether the ANSWER-GENERATION call can move from a hosted
provider to a model the deployment runs itself. That is not a preference: moving
the pin kills task 6.7's terms-verification dependency and the external-provider
surface entirely, which is the largest single reduction in this system's attack
and compliance area. It is also the kind of decision that gets made on vibes, so
it is made here on one artifact instead.

**The ladder is the owner's and is TRANSCRIBED, not re-decided.** `REGLA_ESCALERA`
below is a constant this module prints; nothing in this file evaluates it,
branches on it, or advances a rung. Every rung is decided by the same graded
artifact, in order, and the ladder never skips one.

**Both arms run against the same everything.** Same prompt version, same payloads,
same graders, same answer ids — enforced by `verificar_paridad`, because the only
way this comparison means anything is if the single variable is the generator.
Two arms whose answer sets differ are two measurements of two things, printed as
if they were one.

**Neither arm publishes without real runs.** `assert_publicable` refuses a
synthetic generator and refuses an empty arm, exactly as `eval/answers.py` does —
the answers come from the GPU worker through the runbook. A bench is the place
where a stand-in would be most tempting (the point is to compare two generators
that cost money and time) and therefore the place where the refusal has to be
loudest.

**The safety floor that makes small models viable AT ALL is stated with the
figures**, because a reader deciding on this table is entitled to know why a
weaker generator is even on it: citation enforcement (U5) validates every
citation against the payload post-hoc, so a weaker generator degrades into more
rejections and abstentions — visible failures — never into silently confident
fabrication.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.domains.conocimiento.eval.answers import (
    ConjuntoRespuestas,
    ConjuntoRespuestasInvalido,
    ConjuntoRespuestasNoRatificado,
    MetricasRespuestas,
    RespuestasSinteticas,
    assert_publicable,
    puntuar,
)

RUTA_BENCH = Path(__file__).with_name("slm_bench.yaml")

#: The reference arm is the pin currently in production config.
PIN_REFERENCIA = "deepseek-v4-flash"

#: The first candidate rung the owner named. Later rungs are NOT listed as
#: constants: naming `Qwen3-1.7B` here would put the second rung in the code
#: before the first one has a measurement, and the ladder's whole rule is that a
#: rung is reached only by clearing the one below it.
CANDIDATO_RUNG_1 = "Qwen3-8B-Instruct"

#: The owner's decision rule, TRANSCRIBED. Printed by the report; never evaluated
#: here. This module measures; it does not move a pin.
REGLA_ESCALERA = (
    "Si el SLM despeja las MISMAS barras que la referencia, el pin del proveedor "
    "PUEDE mudarse al SLM embebido — lo que mata la dependencia de verificación "
    "de términos (task 6.7) y la superficie de proveedor externo por completo. "
    "Recién entonces se banca un peldaño MÁS CHICO (≤2B) sobre este mismo "
    "artefacto, y sólo si ESE aguanta, un ≤1B afinado pasa a ser un proyecto "
    "(destilación desde el corpus — cambio aparte, no éste). La escalera nunca "
    "saltea un peldaño, y cada peldaño lo decide este mismo artefacto graduado, "
    "nunca una impresión."
)

#: Why a weaker generator is admissible at all here.
PISO_DE_SEGURIDAD = (
    "La verificación de citas (U5) valida cada cita contra el payload POST-HOC, "
    "así que un generador más débil degrada en más rechazos y más abstenciones "
    "— fallas VISIBLES — nunca en fabricación silenciosamente confiada. Ese piso "
    "es lo que hace que un modelo chico sea siquiera evaluable acá."
)


class BenchSLMInvalido(RuntimeError):
    """The two arms are not comparable, so the table would compare nothing."""


@dataclass(frozen=True)
class BrazoBench:
    """One generator's arm: its pin, its graded answers and its throughput."""

    nombre: str
    pin: str
    conjunto: ConjuntoRespuestas
    #: Measured on the worker, carried rather than computed: this process has no
    #: GPU and timing a report would time the report.
    tokens_por_segundo: float | None


@dataclass(frozen=True)
class BenchSLM:
    estado: str
    prompt_version: int
    corpus_sha: str
    referencia: BrazoBench
    candidato: BrazoBench


def _brazo(crudo: Any, nombre: str) -> BrazoBench:
    from app.domains.conocimiento.eval import answers as modulo_answers

    if crudo is None:
        raise BenchSLMInvalido(f"falta el brazo {nombre!r}: un bench de un solo brazo no compara")
    datos = dict(crudo)
    tps = datos.pop("tokens_por_segundo", None)
    pin = str(datos.get("provider_model_pin", ""))
    # Reuse the answer-set loader wholesale rather than a parallel parser: the
    # arms must be validated by the SAME rules the single-arm eval uses, or the
    # bench becomes a way to get a figure past the checks answers.py enforces.
    conjunto = _conjunto_desde(datos, modulo_answers)
    return BrazoBench(
        nombre=nombre,
        pin=pin,
        conjunto=conjunto,
        tokens_por_segundo=None if tps is None else float(tps),
    )


def _conjunto_desde(datos: dict[str, Any], modulo_answers: Any) -> ConjuntoRespuestas:
    """Parse an inline arm through `answers.cargar_conjunto_respuestas`.

    Written to a temporary file rather than reimplemented, because a second
    parser is a second set of schema rules — and the ones in `answers.py` are the
    ones the invented-citation and uncited-claim scores depend on.
    """
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", encoding="utf-8", delete=False) as tmp:
        yaml.safe_dump(datos, tmp, allow_unicode=True)
        ruta = Path(tmp.name)
    try:
        return modulo_answers.cargar_conjunto_respuestas(ruta)
    finally:
        ruta.unlink(missing_ok=True)


def cargar_bench(ruta: Path | None = None) -> BenchSLM:
    """Load both arms, or refuse. Unratified arms refuse through `answers.py`."""
    ruta = ruta or RUTA_BENCH
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
    estado = str(datos.get("estado", ""))
    if not estado.startswith("RATIFICADO"):
        raise ConjuntoRespuestasNoRatificado(
            f"{ruta.name} reports estado={estado!r}. The SLM bench decides whether "
            "the provider pin moves, so it is scored only from an owner-ratified "
            "artifact — and its answers come from REAL runs of both models on the "
            "GPU worker (runbook G9), never from this harness."
        )
    bench = BenchSLM(
        estado=estado,
        prompt_version=int(datos.get("prompt_version", 0)),
        corpus_sha=str(datos.get("corpus_sha", "")),
        referencia=_brazo(datos.get("referencia"), "referencia"),
        candidato=_brazo(datos.get("candidato"), "candidato"),
    )
    verificar_paridad(bench)
    return bench


def verificar_paridad(bench: BenchSLM) -> None:
    """Same prompt, same corpus, same answer ids — or the table compares nothing.

    The single variable has to be the generator. Two arms over different answer
    sets are two measurements of two different things, and printing them side by
    side is the most convincing way to publish a comparison nobody made.
    """
    for brazo in (bench.referencia, bench.candidato):
        if brazo.conjunto.prompt_version != bench.prompt_version:
            raise BenchSLMInvalido(
                f"el brazo {brazo.nombre!r} corrió con prompt_version "
                f"{brazo.conjunto.prompt_version} y el bench declara "
                f"{bench.prompt_version}: el prompt es parte de lo que se compara, "
                "así que cambiarlo entre brazos mide dos sistemas, no dos modelos."
            )
        if brazo.conjunto.corpus_sha != bench.corpus_sha:
            raise BenchSLMInvalido(
                f"el brazo {brazo.nombre!r} está pineado a corpus_sha "
                f"{brazo.conjunto.corpus_sha!r} y el bench a {bench.corpus_sha!r}"
            )

    ids_ref = tuple(r.id for r in bench.referencia.conjunto.respuestas)
    ids_can = tuple(r.id for r in bench.candidato.conjunto.respuestas)
    if set(ids_ref) != set(ids_can):
        faltan = sorted(set(ids_ref) ^ set(ids_can))
        raise BenchSLMInvalido(
            f"los dos brazos no cubren las mismas preguntas: {faltan[:10]}"
            + (f" (+{len(faltan) - 10} more)" if len(faltan) > 10 else "")
            + ". La única variable del bench tiene que ser el generador."
        )

    if bench.referencia.pin == bench.candidato.pin:
        raise BenchSLMInvalido(
            f"los dos brazos declaran el mismo pin ({bench.referencia.pin!r}). "
            "Un bench de un modelo contra sí mismo mide la varianza del muestreo "
            "y se lee como una comparación."
        )

    # The payload each arm saw must also match, per answer. Two generators handed
    # different context are not two generators being compared: the weaker one may
    # simply have been given less to work with.
    por_id_ref = {
        r.id: tuple(sorted(r.claves_payload)) for r in bench.referencia.conjunto.respuestas
    }
    for respuesta in bench.candidato.conjunto.respuestas:
        esperado = por_id_ref[respuesta.id]
        if tuple(sorted(respuesta.claves_payload)) != esperado:
            raise BenchSLMInvalido(
                f"{respuesta.id}: los dos brazos vieron payloads distintos "
                f"({list(esperado)} vs {sorted(respuesta.claves_payload)}). Un "
                "modelo al que se le entregó menos contexto no es un modelo peor."
            )


def assert_bench_publicable(bench: BenchSLM) -> None:
    """Neither arm may be synthetic, and neither may be empty.

    A bench is where a stand-in is most tempting — the whole point is to avoid
    paying for two real runs — so it is where the refusal has to be loudest.
    """
    for brazo in (bench.referencia, bench.candidato):
        try:
            assert_publicable(brazo.conjunto)
        except RespuestasSinteticas as exc:
            raise RespuestasSinteticas(f"brazo {brazo.nombre!r}: {exc}") from exc


@dataclass(frozen=True)
class FilaComparacion:
    metrica: str
    referencia: float | None
    candidato: float | None
    #: `True` when higher is better, so the report can render the delta's SIGN
    #: without the reader having to remember which way each metric points.
    mayor_es_mejor: bool

    @property
    def delta(self) -> float | None:
        if self.referencia is None or self.candidato is None:
            return None
        return self.candidato - self.referencia


def comparar(
    bench: BenchSLM,
) -> tuple[tuple[FilaComparacion, ...], MetricasRespuestas, MetricasRespuestas]:
    """The one comparison table the owner's rule reads. No verdict is issued here."""
    ref = puntuar(bench.referencia.conjunto)
    can = puntuar(bench.candidato.conjunto)
    filas = (
        FilaComparacion(
            "citation-precision (sostenidas)", ref.tasa_sostenida, can.tasa_sostenida, True
        ),
        FilaComparacion(
            "invented-citation rate", ref.tasa_cita_inventada, can.tasa_cita_inventada, False
        ),
        FilaComparacion(
            "uncited-claim rate", ref.tasa_afirmacion_sin_cita, can.tasa_afirmacion_sin_cita, False
        ),
        FilaComparacion(
            "groundedness (1 - contradichas)", _groundedness(ref), _groundedness(can), True
        ),
        FilaComparacion("abstención e2e recall", ref.par_e2e.recall, can.par_e2e.recall, True),
        FilaComparacion(
            "abstención e2e precision", ref.par_e2e.precision, can.par_e2e.precision, True
        ),
        FilaComparacion(
            "tokens/s",
            bench.referencia.tokens_por_segundo,
            bench.candidato.tokens_por_segundo,
            True,
        ),
    )
    return filas, ref, can


def _groundedness(metricas: MetricasRespuestas) -> float | None:
    """`1 - contradicted`. Reported as its own row because the design names it.

    Not a fourth independent judgment: it is the complement of the contradicted
    rate, which is the grade that says the cited unit says the opposite. Naming
    it that way is what makes the row comparable to the literature the owner will
    read the candidate's own numbers in.
    """
    tasa = metricas.tasa_contradicha
    return None if tasa is None else 1.0 - tasa


def _fmt(valor: float | None, decimales: int = 3) -> str:
    return "n/d" if valor is None else f"{valor:.{decimales}f}"


MOTIVO_NO_CORRIDO = (
    "El bench de SLM no se corrió en esta corrida: no se pasó `--slm-bench`. "
    "Los dos brazos son corridas REALES — el pin de referencia y el candidato "
    "embebido, mismo prompt, mismos payloads, mismos graders — y las produce el "
    "worker con GPU (runbook G9)."
)


def bloque_para(bench: BenchSLM | None, motivo: str | None = None) -> list[str]:
    """The bench section of the report: always present, never invented."""
    cabecera = ["## Bench de SLM candidato (task 9.6b)", ""]
    if bench is None:
        return cabecera + [
            "**`not-evaluable`** — el bench NO se puntuó.",
            "",
            motivo or MOTIVO_NO_CORRIDO,
            "",
            f"> **Regla de escalera (del owner, transcripta):** {REGLA_ESCALERA}",
        ]

    filas, ref, can = comparar(bench)
    lineas = cabecera + [
        f"- estado: {bench.estado}",
        f"- prompt_version `{bench.prompt_version}` · corpus_sha `{bench.corpus_sha}`",
        f"- **referencia**: `{bench.referencia.pin}` · "
        f"n_respuestas {ref.n_respuestas} · n_afirmaciones {ref.n_afirmaciones}",
        f"- **candidato**: `{bench.candidato.pin}` · "
        f"n_respuestas {can.n_respuestas} · n_afirmaciones {can.n_afirmaciones}",
        "",
        "| métrica | referencia | candidato | Δ (candidato − referencia) | mejor si |",
        "|---|---:|---:|---:|---|",
    ]
    for fila in filas:
        delta = "n/d" if fila.delta is None else f"{fila.delta:+.3f}"
        lineas.append(
            f"| {fila.metrica} | {_fmt(fila.referencia)} | {_fmt(fila.candidato)} "
            f"| {delta} | {'mayor' if fila.mayor_es_mejor else 'menor'} |"
        )

    lineas += [
        "",
        "> Los dos brazos corrieron con el **mismo prompt, los mismos payloads y "
        "los mismos graders** sobre las mismas preguntas — `verificar_paridad` lo "
        "exige, porque la única variable del bench tiene que ser el generador.",
        "",
        f"> **Regla de escalera (del owner, transcripta):** {REGLA_ESCALERA}",
        "",
        f"> **Piso de seguridad:** {PISO_DE_SEGURIDAD}",
        "",
        "> Este bloque **no emite veredicto**: mide. Mover el pin es una decisión "
        "del owner sobre esta tabla, y nada en este módulo la toma.",
    ]
    return lineas


def json_para(bench: BenchSLM | None, motivo: str | None = None) -> dict[str, Any]:
    """The machine-readable twin. Same refusal, same absence of a verdict."""
    if bench is None:
        return {
            "evaluado": False,
            "motivo": motivo or MOTIVO_NO_CORRIDO,
            "regla_escalera": REGLA_ESCALERA,
        }
    filas, ref, can = comparar(bench)
    return {
        "evaluado": True,
        "estado": bench.estado,
        "prompt_version": bench.prompt_version,
        "corpus_sha": bench.corpus_sha,
        "referencia": {
            "pin": bench.referencia.pin,
            "n_respuestas": ref.n_respuestas,
            "n_afirmaciones": ref.n_afirmaciones,
            "tokens_por_segundo": bench.referencia.tokens_por_segundo,
        },
        "candidato": {
            "pin": bench.candidato.pin,
            "n_respuestas": can.n_respuestas,
            "n_afirmaciones": can.n_afirmaciones,
            "tokens_por_segundo": bench.candidato.tokens_por_segundo,
        },
        "filas": [
            {
                "metrica": fila.metrica,
                "referencia": fila.referencia,
                "candidato": fila.candidato,
                "delta": fila.delta,
                "mayor_es_mejor": fila.mayor_es_mejor,
            }
            for fila in filas
        ],
        "regla_escalera": REGLA_ESCALERA,
        "piso_de_seguridad": PISO_DE_SEGURIDAD,
        "veredicto": None,
    }


def cargar_y_comparar(ruta: Path | None = None) -> BenchSLM:
    """Load, check parity, refuse a synthetic or empty arm. Then hand it over."""
    bench = cargar_bench(ruta)
    assert_bench_publicable(bench)
    return bench


__all__ = [
    "BenchSLM",
    "BenchSLMInvalido",
    "BrazoBench",
    "CANDIDATO_RUNG_1",
    "ConjuntoRespuestasInvalido",
    "FilaComparacion",
    "PIN_REFERENCIA",
    "PISO_DE_SEGURIDAD",
    "REGLA_ESCALERA",
    "RUTA_BENCH",
    "bloque_para",
    "cargar_bench",
    "cargar_y_comparar",
    "comparar",
    "json_para",
    "verificar_paridad",
]
