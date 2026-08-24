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

**The BAR is unratified and this module issues no verdict.** It prints the
held-out figures, the proposed bar next to them, and the state
`barra_no_ratificada` (`routing.evaluar_barra`). The same-sample matrix is
printed too and is labelled `upper bound (fit on the scoring sample)` wherever
it appears, exactly as `ResultadoLOOCV`'s same-sample pair is.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from app.domains.conocimiento.embedding import Embedder
from app.domains.conocimiento.routing import (
    CLASES,
    ESTADO_BARRA_NO_RATIFICADA,
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
    if evaluacion.estado == ESTADO_BARRA_NO_RATIFICADA:
        lineas += [
            "**Estado: `barra_no_ratificada` — no verdict is issued.**",
            "",
            f"The proposed bar (`operational -> legal` <= "
            f"{evaluacion.barra.operational_a_legal_max}, overall >= "
            f"{evaluacion.barra.exactitud_minima}, design.md:175-186) is printed here next to "
            "the measured figures so the owner can fix the bar WITH the numbers in hand. It "
            "is a proposal until then (tasks.md 0.3 / design.md A4), and nothing in this "
            "pipeline turns it into a pass or a fail.",
        ]
    else:
        lineas.append(f"Veredicto: **{'PASA' if evaluacion.veredicto else 'NO PASA'}**")
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
        "exactitud_held_out": resultado.matriz.exactitud,
        "exactitud_same_sample": resultado.matriz_same_sample.exactitud,
        "barra": {
            "estado": evaluacion.estado,
            "ratificada": evaluacion.barra.ratificada,
            "operational_a_legal_max_propuesto": evaluacion.barra.operational_a_legal_max,
            "exactitud_minima_propuesta": evaluacion.barra.exactitud_minima,
            "veredicto": evaluacion.veredicto,
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


def ids_por_clase(items: Sequence[ItemRuta]) -> dict[str, list[str]]:
    """Traceability helper: which ratified ids sit in each class."""
    agrupado: dict[str, list[str]] = {clase: [] for clase in CLASES}
    for item in items:
        agrupado[item.clase_esperada].append(item.id)
    return agrupado
