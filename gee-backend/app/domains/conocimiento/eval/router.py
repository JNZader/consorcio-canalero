"""Router eval: load the ratified set, score it, render the confusion matrix.

`knowledge-question-routing` spec:83-104 and design.md G1 (:172-196). Three
refusals live here, and each one is a way a router eval could print a number
that means nothing:

**An unratified set is `not-evaluable`, not a warning next to a figure.**
routing spec:100-104. `cargar_router_set` raises `SetRouterNoRatificado` unless
the file's `estado` starts with `RATIFICADO`, and the report block prints that
word instead of numbers. A threshold scored on a set the owner has not reviewed
is a threshold fitted to whatever the author happened to write.

**A synthetic embedder is never a quality claim.** The block names the embedder
and its `sintetico` flag in its own header row. A hash-derived vector has no
class structure at all, so a confusion matrix built on one measures the
plumbing — which is worth running, and worth never confusing with a measurement
of the router.

**The BAR is RATIFIED (owner, 2026-08-24) and this module now prints a verdict.**
The held-out figures come first, the bar next to them, then PASA/NO PASA with
the failing components named. The `barra_no_ratificada` branch stays: a future
bar nobody has fixed re-enters it and gets no verdict. The same-sample matrix is
printed too and is labelled `upper bound (fit on the scoring sample)` wherever
it appears, exactly as `ResultadoLOOCV`'s same-sample pair is.

`EntradaRouter` at the bottom is what makes `make rag-eval` actually print this
block. Before it, `bloque_router` had no caller outside the tests: the command
the tasks file declared produced a report with no router section at all, which
is a measurement that exists in a module and nowhere a reader would look.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from app.domains.conocimiento.embedding import Embedder
from app.domains.conocimiento.routing import (
    CLASES,
    ESTADO_BARRA_NO_RATIFICADA,
    BarraRouter,
    EvaluacionBarra,
    ItemRuta,
    MatrizConfusion,
    ResultadoRouterLOOCV,
    SetRouterNoRatificado,
    calibrar_loocv,
    evaluar_barra,
    senales_desde,
)

RUTA_ROUTER_SET = Path(__file__).with_name("router_set.yaml")

#: The set is ratified at n = 49 with a floor of 10 per class. Both are checked
#: on load, because "n >= 40 with a floor of 10 per class, so the four-class
#: matrix has cells rather than anecdotes" (design.md:181) is a property of the
#: FILE, and a file edited down to 12 items would still parse.
N_MINIMO = 40
PISO_POR_CLASE = 10

ETIQUETA_UPPER_BOUND = "upper bound (fit on the scoring sample)"


def cargar_router_set(ruta: Path | None = None) -> tuple[ItemRuta, ...]:
    """Parse the labeled set, or REFUSE when it is not ratified.

    The refusal is the point. Everything downstream of this function produces
    numbers, and numbers produced from an unratified set are indistinguishable
    on the page from numbers produced from a ratified one.
    """
    datos = yaml.safe_load((ruta or RUTA_ROUTER_SET).read_text(encoding="utf-8")) or {}
    estado = str(datos.get("estado", ""))
    if not estado.startswith("RATIFICADO"):
        raise SetRouterNoRatificado(
            f"the router labeled set reports estado={estado!r}. Router thresholds are "
            "not-evaluable until the owner ratifies it (routing spec:100-104): a "
            "threshold scored on an unreviewed set is fitted to whatever its author "
            "happened to write."
        )

    items = tuple(
        ItemRuta(
            id=str(entrada["id"]),
            pregunta=str(entrada["pregunta"]),
            clase_esperada=str(entrada["clase_esperada"]),
            borde=bool(entrada.get("borde", False)),
        )
        for entrada in datos.get("preguntas", [])
    )

    desconocidas = sorted({item.clase_esperada for item in items} - set(CLASES))
    if desconocidas:
        raise SetRouterNoRatificado(f"{desconocidas} are not routing classes; {CLASES} are")
    if len(items) < N_MINIMO:
        raise SetRouterNoRatificado(
            f"n = {len(items)} is below the ratified floor of {N_MINIMO}: a four-class "
            "matrix over fewer items reports anecdotes as cells."
        )
    for clase in CLASES:
        cuantos = sum(1 for item in items if item.clase_esperada == clase)
        if cuantos < PISO_POR_CLASE:
            raise SetRouterNoRatificado(
                f"{clase!r} has {cuantos} items, below the ratified per-class floor of "
                f"{PISO_POR_CLASE}."
            )
    ids = [item.id for item in items]
    if len(set(ids)) != len(ids):
        raise SetRouterNoRatificado("duplicate ids: an item cannot be traced back to the draft")
    return items


def correr_eval_router(
    embedder: Embedder,
    *,
    ruta: Path | None = None,
    pasos: int = 7,
) -> ResultadoRouterLOOCV:
    """Load, embed once, calibrate by LOOCV. No verdict is produced here."""
    return calibrar_loocv(senales_desde(cargar_router_set(ruta), embedder), pasos=pasos)


def _fmt(valor: float | None, decimales: int = 3) -> str:
    return "n/a" if valor is None else f"{valor:.{decimales}f}"


def _tabla_matriz(matriz: MatrizConfusion) -> list[str]:
    lineas = [
        "| esperada \\ predicha | " + " | ".join(CLASES) + " | total |",
        "|---" * (len(CLASES) + 2) + "|",
    ]
    for esperada in CLASES:
        celdas = [str(matriz.celda(esperada, predicha)) for predicha in CLASES]
        lineas.append(
            f"| {esperada} | " + " | ".join(celdas) + f" | {matriz.total_esperado(esperada)} |"
        )
    return lineas


def bloque_router(
    resultado: ResultadoRouterLOOCV,
    embedder: Embedder,
    evaluacion: EvaluacionBarra | None = None,
) -> list[str]:
    """The markdown block for the eval report. Figures, never a verdict."""
    evaluacion = evaluacion or evaluar_barra(resultado)
    parametros = resultado.parametros_shipped
    lineas = [
        "## Router (question classification)",
        "",
        f"- Embedder: `{embedder.model_id}` · sintetico: **{bool(embedder.sintetico)}**",
        f"- n = {resultado.n} · shipped parameters (full set): umbral "
        f"{_fmt(parametros.umbral)} · banda {_fmt(parametros.banda)} · piso {_fmt(parametros.piso)}",
        "- Held-out figures come from leave-one-out, where each item was classified by "
        "centroids AND parameters selected without it.",
        "",
        "### Confusion matrix — held-out (LOOCV)",
        "",
    ]
    lineas += _tabla_matriz(resultado.matriz)
    lineas += [
        "",
        f"**`operational -> legal` = {resultado.matriz.operational_a_legal}** "
        f"({_fmt(resultado.matriz.fraccion_operational_a_legal)} of the operational items). "
        "This is the cell that fabricates an answer about a real person's debt, and it is "
        "reported explicitly because routing spec:85 requires it to be.",
        "",
        f"**`mixto -> legal` = {resultado.matriz.mixto_a_legal}** "
        f"({_fmt(resultado.matriz.fraccion_mixto_a_legal)} of the mixto items). A mixed "
        "question answered as purely legal drops its operational leg with no symptom on the "
        "page, which is why the ratified bar names this cell too.",
        "",
        f"Overall accuracy (held-out): {_fmt(resultado.matriz.exactitud)}",
        "",
        f"### Confusion matrix — {ETIQUETA_UPPER_BOUND}",
        "",
    ]
    lineas += _tabla_matriz(resultado.matriz_same_sample)
    lineas += [
        "",
        f"Overall accuracy ({ETIQUETA_UPPER_BOUND}): {_fmt(resultado.matriz_same_sample.exactitud)}",
        "",
        "### Bar",
        "",
    ]
    lineas += [
        f"- accuracy (held-out) >= {evaluacion.barra.exactitud_minima}",
        f"- `operational -> legal` <= {evaluacion.barra.operational_a_legal_max} (hard cell)",
        f"- `mixto -> legal` <= {evaluacion.barra.mixto_a_legal_max}",
        "",
    ]
    if evaluacion.estado == ESTADO_BARRA_NO_RATIFICADA:
        lineas += [
            "**Estado: `barra_no_ratificada` — no verdict is issued.**",
            "",
            "The bar above is printed next to the measured figures so the owner can fix it "
            "WITH the numbers in hand. Nothing in this pipeline turns an unratified bar into "
            "a pass or a fail (routing spec:100-104).",
        ]
    else:
        lineas += [
            "Ratificada por el owner el 2026-08-24 (tasks.md 0.3).",
            "",
            f"Veredicto: **{'PASA' if evaluacion.veredicto else 'NO PASA'}**",
        ]
        for fallo in evaluacion.componentes_fallidos:
            lineas.append(f"- falla: {fallo}")
    return lineas


def bloque_no_evaluable(motivo: str) -> list[str]:
    """What the report prints when the set is not ratified (spec:100-104)."""
    return [
        "## Router (question classification)",
        "",
        "**`not-evaluable`** — router thresholds were NOT scored.",
        "",
        motivo,
    ]


def a_json(
    resultado: ResultadoRouterLOOCV, evaluacion: EvaluacionBarra | None = None
) -> dict[str, Any]:
    """Machine-readable twin of the block. Same refusal, same labels."""
    evaluacion = evaluacion or evaluar_barra(resultado)

    def _matriz(matriz: MatrizConfusion) -> Mapping[str, Mapping[str, int]]:
        return {
            esperada: {predicha: matriz.celda(esperada, predicha) for predicha in CLASES}
            for esperada in CLASES
        }

    return {
        "n": resultado.n,
        "parametros_shipped": {
            "umbral": resultado.parametros_shipped.umbral,
            "banda": resultado.parametros_shipped.banda,
            "piso": resultado.parametros_shipped.piso,
        },
        "matriz_held_out": _matriz(resultado.matriz),
        "matriz_same_sample": _matriz(resultado.matriz_same_sample),
        "same_sample_label": ETIQUETA_UPPER_BOUND,
        "operational_a_legal": resultado.matriz.operational_a_legal,
        "fraccion_operational_a_legal": resultado.matriz.fraccion_operational_a_legal,
        "mixto_a_legal": resultado.matriz.mixto_a_legal,
        "fraccion_mixto_a_legal": resultado.matriz.fraccion_mixto_a_legal,
        "exactitud_held_out": resultado.matriz.exactitud,
        "exactitud_same_sample": resultado.matriz_same_sample.exactitud,
        "barra": {
            "estado": evaluacion.estado,
            "ratificada": evaluacion.barra.ratificada,
            "operational_a_legal_max": evaluacion.barra.operational_a_legal_max,
            "mixto_a_legal_max": evaluacion.barra.mixto_a_legal_max,
            "exactitud_minima": evaluacion.barra.exactitud_minima,
            "veredicto": evaluacion.veredicto,
            "componentes_fallidos": list(evaluacion.componentes_fallidos),
        },
        "folds": [
            {
                "id": fold.id,
                "clase_esperada": fold.clase_esperada,
                "clase_predicha": fold.clase_predicha,
            }
            for fold in resultado.folds
        ],
    }


# ---------------------------------------------------------------------------
# The seam the report renders through
# ---------------------------------------------------------------------------


#: What the report prints when nobody asked for a router run at all. Named and
#: printed rather than omitted: a report with no router section reads as a report
#: whose router was fine, and that is the exact confusion the `not-evaluable`
#: vocabulary exists to prevent.
MOTIVO_NO_CORRIDO = (
    "El bloque del router no se corrió en esta corrida: no se construyó un embebedor real. "
    "Para correrlo: `make rag-eval RAG_EVAL_PYTHON=venv-rag/bin/python`, que arma BGE-M3 y "
    "puntúa el set ratificado."
)


@dataclass(frozen=True)
class EntradaRouter:
    """A scored router run, or the stated reason there is none.

    One argument instead of three (`resultado`, `embedder`, `motivo`) because
    the three are not independent: a result without its embedder is a matrix
    whose provenance nobody can read, and the `sintetico` flag is exactly what
    separates "the router scores 0.755" from "the harness runs". Bundling them
    makes the illegal combination unconstructible.

    The report renders through here; it never computes. `renderizar_markdown` is
    asserted pure over its own AST, and embedding 49 questions inside a renderer
    would make the document a side effect of printing it.
    """

    resultado: ResultadoRouterLOOCV | None = None
    embedder: Embedder | None = None
    motivo_no_evaluable: str | None = None
    barra: BarraRouter | None = None

    def __post_init__(self) -> None:
        if (self.resultado is None) != (self.embedder is None):
            raise SetRouterNoRatificado(
                "a router result and the embedder that produced it travel together: a "
                "matrix without its embedder cannot say whether it measured the router "
                "or the plumbing."
            )
        if self.resultado is None and not self.motivo_no_evaluable:
            raise SetRouterNoRatificado(
                "a router entry with no result must name why: `not-evaluable` with no "
                "reason is indistinguishable from a section somebody forgot to fill in."
            )

    @classmethod
    def no_evaluable(cls, motivo: str) -> "EntradaRouter":
        return cls(motivo_no_evaluable=motivo)

    def evaluacion(self) -> EvaluacionBarra | None:
        if self.resultado is None:
            return None
        return (
            evaluar_barra(self.resultado)
            if self.barra is None
            else evaluar_barra(self.resultado, self.barra)
        )


def bloque_para(entrada: EntradaRouter | None) -> list[str]:
    """The router section of the report, always present, never invented."""
    if entrada is None:
        return bloque_no_evaluable(MOTIVO_NO_CORRIDO)
    if entrada.resultado is None or entrada.embedder is None:
        return bloque_no_evaluable(entrada.motivo_no_evaluable or MOTIVO_NO_CORRIDO)
    return bloque_router(entrada.resultado, entrada.embedder, entrada.evaluacion())


def json_para(entrada: EntradaRouter | None) -> dict[str, Any]:
    """The machine-readable twin of `bloque_para`. Same refusal, same reason."""
    if entrada is None:
        return {"evaluado": False, "motivo": MOTIVO_NO_CORRIDO}
    if entrada.resultado is None or entrada.embedder is None:
        return {"evaluado": False, "motivo": entrada.motivo_no_evaluable or MOTIVO_NO_CORRIDO}
    return {
        "evaluado": True,
        "embedder": {
            "modelo": entrada.embedder.model_id,
            "sintetico": bool(entrada.embedder.sintetico),
        },
        **a_json(entrada.resultado, entrada.evaluacion()),
    }


def ids_por_clase(items: Sequence[ItemRuta]) -> dict[str, list[str]]:
    """Traceability helper: which ratified ids sit in each class."""
    agrupado: dict[str, list[str]] = {clase: [] for clase in CLASES}
    for item in items:
        agrupado[item.clase_esperada].append(item.id)
    return agrupado
