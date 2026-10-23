"""The recorded bar of the no-GPU arm: rank order is a measured privilege.

The norms surface (`normas.py`) serves `bm25_sin_ce`, which is BM25 candidate
generation with no cross-encoder. Candidate generation was never measured as a
ranking, so by default the surface returns its units sorted by `citation_key`
and shows no rank, no score and no relevance-implying position. This artifact is
what can change that, and only for ONE corpus SHA at a time.

It copies the pattern of `umbral_abstencion.yaml`: a checked-in file that carries
its own pins, so a reader can tell what a figure was measured against without
finding the run that produced it. It is never hand-typed to unlock the surface.
`derivar_desde` builds it from a scored run, and refuses the runs that cannot
honestly decide the bar (a synthetic snapshot, a `--allow-synthetic` smoke run,
or gold keys that moved with the corpus pin).

**What `superada` means, and it is re-checked on every load:**

* the artifact is for the arm `bm25_sin_ce`, and never for `bm25_ce` — the CUDA
  arm's 31/34 was measured with a ranker this arm does not have;
* its `corpus_sha` is the snapshot being served;
* hit@5 on the answerable gold items is at or above `BARRA_HIT_RATE`;
* norma-vs-secundaria and vigencia-correctness are both at `BARRA_SEPARACION` /
  `BARRA_VIGENCIA` (1.00).

A file that says `superada` while carrying a figure under the bar is refused, not
believed: the state word is a claim and the figures are the evidence.

This module sits on the SERVING side of the eval boundary. It imports the bar
constants from the harness and nothing from `repository`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.domains.conocimiento.eval.harness import (
    BARRA_HIT_RATE,
    BARRA_SEPARACION,
    BARRA_VIGENCIA,
)
from app.domains.conocimiento.service import MODO_SIN_GPU

RUTA_BARRA = Path(__file__).with_name("barra_sin_gpu.yaml")

ESTADO_NO_MEDIDO = "no_medido"
ESTADO_SUPERADA = "superada"
ESTADO_NO_SUPERADA = "no_superada"
ESTADOS = (ESTADO_NO_MEDIDO, ESTADO_SUPERADA, ESTADO_NO_SUPERADA)

_CAMPOS_MEDIDOS = (
    "corpus_sha",
    "n_respondibles",
    "hit_rate_at_5",
    "separacion_norma_secundaria",
    "vigencia_correcta",
)


class BarraInvalida(RuntimeError):
    """The artifact does not satisfy its own header contract."""


class BarraNoSuperada(RuntimeError):
    """The artifact does not show the bar cleared for the requested snapshot.

    The message names the failed condition, because "the bar is not met" sends a
    person to read the artifact and a named condition sends them to the figure.
    """


@dataclass(frozen=True)
class BarraSinGpu:
    """The artifact, exactly as it is on disk."""

    estado: str
    modo: str
    corpus_sha: str | None
    n_respondibles: int | None
    hit_rate_at_5: float | None
    separacion_norma_secundaria: float | None
    vigencia_correcta: float | None
    metodologia: str
    motivo: str


def _opcional(datos: dict[str, Any], campo: str, tipo: type) -> Any:
    valor = datos.get(campo)
    return None if valor is None else tipo(valor)


def cargar_barra(ruta: Path | None = None) -> BarraSinGpu:
    """Parse the artifact and check its header contract.

    `no_medido` carries no measurement at all: a figure stored under it is the
    worst of both worlds, because nobody ratified it and it sits there to be
    read. `superada` and `no_superada` carry the whole measurement header.
    """
    ruta = ruta or RUTA_BARRA
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
    estado = str(datos.get("estado", ESTADO_NO_MEDIDO))
    if estado not in ESTADOS:
        raise BarraInvalida(
            f"{ruta.name}: estado {estado!r} desconocido (esperado uno de {ESTADOS})"
        )

    artefacto = BarraSinGpu(
        estado=estado,
        modo=str(datos.get("modo", MODO_SIN_GPU)),
        corpus_sha=_opcional(datos, "corpus_sha", str),
        n_respondibles=_opcional(datos, "n_respondibles", int),
        hit_rate_at_5=_opcional(datos, "hit_rate_at_5", float),
        separacion_norma_secundaria=_opcional(datos, "separacion_norma_secundaria", float),
        vigencia_correcta=_opcional(datos, "vigencia_correcta", float),
        metodologia=str(datos.get("metodologia", "")),
        motivo=str(datos.get("motivo", "")),
    )

    if estado == ESTADO_NO_MEDIDO:
        presentes = [campo for campo in _CAMPOS_MEDIDOS if getattr(artefacto, campo) is not None]
        if presentes:
            raise BarraInvalida(
                f"{ruta.name}: estado {ESTADO_NO_MEDIDO!r} con valores guardados "
                f"({', '.join(presentes)}). Un número bajo 'no medido' es un número que "
                "nadie ratificó y que está ahí para que alguien lo lea."
            )
        return artefacto

    faltantes = [campo for campo in _CAMPOS_MEDIDOS if getattr(artefacto, campo) is None]
    if not artefacto.metodologia:
        faltantes.append("metodologia")
    if faltantes:
        raise BarraInvalida(
            f"{ruta.name}: estado {estado!r} con el encabezado incompleto "
            f"({', '.join(faltantes)}). Una medición sin sus pines no dice contra qué "
            "corpus se midió."
        )
    return artefacto


def exigir_superada(artefacto: BarraSinGpu, corpus_sha: str) -> None:
    """Refuse unless this artifact shows the bar cleared for `corpus_sha`.

    Every check runs against the FIGURES, not just the state word, so a file
    edited to say `superada` over a failing measurement is still refused.
    """
    if artefacto.estado != ESTADO_SUPERADA:
        raise BarraNoSuperada(
            f"estado {artefacto.estado!r}: la barra del brazo {MODO_SIN_GPU} no figura "
            f"como {ESTADO_SUPERADA!r}."
        )
    if artefacto.modo != MODO_SIN_GPU:
        raise BarraNoSuperada(
            f"modo {artefacto.modo!r}: la barra solo puede registrarse para {MODO_SIN_GPU!r}, "
            "nunca para otro brazo."
        )
    if artefacto.corpus_sha != corpus_sha:
        raise BarraNoSuperada(
            f"corpus_sha: la barra se midió contra {artefacto.corpus_sha!r} y el snapshot "
            f"servido es {corpus_sha!r}."
        )
    if artefacto.hit_rate_at_5 is None or artefacto.hit_rate_at_5 < BARRA_HIT_RATE:
        raise BarraNoSuperada(
            f"hit@5 {artefacto.hit_rate_at_5!r} por debajo de la barra {BARRA_HIT_RATE}."
        )
    if (
        artefacto.separacion_norma_secundaria is None
        or artefacto.separacion_norma_secundaria < BARRA_SEPARACION
    ):
        raise BarraNoSuperada(
            f"norma-vs-secundaria {artefacto.separacion_norma_secundaria!r} por debajo de "
            f"{BARRA_SEPARACION}."
        )
    if artefacto.vigencia_correcta is None or artefacto.vigencia_correcta < BARRA_VIGENCIA:
        raise BarraNoSuperada(
            f"vigencia-correctness {artefacto.vigencia_correcta!r} por debajo de {BARRA_VIGENCIA}."
        )


class BarraSinOrdenRechazada(RuntimeError):
    """The artifact is not an honest failed bar, so the unranked path refuses it.

    Not `BarraNoSuperada`: that one means "the bar is not cleared", which is the
    opposite of what this refusal says when the artifact claims `superada`.
    """


def exigir_no_superada_honesta(artefacto: BarraSinGpu, corpus_sha: str) -> None:
    """Refuse unless this artifact is an honest FAILED bar for `corpus_sha`.

    This is the unranked production path: it accepts only a measurement that
    failed, and it never reports one as cleared. A passing bar goes through
    `exigir_superada`. A `no_superada` word over figures that all clear their
    constants is refused as inconsistent, because the figures are the evidence
    and the state word is only a claim.
    """
    if artefacto.estado == ESTADO_SUPERADA:
        raise BarraSinOrdenRechazada(
            f"estado {artefacto.estado!r}: the bar is recorded as cleared, so this "
            "artifact belongs to the ranked path. Use --exigir-barra."
        )
    if artefacto.estado != ESTADO_NO_SUPERADA:
        raise BarraSinOrdenRechazada(
            f"estado {artefacto.estado!r}: no failed measurement is recorded for the "
            f"{MODO_SIN_GPU} arm."
        )
    if artefacto.modo != MODO_SIN_GPU:
        raise BarraSinOrdenRechazada(
            f"modo {artefacto.modo!r}: the bar can only be recorded for {MODO_SIN_GPU!r}, "
            "never for another arm."
        )
    if artefacto.corpus_sha != corpus_sha:
        raise BarraSinOrdenRechazada(
            f"corpus_sha: the bar was measured against {artefacto.corpus_sha!r} and the "
            f"snapshot being ingested is {corpus_sha!r}."
        )
    hit = artefacto.hit_rate_at_5
    separacion = artefacto.separacion_norma_secundaria
    vigencia = artefacto.vigencia_correcta
    if hit is None or separacion is None or vigencia is None:
        ausentes = [
            nombre
            for nombre, valor in (
                ("hit_rate_at_5", hit),
                ("separacion_norma_secundaria", separacion),
                ("vigencia_correcta", vigencia),
            )
            if valor is None
        ]
        raise BarraSinOrdenRechazada(
            f"{', '.join(ausentes)}: a missing figure is not evidence of a failed bar."
        )
    if not (hit < BARRA_HIT_RATE or separacion < BARRA_SEPARACION or vigencia < BARRA_VIGENCIA):
        raise BarraSinOrdenRechazada(
            f"estado {artefacto.estado!r} is inconsistent with its figures: every figure "
            "meets its constant, so nothing in the artifact shows a failed bar."
        )


def _sin_medir(motivo: str) -> BarraSinGpu:
    """An artifact that decides nothing, and says why.

    Carries no figure at all: `cargar_barra` refuses a number under `no_medido`,
    so a refusal that kept the run's figures would write a file the loader rejects.
    """
    return BarraSinGpu(
        estado=ESTADO_NO_MEDIDO,
        modo=MODO_SIN_GPU,
        corpus_sha=None,
        n_respondibles=None,
        hit_rate_at_5=None,
        separacion_norma_secundaria=None,
        vigencia_correcta=None,
        metodologia="",
        motivo=motivo,
    )


def derivar_desde(
    corrida: Any,
    procedencia: Any,
    gold: Any,
    *,
    permitir_sintetico: bool = False,
) -> BarraSinGpu:
    """Build the artifact from one scored run, or refuse to decide it.

    Never raises on a run that cannot decide the bar: it returns `no_medido` with
    the reason, so the report can print WHY next to the figures instead of dying
    after a 57-question run has been paid for. The refusals, in the order they are
    checked:

    * no provenance row, a SYNTHETIC snapshot, or an `--allow-synthetic` run;
    * a run of any arm other than `bm25_sin_ce` — the CUDA arm's figures were
      measured with a ranker this arm does not have and may not stand in for it;
    * a gold set pinned to a different snapshot than the one scored;
    * any gold item whose expected keys moved out from under the pin (a
      migration-induced miss is not a retrieval result);
    * a gold set below the answerable-count precondition, or unresolved items;
    * a figure with no denominator.

    `corrida`, `procedencia` and `gold` are read structurally (`ResultadoModo`,
    `ProcedenciaEmbeddings`, `GoldSet`), which keeps this module on the serving
    side of the eval boundary.
    """
    if procedencia is None:
        return _sin_medir(
            "el snapshot no tiene procedencia registrada en rag_corpus, así que no hay "
            "contra qué corpus atar la medición."
        )
    if procedencia.sintetico:
        return _sin_medir(
            "el snapshot es sintético (vectores de prueba): una medición sobre él tiene "
            "la forma de una evaluación y no lo es."
        )
    if permitir_sintetico:
        return _sin_medir(
            "la corrida se hizo con --allow-synthetic: es un SMOKE RUN sobre material "
            "sintético y no decide ninguna barra."
        )
    if corrida.modo != MODO_SIN_GPU:
        return _sin_medir(
            f"la corrida es del brazo {corrida.modo!r}: sus cifras se midieron con un "
            f"ranker que {MODO_SIN_GPU!r} no tiene, y no pueden registrarse como suyas."
        )
    if gold.corpus_sha != procedencia.corpus_sha:
        return _sin_medir(
            f"el gold está fijado a {gold.corpus_sha!r} y el snapshot medido es "
            f"{procedencia.corpus_sha!r}."
        )
    if corrida.perdidas_de_migracion:
        ids = ", ".join(identificador for identificador, _ in corrida.perdidas_de_migracion)
        return _sin_medir(
            f"{len(corrida.perdidas_de_migracion)} ítem(s) del gold esperan claves que ya "
            f"no están en el snapshot ({ids}): son pérdidas de migración, no fallas de "
            "recuperación. Re-validá las claves del gold antes de decidir la barra."
        )
    precondicion = gold.precondicion()
    if not precondicion.evaluable:
        return _sin_medir("el gold no es evaluable: " + "; ".join(precondicion.motivos))

    metricas = corrida.metricas
    faltan = [
        nombre
        for nombre, valor in (
            ("hit@5", metricas.hit_rate_at_5),
            ("norma-vs-secundaria", metricas.separacion_norma_secundaria),
            ("vigencia-correctness", metricas.vigencia_correctness),
        )
        if valor is None
    ]
    if faltan:
        return _sin_medir(
            f"sin denominador para: {', '.join(faltan)}. Una cifra que no se pudo "
            "calcular no se decide como si fuera un cero ni como si fuera un uno."
        )

    supera = (
        metricas.hit_rate_at_5 >= BARRA_HIT_RATE
        and metricas.separacion_norma_secundaria >= BARRA_SEPARACION
        and metricas.vigencia_correctness >= BARRA_VIGENCIA
    )
    return BarraSinGpu(
        estado=ESTADO_SUPERADA if supera else ESTADO_NO_SUPERADA,
        modo=MODO_SIN_GPU,
        corpus_sha=procedencia.corpus_sha,
        n_respondibles=int(metricas.n_respondibles),
        hit_rate_at_5=float(metricas.hit_rate_at_5),
        separacion_norma_secundaria=float(metricas.separacion_norma_secundaria),
        vigencia_correcta=float(metricas.vigencia_correctness),
        metodologia=(
            f"{MODO_SIN_GPU}: candidatos BM25 en orden BM25, sin cross-encoder. Medido "
            f"sobre {int(metricas.n_respondibles)} ítems respondibles del gold, claves "
            "del gold re-validadas contra el snapshot, snapshot no sintético. Derivado "
            "por derivar_desde desde scripts/rag_eval.py."
        ),
        motivo="",
    )


def volcar(barra: BarraSinGpu) -> dict[str, Any]:
    """The artifact as a plain mapping, in the order a reader expects to find it."""
    return {
        "estado": barra.estado,
        "modo": barra.modo,
        "corpus_sha": barra.corpus_sha,
        "n_respondibles": barra.n_respondibles,
        "hit_rate_at_5": barra.hit_rate_at_5,
        "separacion_norma_secundaria": barra.separacion_norma_secundaria,
        "vigencia_correcta": barra.vigencia_correcta,
        "metodologia": barra.metodologia,
        "motivo": barra.motivo,
    }


def a_yaml(barra: BarraSinGpu) -> str:
    """`volcar` rendered for pasting into `barra_sin_gpu.yaml`."""
    return yaml.safe_dump(volcar(barra), sort_keys=False, allow_unicode=True)


def superada_para(corpus_sha: str, ruta: Path | None = None) -> bool:
    """Is rank order allowed for this snapshot? Any refusal, of any kind, is False.

    Fail-safe by construction: an unreadable, invalid or non-passing artifact
    never unlocks rank order. The cost of a false negative is a list sorted by
    citation key, which is always a correct answer.
    """
    try:
        exigir_superada(cargar_barra(ruta), corpus_sha)
    except (BarraInvalida, BarraNoSuperada):
        return False
    return True
