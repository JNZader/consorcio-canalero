"""Three-mode ablation harness over the gold set (design.md D6).

One code path for `fts`, `vector` and `hybrid`. Three would be three chances for
the modes to stop being comparable, which is the single thing an ablation cannot
survive — and the code path is `service.recuperar`, never a repository leg (the
D4 rule; see this package's `__init__`).

The harness is deliberately thin. It turns a gold set plus a snapshot into two
things — `PreguntaEvaluada` for `metrics.py` and `SenalAbstencion` for
`abstention.py` — and then does no arithmetic of its own. Everything that
produces a number the report will publish lives in a pure module with its own
tests, so nothing in the pipeline can quietly become the place where a metric is
"adjusted".

**Time is an input, never a reading.** Nothing here calls the clock. The report
takes its timestamp from its caller so that the same database and the same gold
set produce a byte-identical artifact modulo the header it was handed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml
from sqlalchemy.orm import Session

from app.domains.conocimiento import service
from app.domains.conocimiento.abstention import (
    PRECISION_MINIMA,
    RECALL_OBJETIVO,
    ResultadoLOOCV,
    SenalAbstencion,
    select_threshold_loocv,
)
from app.domains.conocimiento.embedding import Embedder
from app.domains.conocimiento.eval.metrics import (
    HIT_RATE_K,
    HitEvaluado,
    MetricasRecuperacion,
    PreguntaEvaluada,
    metricas_recuperacion,
)
from app.domains.conocimiento.schemas import ResultadoRecuperacion

GOLD_SET_PATH = Path(__file__).parent / "gold_set.yaml"

#: Where the owner keeps the text of the `origen: privado` items. No default
#: path: a default would be a place this repository is entitled to read from,
#: and the whole point of the split is that it is not.
ENV_PRIVADO = "RAG_GOLD_PRIVADO_PATH"

#: The gold-set precondition from the retrieval spec. Below it the report marks
#: thresholds not-evaluable instead of scoring them.
MINIMO_RESPONDIBLES = 20

MODOS_ABLACION = ("fts", "vector", "hybrid")

#: The owner's ratified bars (retrieval spec, `Go/No-Go Thresholds`).
BARRA_HIT_RATE = 0.85
BARRA_MRR = 0.70
BARRA_CITATION_PRECISION = 1.0
BARRA_SEPARACION = 1.0
BARRA_VIGENCIA = 1.0


class GoldSetInvalido(RuntimeError):
    """The committed gold set does not satisfy its own schema."""


@dataclass(frozen=True)
class GoldItem:
    id: str
    #: `None` for an `origen: privado` item whose text was not resolved. NOT the
    #: empty string: "no text available" and "empty question" are different
    #: facts and only one of them is a configuration problem.
    pregunta: str | None
    pregunta_ref: str | None
    clase: str
    subclase: str
    citas_esperadas: tuple[str, ...]
    citas_vigencia: tuple[str, ...]
    fuente: str
    validado_por: str
    dificultad: str | None
    origen: str

    @property
    def resuelta(self) -> bool:
        return self.pregunta is not None

    @property
    def es_respondible(self) -> bool:
        """`trampa-vigencia` IS answerable — it is the subset whose correct answer
        depends on a caveat unit, and it counts toward the ratified 29."""
        return self.clase != "unanswerable"


@dataclass(frozen=True)
class Precondicion:
    evaluable: bool
    motivos: tuple[str, ...]
    n_respondibles: int
    n_unanswerable: int


@dataclass(frozen=True)
class GoldSet:
    version: int
    corpus_sha: str
    ratificado: str
    items: tuple[GoldItem, ...]

    @property
    def n_respondibles(self) -> int:
        return sum(1 for item in self.items if item.es_respondible)

    @property
    def n_unanswerable(self) -> int:
        return sum(1 for item in self.items if not item.es_respondible)

    @property
    def no_resueltas(self) -> tuple[str, ...]:
        return tuple(item.id for item in self.items if not item.resuelta)

    @property
    def no_validadas(self) -> tuple[str, ...]:
        return tuple(item.id for item in self.items if item.validado_por != "owner")

    @property
    def resueltas(self) -> tuple[GoldItem, ...]:
        return tuple(item for item in self.items if item.resuelta)

    def precondicion(self, minimo: int = MINIMO_RESPONDIBLES) -> Precondicion:
        """Mechanical, not procedural (D6): three conditions, all of them hard.

        An unresolved private item counts as a blocker for the same reason a
        `draft` item does — the pair the owner ratified is over 52 questions, and
        a pair computed over the subset this machine happened to be able to read
        is a different measurement wearing the same name.
        """
        motivos: list[str] = []
        if self.n_respondibles < minimo:
            motivos.append(
                f"answerable = {self.n_respondibles} < {minimo}: the gold-set "
                "precondition is not met, so no go/no-go may be scored"
            )
        if self.no_validadas:
            motivos.append(
                "not owner-validated: "
                + ", ".join(self.no_validadas[:10])
                + (f" (+{len(self.no_validadas) - 10} more)" if len(self.no_validadas) > 10 else "")
            )
        if self.no_resueltas:
            motivos.append(
                f"{len(self.no_resueltas)} item(s) have no question text — set "
                f"{ENV_PRIVADO}: "
                + ", ".join(self.no_resueltas[:10])
                + (f" (+{len(self.no_resueltas) - 10} more)" if len(self.no_resueltas) > 10 else "")
            )
        return Precondicion(
            evaluable=not motivos,
            motivos=tuple(motivos),
            n_respondibles=self.n_respondibles,
            n_unanswerable=self.n_unanswerable,
        )


def _textos_privados(path: Path | None) -> Mapping[str, str]:
    if path is None:
        crudo = os.environ.get(ENV_PRIVADO)
        if not crudo:
            return {}
        path = Path(crudo).expanduser()
    if not path.is_file():
        return {}
    datos = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return dict(datos.get("preguntas") or {})


def cargar_gold_set(path: Path | None = None, privado_path: Path | None = None) -> GoldSet:
    """Load the committed gold set, resolving private question text if available."""
    path = path or GOLD_SET_PATH
    datos = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    privados = _textos_privados(privado_path)

    items: list[GoldItem] = []
    vistos: set[str] = set()
    for crudo in datos.get("items") or []:
        id = str(crudo["id"])
        if id in vistos:
            raise GoldSetInvalido(f"duplicate gold-set id {id!r}")
        vistos.add(id)

        origen = str(crudo.get("origen", "publico"))
        pregunta = crudo.get("pregunta")
        if pregunta is None and origen == "privado":
            pregunta = privados.get(id)
        if pregunta is None and origen == "publico":
            raise GoldSetInvalido(f"{id}: `origen: publico` with no `pregunta`")

        clase = str(crudo["clase"])
        citas = tuple(crudo.get("citas_esperadas") or ())
        vigencia = tuple(crudo.get("citas_vigencia") or ())
        if clase == "unanswerable" and citas:
            raise GoldSetInvalido(f"{id}: an unanswerable item declares expected citations")
        if not set(vigencia).issubset(set(citas)):
            raise GoldSetInvalido(f"{id}: `citas_vigencia` is not a subset of `citas_esperadas`")

        items.append(
            GoldItem(
                id=id,
                pregunta=None if pregunta is None else str(pregunta),
                pregunta_ref=(
                    None if crudo.get("pregunta_ref") is None else str(crudo["pregunta_ref"])
                ),
                clase=clase,
                subclase=str(crudo.get("subclase", "")),
                citas_esperadas=citas,
                citas_vigencia=vigencia,
                fuente=str(crudo.get("fuente", "")),
                validado_por=str(crudo.get("validado_por", "draft")),
                dificultad=None if crudo.get("dificultad") is None else str(crudo["dificultad"]),
                origen=origen,
            )
        )

    return GoldSet(
        version=int(datos.get("version", 1)),
        corpus_sha=str(datos.get("corpus_sha", "")),
        ratificado=str(datos.get("ratificado", "")),
        items=tuple(items),
    )


@dataclass(frozen=True)
class DetallePregunta:
    """One question's row in the report. Carries what a reader needs to argue."""

    id: str
    clase: str
    pregunta: str
    citas_esperadas: tuple[str, ...]
    claves_devueltas: tuple[str, ...]
    score_top1: float
    margen: float
    n_fts: int
    n_vector: int


