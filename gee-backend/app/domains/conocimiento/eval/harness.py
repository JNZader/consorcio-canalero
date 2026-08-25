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
from app.domains.conocimiento.recuperacion.reranker import Reranker
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

#: Which legs each mode actually runs. Mirrors `service.recuperar`'s own branches
#: — the coverage diagnostic must not call a leg "degraded" that the mode never
#: asked to run.
LEGS_POR_MODO: dict[str, tuple[str, ...]] = {
    "fts": ("fts",),
    "vector": ("vector",),
    "hybrid": ("fts", "vector"),
    # `bm25_ce`'s ONE candidate leg is BM25 — not `fts`, and that distinction is
    # the whole finding of the candidate-recall campaign: `ts_rank_cd` as the
    # candidate scorer measured 0.655 against BM25's 0.759 on the same pool and
    # the same reranker. Naming the leg `fts` here would make the coverage block
    # report an empty lexical leg for an arm that never asked for one, and would
    # annotate the leg that DOES run as "not run in this mode" (task 9.1b).
    "bm25_ce": ("bm25",),
}

#: Modes whose ONLY leg is the vector one, and therefore the only modes in which
#: an over-the-ceiling unit is unreachable rather than merely badly ranked. In
#: `fts` and `hybrid` the lexical leg reaches those units, so nothing is exempt
#: there and every item stays in every denominator.
MODOS_SIN_ALCANCE_LEXICO = ("vector",)

#: Modes that carry NO ratified abstention signal, so the harness builds none for
#: them and the report prints `not-evaluable` instead of a pair.
#:
#: This is the seam task 9.1b needed and did not have. `senales_desde` refuses on
#: `bm25_ce` (`SenalAbstencionNoRatificada`), which was correct and also meant the
#: arm could not be RUN at all: `correr_modo` built a signal per question, so the
#: exception that protects the abstention gate also blocked the retrieval margin
#: the amended serving gate requires. The two are separable and are now separated
#: — the arm is scored, its abstention row says `not-evaluable`, and no threshold
#: is selected from a signal nobody ratified (owner decision 0.1, OPEN).
MODOS_SIN_SENAL_RATIFICADA = ("bm25_ce",)

#: What `fuente_senal` says for those modes. NOT `FUENTE_RRF`, which is what the
#: empty-signals fallback used to return: naming a fusion that never ran, on the
#: one arm whose whole point is that its signal is unratified, is the RJDB-002
#: pathology wearing a different hat.
FUENTE_NO_RATIFICADA = "sin señal ratificada (decisión 0.1 del owner, ABIERTA)"

#: The owner's RE-RATIFIED bars (`design.md:1141-1145`, amendment of 2026-08-23),
#: fixed against 116 measured configurations rather than proposed in advance.
#:
#: They moved DOWN from the V0 aspirations (hit@5 0.85, MRR 0.70,
#: citation-precision 1.00) and the honest reason is recorded here rather than
#: buried in a commit message: those figures were written before anything had
#: been measured, and citation-precision = 1.00 is unreachable BY CONSTRUCTION on
#: this gold set — several items expect two citations where the corpus offers a
#: third, equally correct one. A bar nothing can clear does not protect quality,
#: it just guarantees a NO-GO that gets waived.
#:
#: The two bars that did NOT move are the two that cannot be traded:
#: norma-vs-secundaria and vigencia-correctness stay at 1.00, both measured clear
#: at B50, and they are what stops a consultant's report or a derogated article
#: from being served as live law. The per-document cap was rejected for breaking
#: exactly the second of them (0.793 hit@5 against 0.333 vigencia).
#:
#: The honesty rider travels with these numbers: the gold set is 29 answerable
#: questions, so ONE question is worth 0.034 hit@5, and the B50 family reads as
#: ≈0.72–0.76. Growing the gold set (follow-up F2) is what would make these bars
#: sharper; lowering them again is not.
BARRA_HIT_RATE = 0.72
BARRA_HIT_RATE_10 = 0.80
BARRA_MRR = 0.55
BARRA_CITATION_PRECISION = 0.33
BARRA_SEPARACION = 1.0
BARRA_VIGENCIA = 1.0


#: The public gold set's own filename, which the owner-side private file names in
#: its `para:` key. Checked rather than assumed: `RAG_GOLD_PRIVADO_PATH` is an
#: environment variable pointing outside this repository, so the only thing
#: stopping a stale or foreign file from resolving 26 questions is that the file
#: says which set it belongs to and we read it.
NOMBRE_GOLD_SET = "gold_set.yaml"