@dataclass(frozen=True)
class CoberturaLegs:
    """How often each leg returned NOTHING — the diagnostic that keeps a mode's
    metrics from being read as a statement about a leg that never ran.

    This exists because of a measured defect (ledger RAG4-001):
    `websearch_to_tsquery` builds a CONJUNCTION, so a colloquial gold question
    compiles to a dozen ANDed lexemes and matches no legal article at all. The
    FTS leg then contributes zero rows — and in `hybrid` that turns the fused
    result into vector-only while the report keeps saying "hybrid".

    A metric computed over an empty leg is not wrong, it is about something
    else, so the fact travels beside it rather than in a footnote.
    """

    n_preguntas: int
    sin_candidatos_fts: int
    sin_candidatos_vector: int

    @property
    def fraccion_sin_candidatos_fts(self) -> float:
        return self.sin_candidatos_fts / self.n_preguntas if self.n_preguntas else 0.0

    @property
    def fraccion_sin_candidatos_vector(self) -> float:
        return self.sin_candidatos_vector / self.n_preguntas if self.n_preguntas else 0.0

    @property
    def leg_fts_degradada(self) -> bool:
        """A strict majority of questions got nothing from the lexical leg."""
        return self.fraccion_sin_candidatos_fts > 0.5

    @property
    def leg_vector_degradada(self) -> bool:
        return self.fraccion_sin_candidatos_vector > 0.5