class SenalAbstencionNoRatificada(RuntimeError):
    """This mode has no ratified abstention signal, so none is improvised.

    Raised for a mode that carries no fused score — today only `bm25_ce`.
    Abstention bars are an OPEN owner decision (0.1) precisely because the
    measured candidate signal, reranker confidence, is worse than the cosine one
    it would replace. Refusing beats defaulting: a threshold selected from an
    unratified signal would still print a number, and the number would decide a
    go/no-go nobody chose.
    """


#: One wording for both refusal paths in `_escala_de_senal`. Two hand-written
#: copies of the same refusal drift, and the arm whose gate this decides is the
#: one nobody re-reads until it has already published a number.
_MOTIVO_SENAL_NO_RATIFICADA = (
    "modo {modo!r} carries no fused score, and no abstention signal has been "
    "ratified for it. Owner decision 0.1 is open: the options on the table are "
    "relaxing recall to >= 0.90 or building a different signal. Until one is "
    "chosen this arm's abstention pair is not-evaluable, and inventing one here "
    "would set the gate to whatever the system already does."
)


class GoldSetInvalido(RuntimeError):
    """The committed gold set does not satisfy its own schema."""


class CorpusShaMismatch(RuntimeError):
    """The gold set and the snapshot being evaluated pin different corpus revisions.

    The gold set's `citas_esperadas` are citation keys of ONE corpus revision.
    Scored against a different snapshot, a key that simply does not exist there
    reads as a retrieval miss, so every metric shifts down and the report names a
    failure of the retriever instead of a mismatch of inputs.

    The direction of the error is fail-safe — a spurious NO-GO, never a spurious
    GO — which is why this is a refusal and not a warning: a NO-GO nobody can
    explain costs a re-run of the whole batch, and the cause is one string
    comparison away.
    """


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


def _textos_privados(path: Path | None, corpus_sha: str) -> Mapping[str, str]:
    """Question text for the `origen: privado` items, or `{}` when unavailable.

    The file declares `para:` and `corpus_sha:` and both are CHECKED here rather
    than skipped, which is the whole difference between "the harness resolved 26
    questions" and "the harness resolved 26 questions that belong to this set".
    The file lives outside this repository at an operator-supplied path, so a
    stale copy from a previous corpus revision, or the wrong file entirely, is a
    plain configuration slip — and its symptom would be 26 questions silently
    scored against citations that no longer exist.

    A missing/unset path is NOT an error: unresolved items are already a hard
    blocker in `precondicion()`. Only a file that IS there and contradicts the
    set it claims to serve raises.
    """
    if path is None:
        crudo = os.environ.get(ENV_PRIVADO)
        if not crudo:
            return {}
        path = Path(crudo).expanduser()
    if not path.is_file():
        return {}

    datos = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    para = datos.get("para")
    if para is not None and Path(str(para)).name != NOMBRE_GOLD_SET:
        raise GoldSetInvalido(
            f"{path}: declares `para: {para}` but it is being used to resolve "
            f"{NOMBRE_GOLD_SET}. Refusing rather than pasting one gold set's "
            "question text into another's items."
        )

    sha_privado = datos.get("corpus_sha")
    if sha_privado is not None and str(sha_privado) != corpus_sha:
        raise CorpusShaMismatch(
            f"{path} is pinned to corpus_sha {sha_privado} but {NOMBRE_GOLD_SET} "
            f"is pinned to {corpus_sha}. The 26 private items would be resolved "
            "from a different corpus revision than the one their expected "
            "citations were written against."
        )

    return dict(datos.get("preguntas") or {})


def verificar_corpus_sha(gold: GoldSet, corpus_sha: str) -> None:
    """Refuse a gold set pinned to a different corpus revision than the snapshot.

    Called at the CLI edge BEFORE the database is opened, the report directory is
    created or an embedder is built: this is a pure string comparison and there is
    no reason for it to cost anything.
    """
    if gold.corpus_sha != corpus_sha:
        raise CorpusShaMismatch(
            f"the gold set is pinned to corpus_sha {gold.corpus_sha} but the "
            f"snapshot being evaluated is {corpus_sha}. Every `citas_esperadas` "
            "key belongs to the first revision; scored against the second, a key "
            "that does not exist there is indistinguishable from a retrieval "
            "miss. Re-ingest the pinned corpus, or evaluate the snapshot this "
            "gold set was written for."
        )


def cargar_gold_set(path: Path | None = None, privado_path: Path | None = None) -> GoldSet:
    """Load the committed gold set, resolving private question text if available."""
    path = path or GOLD_SET_PATH
    datos = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    corpus_sha = str(datos.get("corpus_sha", ""))
    privados = _textos_privados(privado_path, corpus_sha)

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
        corpus_sha=corpus_sha,
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
    #: Size of the BM25 candidate pool. `0` in every fused mode, which never asks
    #: for one — and a real, reportable outcome in `bm25_ce`, where an empty pool
    #: means the cross-encoder ranked nothing at all.
    n_bm25: int = 0


@dataclass(frozen=True)
class CoberturaLegs:
    """How often each leg returned NOTHING — the diagnostic that keeps a mode's
    metrics from being read as a statement about a leg that never ran.

    This exists because of a measured defect (ledger RAG4-001):
    `websearch_to_tsquery` builds a CONJUNCTION, so a colloquial gold question
    compiled to a dozen ANDed lexemes and matched no legal article at all. The
    FTS leg then contributed zero rows — and in `hybrid` that turned the fused
    result into vector-only while the report kept saying "hybrid".

    **The operator was fixed** (`repository.FTS_OPERADOR`: the leg now ORs its
    lexemes), so the emptiness this counts should be rare. That is exactly why
    the counter stays: it was the instrument that measured the defect, and
    deleting the instrument once the reading improves is how the next regression
    goes unnoticed. Vocabulary can still miss — gold D-7's article shares no
    lexeme with its question, which is the vector leg's job, not the lexical
    leg's — so an empty leg remains a real and reportable outcome.

    A metric computed over an empty leg is not wrong, it is about something
    else, so the fact travels beside it rather than in a footnote.
    """

    n_preguntas: int
    sin_candidatos_fts: int
    sin_candidatos_vector: int
    #: How often the BM25 candidate pool came back empty. Its own counter rather
    #: than a reuse of `sin_candidatos_fts`, because BM25 and `ts_rank_cd` select
    #: different pools from the same index and the arm being gated is the one
    #: whose empty leg would otherwise be the only invisible one (task 9.1b).
    sin_candidatos_bm25: int = 0
    #: Which legs this mode actually RAN. A leg that was never asked to run
    #: trivially returned nothing for every question, and calling that
    #: "degraded" is a warning that fires on every `--modo fts` run — which is
    #: how the reader learns to skip the block that carries the RAG4-001 finding.
    #: Measured on a real 52-question run before this was gated: `--modo fts`
    #: printed `LEG DEGRADADA (vector)` next to a perfectly healthy lexical leg.
    legs_corridas: tuple[str, ...] = ("fts", "vector")

    @property
    def fraccion_sin_candidatos_fts(self) -> float:
        return self.sin_candidatos_fts / self.n_preguntas if self.n_preguntas else 0.0

    @property
    def fraccion_sin_candidatos_vector(self) -> float:
        return self.sin_candidatos_vector / self.n_preguntas if self.n_preguntas else 0.0

    @property
    def leg_fts_degradada(self) -> bool:
        """A strict majority of questions got nothing from the lexical leg.

        False when the mode did not run that leg: "it returned nothing" and "it
        was never asked" are different facts, and only one of them is a finding.
        """
        return "fts" in self.legs_corridas and self.fraccion_sin_candidatos_fts > 0.5

    @property
    def leg_vector_degradada(self) -> bool:
        return "vector" in self.legs_corridas and self.fraccion_sin_candidatos_vector > 0.5

    @property
    def fraccion_sin_candidatos_bm25(self) -> float:
        return self.sin_candidatos_bm25 / self.n_preguntas if self.n_preguntas else 0.0

    @property
    def leg_bm25_degradada(self) -> bool:
        """A strict majority of questions got no BM25 candidates at all.

        In `bm25_ce` this is not a caveat on the metric, it IS the metric: the
        cross-encoder can only rank what BM25 selected, so an empty pool is an
        unanswerable question by construction rather than a ranking failure.
        """
        return "bm25" in self.legs_corridas and self.fraccion_sin_candidatos_bm25 > 0.5