@dataclass(frozen=True)
class ResultadoModo:
    modo: str
    k: int
    preguntas: tuple[PreguntaEvaluada, ...]
    senales: tuple[SenalAbstencion, ...]
    detalles: tuple[DetallePregunta, ...]
    metricas: MetricasRecuperacion
    #: Computed from `senales`/`detalles` at construction time so a caller cannot
    #: pass a LOOCV result or a coverage count that does not belong to this run.
    loocv: ResultadoLOOCV = field(init=False)
    cobertura: CoberturaLegs = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "loocv", select_threshold_loocv(self.senales))
        object.__setattr__(
            self,
            "cobertura",
            CoberturaLegs(
                n_preguntas=len(self.detalles),
                sin_candidatos_fts=sum(1 for d in self.detalles if d.n_fts == 0),
                sin_candidatos_vector=sum(1 for d in self.detalles if d.n_vector == 0),
            ),
        )

    @property
    def hibrido_degenerado(self) -> bool:
        """`hybrid` where one leg contributed nothing at all is not hybrid.

        Reporting it under that name would publish a comparison that was never
        made — the same failure `VectorSupportUnavailable` refuses loudly,
        reached instead through a query that simply matched nothing.
        """
        if self.modo != "hybrid":
            return False
        return all(d.n_fts == 0 for d in self.detalles) or all(
            d.n_vector == 0 for d in self.detalles
        )


def senales_desde(item: GoldItem, resultado: ResultadoRecuperacion) -> SenalAbstencion:
    """Reduce one retrieval result to its abstention signal.

    A run that returned nothing scores `0.0`, not `None`: "the top hit was not
    confident enough to cite" is exactly what an empty page means, and it is the
    same decision the policy makes for a weak hit. Modelling it as missing data
    would put an `if` in front of every threshold comparison, and that `if` is
    where an empty page quietly becomes an answer.
    """
    scores = [hit.score_rrf for hit in resultado.hits]
    top1 = scores[0] if scores else 0.0
    margen = (scores[0] - scores[1]) if len(scores) > 1 else 0.0
    ambas = bool(
        resultado.hits
        and resultado.hits[0].rango_fts is not None
        and resultado.hits[0].rango_vector is not None
    )
    return SenalAbstencion(
        id=item.id,
        debe_abstenerse=not item.es_respondible,
        score_top1=top1,
        margen=margen,
        ambas_piernas=ambas,
    )