@dataclass(frozen=True)
class ExencionOverCeiling:
    """Which units this mode cannot reach at all, and whom that silences.

    The units over the embedder's token ceiling are ingested whole, stay
    FTS-retrievable and are never embedded — a ratified design decision, not a
    defect (design.md D3). WHICH units those are is a property of the model that
    produced the batch, not a constant: BGE-M3's window is 8192 tokens and leaves
    three, multilingual-e5-large's is 512 and leaves many more. That is why the
    set is read from the database (`embedding IS NULL`) instead of recomputed,
    and why the report names the ceiling rather than printing a number nothing
    durable records (ledger RJDB-101). But gold D-8's ONLY expected citation is
    one of them
    (`8560#5`), so in a single-leg `vector` run its citation-precision is 0 by
    construction, and citation-precision feeds a hard `== 1.00` bar. Left in the
    denominator that item alone made the vector arm's bar unreachable while the
    report said nothing about why; taken out silently, the report would show a
    denominator shrinking for no stated reason. So it leaves the denominator AND
    this block travels with the number.

    `aplica` is False for `fts` and `hybrid`: there the lexical leg reaches the
    unit, so the score is a real measurement and nothing is exempt.
    """

    aplica: bool
    #: Every unit of the snapshot with no vector, sorted. Empty when `aplica` is
    #: False — the set is not even queried for a mode that has a lexical leg.
    claves: tuple[str, ...] = ()
    #: Gold ids whose expected citations are ALL in `claves`, i.e. the items this
    #: mode cannot answer with a citation no matter how good the ranking is.
    preguntas: tuple[str, ...] = ()

    @property
    def n_preguntas_exentas(self) -> int:
        return len(self.preguntas)


@dataclass(frozen=True)
class ResultadoModo:
    modo: str
    k: int
    preguntas: tuple[PreguntaEvaluada, ...]
    senales: tuple[SenalAbstencion, ...]
    detalles: tuple[DetallePregunta, ...]
    metricas: MetricasRecuperacion
    exencion: ExencionOverCeiling = field(default_factory=lambda: ExencionOverCeiling(False))
    #: Identity of the ranker that produced this mode's ORDER, carried up from the
    #: retrieval results rather than re-derived from `modo`. `None` in a mode that
    #: has no ranker at all (the RRF ablation orders by fusion, not by a model).
    #:
    #: This travels for the same reason `rag_corpus` records which model wrote the
    #: embeddings: a report rendered over a deterministic stand-in ranker is shaped
    #: exactly like a measurement and is none, and the only thing that can tell the
    #: two apart is the identity of the thing that ranked. `report._gate_sintetico`
    #: refuses on it exactly as it refuses on synthetic embeddings.
    ranker_modelo: str | None = None
    ranker_sintetico: bool | None = None
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
                sin_candidatos_bm25=sum(1 for d in self.detalles if d.n_bm25 == 0),
                legs_corridas=LEGS_POR_MODO.get(self.modo, ()),
            ),
        )

    @property
    def fuente_senal(self) -> str:
        """The scale this mode's abstention grid was swept over.

        Read off the signals themselves rather than re-derived from `modo`, so
        the report can never name a scale the numbers were not on.
        """
        if self.senales:
            return self.senales[0].fuente_senal
        if self.modo in MODOS_SIN_SENAL_RATIFICADA:
            return FUENTE_NO_RATIFICADA
        return FUENTE_RRF

    @property
    def senal_ratificada(self) -> bool:
        """Does this mode have an abstention signal at all? (task 9.1b)"""
        return self.modo not in MODOS_SIN_SENAL_RATIFICADA

    @property
    def senal_constante(self) -> bool:
        """Did every question produce the SAME signal? Then nothing was swept.

        A one-value grid means the threshold selection had exactly one candidate
        and the outcome was fixed before the data was read — the RJDB-002
        pathology. Surfaced rather than swallowed, next to the fallback count it
        would otherwise be indistinguishable from.
        """
        return len({senal.score_top1 for senal in self.senales}) <= 1 and bool(self.senales)

    @property
    def hibrido_degenerado(self) -> bool:
        """`hybrid` where a leg contributed nothing for MOST questions is not hybrid.

        Reporting it under that name would publish a comparison that was never
        made — the same failure `VectorSupportUnavailable` refuses loudly,
        reached instead through a query that simply matched nothing.

        The threshold is the same strict majority `leg_fts_degradada` uses, and
        that alignment is a fix rather than a tidy-up: this property used to fire
        only at `all(...)`, i.e. 100 % empty. A `hybrid` run where the lexical leg
        died on 49 of 52 questions is fused for three of them and vector-only for
        the rest, and the old predicate called that a healthy hybrid. One
        surviving question was enough to silence the flag, which made the loudest
        warning in the report the easiest one to switch off by accident.
        """
        if self.modo != "hybrid":
            return False
        return self.cobertura.leg_fts_degradada or self.cobertura.leg_vector_degradada


FUENTE_RRF = "RRF fusionado (1/(k+rango+1) sumado sobre las dos piernas)"
FUENTE_FTS = "ts_rank_cd de la pierna léxica (mayor = mejor, piso 0)"
FUENTE_VECTOR = "similitud coseno reescalada (1 - distancia/2) de la pierna vectorial"


def _similitud_desde_distancia(distancia: float) -> float:
    """pgvector cosine distance -> a [0, 1] similarity, monotonically INCREASING.

    `<=>` returns `1 - cos(θ)`, so its range is `[0, 2]` and *smaller* means more
    similar — the wrong direction for a threshold whose rule is "abstain below".
    `1 - d/2` is `(1 + cos)/2`: order-preserving in `cos`, and bounded in
    `[0, 1]`.

    The `/2` is the load-bearing half and NOT cosmetic rescaling. The obvious
    transform `1 - d` gives `cos`, which is NEGATIVE for any hit more than 90°
    from the query — and an empty page scores a flat `0.0`. A negative-similarity
    hit would then rank BELOW "we retrieved absolutely nothing", so the weakest
    real answer would look less confident than no answer at all, and a threshold
    between the two would abstain on the real hit while answering the empty one.
    With `/2` the floor is a true floor: `0.0` is reachable only by a
    diametrically opposed vector, which no retrieved unit is.
    """
    return 1.0 - distancia / 2.0


def _lector_nativo(modo: str):
    """The per-mode reader of a hit's own leg score, or None for a fused mode."""
    if modo == "fts":
        return lambda hit: hit.valor_fts
    if modo == "vector":
        return lambda hit: (
            None
            if hit.distancia_vector is None
            else _similitud_desde_distancia(hit.distancia_vector)
        )
    return None


def _escala_de_senal(resultado: ResultadoRecuperacion) -> tuple[list[float], str]:
    """The confidence series this run's abstention grid is built from, and its name.

    **Why a single-leg mode may not use the fused score (RJDB-002).** RRF gives
    the top hit `1/(k + 0 + 1)` from whichever legs returned it. With one leg
    that is `1/61` for EVERY question that returned anything, and `0.0` for every
    question that returned nothing — a two-valued presence/absence flag wearing a
    score's clothes. `grilla_de_umbrales` then has at most two candidates, the
    LOOCV sweep explores an outcome fixed before any data was read, and the `fts`
    and `vector` arms' abstention bars are decided by whether their leg matched
    at all. The data to do better is already carried and was being thrown away:
    `CitaRecuperada` holds `valor_fts` (ts_rank_cd) and `distancia_vector`
    (cosine distance) per hit.

    So a single-leg mode reads its own leg, transformed onto a scale that is
    monotonically increasing in relevance and bounded below by 0 (see
    `_similitud_desde_distancia`). `hybrid` keeps RRF, which is the only signal
    that exists for it: `ts_rank_cd` and cosine distance are not commensurable
    and this codebase never blends them (design.md D4).

    The two scales are never mixed inside one run. If a leg value were missing —
    structurally impossible, since in a single-leg mode every fused key came from
    that leg — the WHOLE run falls back to RRF rather than putting two
    incommensurable numbers in one grid.
    """
    lector = _lector_nativo(resultado.modo)
    if lector is not None:
        crudos = [lector(hit) for hit in resultado.hits]
        if not any(valor is None for valor in crudos):
            nombre = FUENTE_FTS if resultado.modo == "fts" else FUENTE_VECTOR
            return [float(valor) for valor in crudos if valor is not None], nombre
    # Keyed on the MODE, not on the shape of the hits. Asking `any(hit.score_rrf
    # is None ...)` reads as the same question and is not: over an empty page
    # `any([])` is False, so a `bm25_ce` run that retrieved nothing fell straight
    # through to the RRF branch and produced `top1 = 0.0` labelled "RRF
    # fusionado" — a signal from a fusion that never ran, on the arm whose whole
    # point is that its abstention signal is unratified. The empty page is
    # exactly the case an abstention grid cares most about, so it was the one
    # case the refusal leaked on.
    if resultado.modo not in service.MODOS_RRF:
        raise SenalAbstencionNoRatificada(_MOTIVO_SENAL_NO_RATIFICADA.format(modo=resultado.modo))
    crudos_rrf = [hit.score_rrf for hit in resultado.hits]
    if any(valor is None for valor in crudos_rrf):
        # Defensive backstop for an RRF mode whose fused score is missing: the
        # fused path always sets it, so reaching here means the invariant broke
        # and the same refusal applies — a threshold selected from an unratified
        # signal still prints a number, and the number decides a go/no-go nobody
        # chose (`design.md:1145-1148`, amendment A6).
        raise SenalAbstencionNoRatificada(_MOTIVO_SENAL_NO_RATIFICADA.format(modo=resultado.modo))
    return [float(valor) for valor in crudos_rrf if valor is not None], FUENTE_RRF