def _pregunta_evaluada(item: GoldItem, resultado: ResultadoRecuperacion) -> PreguntaEvaluada:
    return PreguntaEvaluada(
        id=item.id,
        clase=item.clase,
        citas_esperadas=item.citas_esperadas,
        citas_vigencia=item.citas_vigencia,
        hits=tuple(
            HitEvaluado(
                citation_key=hit.citation_key,
                es_secundaria=hit.es_secundaria,
                estado_vigencia=hit.estado_vigencia,
            )
            for hit in resultado.hits
        ),
    )


def correr_modo(
    db: Session,
    corpus_sha: str,
    gold: GoldSet,
    *,
    modo: str,
    k: int = 10,
    embedder: Embedder | None = None,
) -> ResultadoModo:
    """Run every RESOLVED gold question through `service.recuperar` in one mode.

    Unresolved items are skipped here and blocked at the precondition, rather
    than silently shrinking the denominator: `precondicion()` already refuses a
    go/no-go while any item is unresolved, so a partial run can produce
    diagnostics and never a verdict.
    """
    preguntas: list[PreguntaEvaluada] = []
    senales: list[SenalAbstencion] = []
    detalles: list[DetallePregunta] = []

    for item in gold.resueltas:
        assert item.pregunta is not None  # guarded by `resueltas`; keeps mypy honest
        resultado = service.recuperar(
            db,
            corpus_sha,
            item.pregunta,
            modo=modo,
            k=k,
            embedder=embedder,
        )
        senal = senales_desde(item, resultado)
        preguntas.append(_pregunta_evaluada(item, resultado))
        senales.append(senal)
        detalles.append(
            DetallePregunta(
                id=item.id,
                clase=item.clase,
                pregunta=item.pregunta,
                citas_esperadas=item.citas_esperadas,
                claves_devueltas=tuple(hit.citation_key for hit in resultado.hits),
                score_top1=senal.score_top1,
                margen=senal.margen,
                n_fts=resultado.n_fts,
                n_vector=resultado.n_vector,
            )
        )

    return ResultadoModo(
        modo=modo,
        k=k,
        preguntas=tuple(preguntas),
        senales=tuple(senales),
        detalles=tuple(detalles),
        metricas=metricas_recuperacion(preguntas, k=HIT_RATE_K),
    )


@dataclass(frozen=True)
class ResultadoEval:
    corpus_sha: str
    modos: tuple[str, ...]
    por_modo: dict[str, ResultadoModo]
    gold: GoldSet


def evaluar(
    db: Session,
    corpus_sha: str,
    gold: GoldSet,
    *,
    modos: Sequence[str] = MODOS_ABLACION,
    k: int = 10,
    embedder: Embedder | None = None,
) -> ResultadoEval:
    """The ablation: the same questions, the same k, one code path, N modes."""
    por_modo = {
        modo: correr_modo(db, corpus_sha, gold, modo=modo, k=k, embedder=embedder) for modo in modos
    }
    return ResultadoEval(
        corpus_sha=corpus_sha,
        modos=tuple(modos),
        por_modo=por_modo,
        gold=gold,
    )


# ---------------------------------------------------------------------------
# Go / no-go
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Barra:
    """One bar, its measured value, and WHERE the value came from.

    `fuente` exists because the whole D5 argument is about which number decided
    the outcome. A report that prints a pass next to a figure without saying
    whether it was fitted on the scoring sample is the exact artifact this design
    refuses to produce.
    """

    nombre: str
    valor: float | None
    minimo: float
    comparador: str
    fuente: str

    @property
    def pasa(self) -> bool:
        if self.valor is None:
            return False
        if self.comparador == "==":
            return self.valor == self.minimo
        return self.valor >= self.minimo