def senales_desde(item: GoldItem, resultado: ResultadoRecuperacion) -> SenalAbstencion:
    """Reduce one retrieval result to its abstention signal.

    A run that returned nothing scores `0.0`, not `None`: "the top hit was not
    confident enough to cite" is exactly what an empty page means, and it is the
    same decision the policy makes for a weak hit. Modelling it as missing data
    would put an `if` in front of every threshold comparison, and that `if` is
    where an empty page quietly becomes an answer. Every scale used here is
    bounded below by 0, so that `0.0` is genuinely under every real hit rather
    than merely under most of them.

    Which scale, and why it depends on the mode, is `_escala_de_senal`.
    """
    scores, fuente = _escala_de_senal(resultado)
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
        fuente_senal=fuente,
    )


def _pregunta_evaluada(
    item: GoldItem,
    resultado: ResultadoRecuperacion,
    *,
    precision_no_evaluable: bool = False,
) -> PreguntaEvaluada:
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
        precision_no_evaluable=precision_no_evaluable,
    )


def item_fuera_de_alcance(item: GoldItem, claves_exentas: frozenset[str]) -> bool:
    """Is every expected citation of this item unreachable by the running mode?

    Requires a non-empty expected set on purpose: an `unanswerable` item has no
    citations, and `set() <= anything` is vacuously true — which would mark the
    whole abstention half of the gold set exempt from a metric it is not scored
    by anyway. A partial overlap is NOT exempt either: an item that can still
    reach one of its two expected keys has a real, if capped, score.
    """
    return bool(item.citas_esperadas) and set(item.citas_esperadas).issubset(claves_exentas)


def correr_modo(
    db: Session,
    corpus_sha: str,
    gold: GoldSet,
    *,
    modo: str,
    k: int = 10,
    embedder: Embedder | None = None,
    reranker: Reranker | None = None,
) -> ResultadoModo:
    """Run every RESOLVED gold question through `service.recuperar` in one mode.

    `reranker` is threaded through for exactly the same reason `embedder` is: it
    is the dependency ONE mode needs, and `service.recuperar` is the single code
    path. Passing it here rather than constructing one inside means the eval and
    the serving path rank with the same object, and that `ranker_sintetico`
    travels up truthfully instead of being re-derived from the mode name.

    Unresolved items are skipped here and blocked at the precondition, rather
    than silently shrinking the denominator: `precondicion()` already refuses a
    go/no-go while any item is unresolved, so a partial run can produce
    diagnostics and never a verdict.
    """
    preguntas: list[PreguntaEvaluada] = []
    senales: list[SenalAbstencion] = []
    detalles: list[DetallePregunta] = []

    # Queried ONLY for a mode with no lexical leg, and only there because it is
    # only there that "no vector" means "unreachable". It also reads the dev-only
    # `embedding` column, which does not exist on the CI image — a mode that
    # never asks the vector leg for anything must not need it.
    claves_exentas: frozenset[str] = frozenset()
    if modo in MODOS_SIN_ALCANCE_LEXICO:
        claves_exentas = service.claves_sin_vector(db, corpus_sha)
    exentas_ids: list[str] = []

    # Read off the runs rather than derived from `modo`, for the same reason
    # `fuente_senal` is: the report may not name a ranker the numbers did not come
    # from. `None` stays `None` for a mode with no ranker, and one synthetic run
    # is enough to mark the whole mode synthetic — a page ordered by a stand-in
    # does not stop being noise because its neighbours were ordered by the model.
    rankers: set[str] = set()
    ranker_sintetico: bool | None = None

    for item in gold.resueltas:
        assert item.pregunta is not None  # guarded by `resueltas`; keeps mypy honest
        resultado = service.recuperar(
            db,
            corpus_sha,
            item.pregunta,
            modo=modo,
            k=k,
            embedder=embedder,
            reranker=reranker,
        )
        if resultado.reranker_modelo is not None:
            rankers.add(resultado.reranker_modelo)
        if resultado.reranker_sintetico is not None:
            ranker_sintetico = bool(ranker_sintetico) or resultado.reranker_sintetico
        fuera_de_alcance = item_fuera_de_alcance(item, claves_exentas)
        if fuera_de_alcance:
            exentas_ids.append(item.id)
        # A mode with no ratified signal gets NO signal, rather than a refusal
        # that also takes its retrieval metrics down with it. The two concerns
        # were entangled and are now not: see `MODOS_SIN_SENAL_RATIFICADA`.
        senal = senales_desde(item, resultado) if modo not in MODOS_SIN_SENAL_RATIFICADA else None
        preguntas.append(
            _pregunta_evaluada(item, resultado, precision_no_evaluable=fuera_de_alcance)
        )
        if senal is not None:
            senales.append(senal)
        detalles.append(
            DetallePregunta(
                id=item.id,
                clase=item.clase,
                pregunta=item.pregunta,
                citas_esperadas=item.citas_esperadas,
                claves_devueltas=tuple(hit.citation_key for hit in resultado.hits),
                # `0.0` is not a measurement here and is not read as one: the
                # report prints `not-evaluable` for this mode's abstention row
                # and never a top-1 score column that came from nowhere.
                score_top1=senal.score_top1 if senal is not None else 0.0,
                margen=senal.margen if senal is not None else 0.0,
                n_fts=resultado.n_fts,
                n_vector=resultado.n_vector,
                n_bm25=resultado.n_bm25,
            )
        )

    return ResultadoModo(
        modo=modo,
        k=k,
        preguntas=tuple(preguntas),
        senales=tuple(senales),
        detalles=tuple(detalles),
        metricas=metricas_recuperacion(preguntas, k=HIT_RATE_K),
        exencion=ExencionOverCeiling(
            aplica=modo in MODOS_SIN_ALCANCE_LEXICO,
            claves=tuple(sorted(claves_exentas)),
            preguntas=tuple(exentas_ids),
        ),
        # Joined rather than picked: two rankers inside one mode is not a state
        # this pipeline produces, and if it ever does the report must say so
        # instead of naming whichever one came last.
        ranker_modelo=" + ".join(sorted(rankers)) or None,
        ranker_sintetico=ranker_sintetico,
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
    reranker: Reranker | None = None,
) -> ResultadoEval:
    """The ablation: the same questions, the same k, one code path, N modes."""
    por_modo = {
        modo: correr_modo(
            db, corpus_sha, gold, modo=modo, k=k, embedder=embedder, reranker=reranker
        )
        for modo in modos
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
    #: The bar was not SCORED, as opposed to scored and failed. A `NO` in the
    #: table means "measured, below the bar"; this means "there is no measurement
    #: and inventing one would decide a go/no-go nobody chose" — today only the
    #: abstention pair of a mode with no ratified signal (task 9.1b / 9.5).
    no_evaluable: bool = False

    @property
    def pasa(self) -> bool:
        if self.valor is None:
            return False
        if self.comparador == "==":
            return self.valor == self.minimo
        return self.valor >= self.minimo


#: How each leg is named in prose, so the qualified verdict can say which leg the
#: reader is actually looking at rather than only which one failed.
_ADJETIVO_LEG = {"FTS": "léxica", "vector": "vectorial"}


@dataclass(frozen=True)
class GoNoGo:
    modo: str
    evaluable: bool
    motivos_no_evaluable: tuple[str, ...]
    barras: tuple[Barra, ...]
    #: The degraded legs of a FUSED mode, empty for a single-leg mode. A verdict
    #: over `hybrid` whose lexical leg died on most questions is a real verdict —
    #: the ablation still informs — but it is a verdict about one leg wearing a
    #: fused label, and `GO` three words above a `LEG DEGRADADA` warning is a line
    #: somebody will quote without the warning.
    legs_degradadas: tuple[str, ...] = ()

    @property
    def barras_no_evaluables(self) -> tuple[str, ...]:
        return tuple(barra.nombre for barra in self.barras if barra.no_evaluable)

    @property
    def pasa(self) -> bool:
        return self.evaluable and all(barra.pasa for barra in self.barras)

    @property
    def veredicto(self) -> str:
        """`NO EVALUABLE` also when a BAR could not be scored at all.

        A bar with no measurement must not read as a failure: `NO-GO` says the
        system was measured and fell short, and quoting that about the `bm25_ce`
        arm — whose retrieval figures may be perfectly fine — would attribute to
        the retriever a gap that belongs to an OPEN owner decision (0.1). It must
        not read as a pass either, which is why `pasa` stays False regardless.
        """
        if not self.evaluable or self.barras_no_evaluables:
            return "NO EVALUABLE"
        return "GO" if self.pasa else "NO-GO"

    @property
    def veredicto_calificado(self) -> bool:
        """Does the verdict need its scope stated to be quotable on its own?

        Deliberately NOT a reason to force `evaluable=False`: a degraded leg does
        not invalidate the measurement, it narrows what the measurement is ABOUT.
        Refusing to score would throw away the ablation's actual finding.
        """
        return self.evaluable and bool(self.legs_degradadas)

    @property
    def veredicto_con_alcance(self) -> str:
        """The verdict word, plus its scope when a leg of a fused mode is degraded."""
        if not self.veredicto_calificado:
            return self.veredicto
        degradadas = " y ".join(self.legs_degradadas)
        plural = "s" if len(self.legs_degradadas) > 1 else ""
        sanas = [
            adjetivo for leg, adjetivo in _ADJETIVO_LEG.items() if leg not in self.legs_degradadas
        ]
        alcance = (
            f"el veredicto refleja principalmente la pata {' y '.join(sanas)}"
            if sanas
            else "el veredicto no refleja ninguna pierna sana"
        )
        return f"{self.veredicto} (con leg {degradadas} degradada{plural} — {alcance})"

    @property
    def barras_fallidas(self) -> tuple[str, ...]:
        """Bars that were MEASURED and fell short. Not the unmeasured ones.

        Listing a `not-evaluable` bar under "fallan:" tells an operator the
        retriever missed a target it was never scored against — which is how an
        open owner decision gets read as a defect and then gets "fixed" by
        lowering something.
        """
        return tuple(
            barra.nombre for barra in self.barras if not barra.pasa and not barra.no_evaluable
        )


def decidir_go_no_go(
    corrida: ResultadoModo,
    gold: GoldSet,
    *,
    forzar_evaluable: bool = False,
    minimo_respondibles: int = MINIMO_RESPONDIBLES,
) -> GoNoGo:
    """Score the eight bars. The abstention pair reads the HELD-OUT figures.

    `forzar_evaluable` exists for tests that need the bar arithmetic without a
    52-item fixture. It is not exposed on the CLI, because "evaluate anyway" is
    precisely the switch the n>=20 precondition exists to remove.
    """
    precondicion = gold.precondicion(minimo_respondibles)
    metricas = corrida.metricas
    loocv = corrida.loocv
    sin_senal = not corrida.senal_ratificada
    fuente_abstencion = FUENTE_NO_RATIFICADA if sin_senal else "LOOCV held-out"

    barras = (
        Barra("hit-rate@5", metricas.hit_rate_at_5, BARRA_HIT_RATE, ">=", "answerable subset"),
        Barra(
            "hit-rate@10",
            metricas.hit_rate_at_10,
            BARRA_HIT_RATE_10,
            ">=",
            "answerable subset",
        ),
        Barra("MRR", metricas.mrr, BARRA_MRR, ">=", "answerable subset"),
        # `>=`, not `==`: the re-ratified bar is a floor at 0.33, because 1.00 is
        # unreachable by construction on this gold set.
        Barra(
            "citation-precision",
            metricas.citation_precision,
            BARRA_CITATION_PRECISION,
            ">=",
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
        #
        # …unless this mode has no ratified signal, in which case the pair was
        # never computed and says so. `valor=None` renders `n/d`, `pasa` stays
        # False, and `veredicto` becomes NO EVALUABLE rather than NO-GO.
        Barra(
            "abstention recall",
            loocv.recall if sin_senal is False else None,
            RECALL_OBJETIVO,
            "==",
            fuente_abstencion,
            no_evaluable=sin_senal,
        ),
        Barra(
            "abstention precision",
            loocv.precision if sin_senal is False else None,
            PRECISION_MINIMA,
            ">=",
            fuente_abstencion,
            no_evaluable=sin_senal,
        ),
    )

    # Only a FUSED mode can have its verdict misread as being about both legs.
    # In `fts` or `vector` the degradation is the measurement, not a caveat on it.
    degradadas: tuple[str, ...] = ()
    if corrida.modo == "hybrid":
        degradadas = tuple(
            nombre
            for nombre, degradada in (
                ("FTS", corrida.cobertura.leg_fts_degradada),
                ("vector", corrida.cobertura.leg_vector_degradada),
            )
            if degradada
        )

    motivos = () if forzar_evaluable else precondicion.motivos
    if sin_senal:
        # Appended rather than substituted: a `bm25_ce` run on a thin gold set has
        # BOTH problems and the reader needs both named.
        motivos = motivos + (
            f"modo {corrida.modo!r}: el par de abstención es `not-evaluable` — no "
            "hay señal ratificada para este arm y la decisión 0.1 del owner sigue "
            "ABIERTA. Las métricas de recuperación de arriba SÍ están medidas; lo "
            "que no puede emitirse es el veredicto de habilitación (task 9.5).",
        )

    return GoNoGo(
        modo=corrida.modo,
        evaluable=forzar_evaluable or precondicion.evaluable,
        motivos_no_evaluable=motivos,
        barras=barras,
        legs_degradadas=degradadas,
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
        "senal": corrida.fuente_senal,
        "senal_constante": corrida.senal_constante,
        "regla_de_seleccion": (
            "highest precision among thresholds reaching abstention recall 1.00; "
            "ties broken by the lower threshold. Grid = the observed values of "
            "the signal named above, with nothing appended."
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