@dataclass(frozen=True)
class GoNoGo:
    modo: str
    evaluable: bool
    motivos_no_evaluable: tuple[str, ...]
    barras: tuple[Barra, ...]

    @property
    def pasa(self) -> bool:
        return self.evaluable and all(barra.pasa for barra in self.barras)

    @property
    def veredicto(self) -> str:
        if not self.evaluable:
            return "NO EVALUABLE"
        return "GO" if self.pasa else "NO-GO"

    @property
    def barras_fallidas(self) -> tuple[str, ...]:
        return tuple(barra.nombre for barra in self.barras if not barra.pasa)


def decidir_go_no_go(
    corrida: ResultadoModo,
    gold: GoldSet,
    *,
    forzar_evaluable: bool = False,
    minimo_respondibles: int = MINIMO_RESPONDIBLES,
) -> GoNoGo:
    """Score the seven bars. The abstention pair reads the HELD-OUT figures.

    `forzar_evaluable` exists for tests that need the bar arithmetic without a
    52-item fixture. It is not exposed on the CLI, because "evaluate anyway" is
    precisely the switch the n>=20 precondition exists to remove.
    """
    precondicion = gold.precondicion(minimo_respondibles)
    metricas = corrida.metricas
    loocv = corrida.loocv

    barras = (
        Barra("hit-rate@5", metricas.hit_rate_at_5, BARRA_HIT_RATE, ">=", "answerable subset"),
        Barra("MRR", metricas.mrr, BARRA_MRR, ">=", "answerable subset"),
        Barra(
            "citation-precision",
            metricas.citation_precision,
            BARRA_CITATION_PRECISION,
            "==",
            "answerable subset",
        ),
        Barra(
            "norma-vs-secundaria",
            metricas.separacion_norma_secundaria,
            BARRA_SEPARACION,
            "==",
            "answerable subset",
        ),
        Barra(
            "vigencia-correctness",
            metricas.vigencia_correctness,
            BARRA_VIGENCIA,
            "==",
            "answerable subset",
        ),
        # STRICT, and read from the held-out predictions. A single false-confident
        # answer — one unanswerable question that got an answer — fails go/no-go
        # regardless of every other bar.
        Barra("abstention recall", loocv.recall, RECALL_OBJETIVO, "==", "LOOCV held-out"),
        Barra("abstention precision", loocv.precision, PRECISION_MINIMA, ">=", "LOOCV held-out"),
    )

    return GoNoGo(
        modo=corrida.modo,
        evaluable=forzar_evaluable or precondicion.evaluable,
        motivos_no_evaluable=() if forzar_evaluable else precondicion.motivos,
        barras=barras,
    )


def resumen_metodologico(corrida: ResultadoModo) -> dict[str, Any]:
    """The per-mode disclosure block the report contract requires (D6).

    Everything a reader needs to tell a measurement from a fit: the selection
    rule, that it was cross-validated, `n`, the shipped threshold, the held-out
    pair that decided go/no-go, the same-sample pair explicitly labelled, and the
    fallback count — because a fallback that fires often is itself a no-go
    signal.
    """
    loocv = corrida.loocv
    return {
        "modo": corrida.modo,
        "n": loocv.n,
        "regla_de_seleccion": (
            "highest precision among thresholds reaching abstention recall 1.00; "
            "ties broken by the lower threshold. Grid = the observed fused-score "
            "values, with nothing appended."
        ),
        "validacion": "leave-one-out cross-validation, one fold per gold item",
        "umbral_shipped": loocv.umbral_shipped,
        "umbral_shipped_fallback": loocv.seleccion_shipped.fallback,
        "held_out_recall": loocv.recall,
        "held_out_precision": loocv.precision,
        "same_sample_recall": loocv.same_sample_recall,
        "same_sample_precision": loocv.same_sample_precision,
        "etiqueta_same_sample": "upper bound (fit on the scoring sample)",
        "folds_con_fallback": loocv.folds_con_fallback,
        "fraccion_fallback": loocv.fraccion_fallback,
    }
