"""Pydantic v2 result shapes for the conocimiento pipeline and its HTTP surface.

House pattern (`app/domains/*/schemas.py`). Most of this file is script/report
shapes from V0's ingestion pipeline; the block at the bottom is U7's request and
response bodies for the mailbox (`router.py`, amendment A3).
"""

from __future__ import annotations

import datetime
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DocumentoIngestado(BaseModel):
    """Per-document outcome of one ingestion run."""

    model_config = ConfigDict(from_attributes=True)

    documento_id: str
    archivo: str
    tipo: str
    es_secundaria: bool
    articulos: int
    no_articulos: int


class UnidadSobreCeiling(BaseModel):
    """A unit whose indexed text exceeds the embedding model's context ceiling."""

    model_config = ConfigDict(from_attributes=True)

    citation_key: str
    tokens: int


class GateOutcome(BaseModel):
    """Aggregate gate result. `ok` False means nothing was committed."""

    model_config = ConfigDict(from_attributes=True)

    ok: bool
    articulos_total: int
    no_articulos_total: int
    documentos: int
    failures: list[str] = Field(default_factory=list)
    #: Units over the 8192-token embedding ceiling. NOT a failure: the ceiling
    #: is an embedding constraint and these units are ingested whole and stay
    #: fully retrievable by FTS. Carried here because `GateReport.over_ceiling`
    #: was populated and then reached no output at all — "always reported" was
    #: true of the dataclass and false of everything a human sees (RAG2-004).
    over_ceiling: list[UnidadSobreCeiling] = Field(default_factory=list)


class IngestionSummary(BaseModel):
    """What `scripts/rag_ingest.py` reports after a run."""

    model_config = ConfigDict(from_attributes=True)

    corpus_sha: str
    repo_url: str
    manifest_version: str
    #: `tipo_chunk='articulo'` only — the MANIFEST's declared total. Distinct
    #: from `unidades_escritas`, which includes non-article units.
    articulos_declarados: int
    unidades_escritas: int
    unidades_eliminadas: int = 0
    documentos: list[DocumentoIngestado] = Field(default_factory=list)
    gates: GateOutcome
    #: `--verify-unchanged`, class 1 of 3: keys present in BOTH the snapshot and
    #: the new parse whose `texto` changed while the corpus_sha did not.
    divergencias: list[str] = Field(default_factory=list)
    #: Class 2: keys the new parse produces that the stored snapshot lacks.
    claves_agregadas: list[str] = Field(default_factory=list)
    #: Class 3: keys the stored snapshot has that the new parse does not produce
    #: — the ones a normal run PRUNES. Comparing only the intersection made this
    #: class invisible, so `--verify-unchanged` deleted rows it never examined
    #: and still reported "divergencias: []" (RAG2-003).
    claves_eliminadas: list[str] = Field(default_factory=list)
    committed: bool = False

    @property
    def verificacion_fallida(self) -> bool:
        """True when `--verify-unchanged` found ANY of the three differences.

        The three classes stay separate in the report because they mean
        different things — content rewritten, unit added, unit dropped — but any
        one of them must stop the run before it writes.
        """
        return bool(self.divergencias or self.claves_agregadas or self.claves_eliminadas)


class CitaRecuperada(BaseModel):
    """One retrieval hit, with everything needed to cite it responsibly.

    The provenance block is not decoration. `tipo` and `es_secundaria` separate
    norm from evidence; `estado_vigencia` is what keeps a derogated article from
    being read as live law; and `relevancia_consorcio` covers the case the other
    two cannot — a document that IS derecho aplicable by `tipo` and still must
    not be cited as grounds for a canalero obligation (design.md D1/D4).

    `texto` is the verbatim, byte-exact unit text. It is the ONLY field ever
    shown as a citation: `texto_indexado` (title + structural path + text) is
    what the legs search, and it deliberately never appears here.
    """

    model_config = ConfigDict(from_attributes=True)

    citation_key: str
    documento_id: str
    tipo_chunk: str
    epigrafe: str | None = None
    texto: str

    tipo: str
    es_secundaria: bool
    jurisdiccion: str
    estado_vigencia: str | None = None
    relevancia_consorcio: str | None = None
    verificacion: str | None = None
    fuente_url: str | None = None
    source_file: str
    source_offset: int

    #: Fused RRF score. A sum of `1/(k+rank+1)` terms — NOT a blend of the legs'
    #: own metrics, which are not commensurable and are never combined. `None` in
    #: `bm25_ce`, which does not fuse anything: its order is the cross-encoder's
    #: alone, and reporting an RRF number there would name a computation that
    #: never ran.
    score_rrf: float | None = None
    #: The cross-encoder logit that ORDERED this page, in `bm25_ce` only. It is
    #: the ranking score in full: no lexical term is blended into it, because
    #: every measured blend made retrieval worse (`design.md:1136-1138`).
    score_ce: float | None = None
    #: Per-leg position and raw metric, `None` when the leg did not return the
    #: unit at all. Carried so the eval report can show what each leg actually
    #: saw rather than only the fused outcome (design.md D6).
    rango_fts: int | None = None
    valor_fts: float | None = None
    rango_vector: int | None = None
    distancia_vector: float | None = None
    #: Where BM25 placed this unit in the candidate pool, and with what score.
    #: Carried for disclosure only — it is what SELECTED the unit and explicitly
    #: not what ranked it.
    rango_bm25: int | None = None
    valor_bm25: float | None = None


class ResultadoRecuperacion(BaseModel):
    """One retrieval run: the fused page plus how each leg contributed."""

    model_config = ConfigDict(from_attributes=True)

    corpus_sha: str
    pregunta: str
    modo: str
    k: int
    hits: list[CitaRecuperada] = Field(default_factory=list)
    #: Candidates each leg returned BEFORE fusion and before `k` truncation.
    n_fts: int = 0
    n_vector: int = 0
    #: Size of the BM25 candidate pool that reached the reranker (`bm25_ce`).
    n_bm25: int = 0
    #: Identity of the ranker that produced the order, in `bm25_ce`. Carried for
    #: the same reason `rag_corpus` records which model wrote the embeddings: a
    #: ranking is only interpretable next to the thing that produced it, and a
    #: synthetic ranker must be visible rather than inferred.
    reranker_modelo: str | None = None
    reranker_sintetico: bool | None = None


class Redireccion(BaseModel):
    """Where a non-legal question (or the non-legal half of a `mixto`) belongs.

    Carries NO answer surface — no prose, no figure, no citation (routing
    spec:38). A redirect with an answer field is one refactor away from having
    an answer in it.
    """

    model_config = ConfigDict(from_attributes=True)

    superficie: str
    motivo: str


class RespuestaConocimiento(BaseModel):
    """One item of the bandeja. `estado` is the LEGAL leg; the redirect is not.

    `estado` holds SIX mutually exclusive values (`design.md:711-749`, plus
    `pendiente` from amendment A3) and `redireccion_parcial` is ORTHOGONAL to
    all of them: it answers a different question ("was part of this
    non-legal?") than `estado` does ("what happened to the legal part?"). That
    is what makes `mixto` representable at all — a single mutually-exclusive tag
    could not hold `abstencion` and `redireccion` at once, and the routing spec
    requires the redirect to SURVIVE the legal part abstaining.

    `estado='redireccion'` is the PURE redirect and never carries a partial one:
    a partial redirect alongside a total one would be the same fact twice.

    `generacion_fallida` carries no prose and no rejected draft. That is a
    validated invariant here, not a convention the caller is trusted to keep.

    The invariants run in both directions. The non-answer states carry no prose
    and no citations; `respuesta` carries BOTH, non-empty. An answer-shaped item
    with neither is the one shape U8 must never render, and it is unconstructible
    rather than merely undocumented.
    """

    model_config = ConfigDict(from_attributes=True)

    estado: Literal[
        "pendiente",
        "respuesta",
        "abstencion",
        "redireccion",
        "generacion_fallida",
        "no_disponible",
    ]
    respuesta: str | None = None
    #: Exactly the POST-EXCLUSION payload, so the panel physically cannot render
    #: a card for a unit the generator never saw (G6, `design.md:765-768`).
    citas: list[CitaRecuperada] = Field(default_factory=list)
    #: Retrieved and dropped by the classification gate. The keys only — never
    #: the text, never the provenance of a unit that may not travel.
    claves_excluidas: list[str] = Field(default_factory=list)
    motivo: str | None = None
    #: The enforcement violations of the LAST rejected draft, on an abstention.
    #: The violations, not the draft: the draft is never surfaced.
    violaciones: list[str] = Field(default_factory=list)
    intentos: int = 0
    llamadas_proveedor: int = 0
    #: The PURE redirect's surface, present iff `estado='redireccion'`.
    #:
    #: Added in U7. `design.md:775-777` says the pure redirect "carries no answer,
    #: no citation and no `redireccion_parcial` — the redirect IS the response",
    #: and the round-1 schema gave it nowhere to say WHERE. `estado='redireccion'`
    #: was therefore constructible but empty: a redirect that names no surface is
    #: the thing the whole router exists to avoid. This is the pure slot;
    #: `redireccion_parcial` remains the orthogonal one, and the validator below
    #: makes them mutually exclusive so the same fact is never carried twice.
    redireccion: Redireccion | None = None
    redireccion_parcial: Redireccion | None = None

    def model_post_init(self, __context: object) -> None:
        if self.estado == "redireccion" and self.redireccion is None:
            raise ValueError(
                "estado='redireccion' requires the surface it redirects TO. The "
                "redirect is the whole response (design.md:775-777); one that "
                "names no surface tells the reader their question was refused "
                "and nothing else."
            )
        if self.estado != "redireccion" and self.redireccion is not None:
            raise ValueError(
                f"estado={self.estado!r} must not carry a PURE redirect: the "
                "orthogonal block is `redireccion_parcial`. Two fields holding "
                "the same fact is how a partial redirect starts reading as a "
                "total one."
            )
        if self.estado == "generacion_fallida" and self.respuesta is not None:
            raise ValueError(
                "generacion_fallida carries no prose and no rejected draft "
                "(generation spec:79-87). Surfacing the last draft is exactly "
                "the uncertified answer the enforcement refused to serve."
            )
        if self.estado == "redireccion" and self.redireccion_parcial is not None:
            raise ValueError(
                "estado='redireccion' is the PURE redirect and never carries a "
                "partial one (design.md:730-732)."
            )
        if self.estado != "respuesta" and self.respuesta is not None:
            raise ValueError(
                f"estado={self.estado!r} must carry no answer prose; only 'respuesta' does."
            )
        if self.estado != "respuesta" and self.citas:
            raise ValueError(
                f"estado={self.estado!r} must carry no citations: a citation "
                "block next to a non-answer reads as a partial answer."
            )
        if self.estado == "respuesta":
            # The POSITIVE half of the invariant. The four rules above are all
            # negative — they say what the non-answer states must not carry — and
            # negative rules alone leave `estado='respuesta', respuesta=None,
            # citas=[]` constructible: an answer-shaped item with no answer and
            # no grounds, which U8 would render as a blank card under a heading
            # that promises a legal answer. The shape the panel must never render
            # is made unconstructible here rather than trusted not to occur.
            if not (self.respuesta or "").strip():
                raise ValueError(
                    "estado='respuesta' requires answer prose. An empty answer is "
                    "an abstención, a generacion_fallida or a no_disponible, and "
                    "which one it is is information the caller is owed."
                )
            if not self.citas:
                raise ValueError(
                    "estado='respuesta' requires at least one citation. The whole "
                    "enforcement chain exists so that no served claim is uncited; "
                    "an answer with an empty citation block is that failure "
                    "reaching the reader with the panel showing nothing amiss."
                )


# ---------------------------------------------------------------------------
# U7 — the mailbox's HTTP bodies (amendment A3, `design.md:1344-1348`)
# ---------------------------------------------------------------------------


class PreguntaEntrada(BaseModel):
    """The submit body. One field, because the surface asks one thing."""

    model_config = ConfigDict(extra="forbid")

    pregunta: str


class ConsultaEncolada(BaseModel):
    """What `POST /preguntas` returns: an identifier and `pendiente`.

    It NEVER carries an answer. That is the whole restructuring of A3: the
    submit call cannot answer, because answering needs a GPU whose availability
    is intermittent by design, and a request that waited for it would be a CD
    member watching a spinner for an outcome the queue can deliver honestly.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    estado: Literal["pendiente"] = "pendiente"
    creada_en: datetime.datetime


class ItemBuzon(BaseModel):
    """One row of the bandeja: the question, its state, the answer when it exists.

    `demorado` is A3's honesty obligation made a field rather than a UI guess:
    "pendiente" is only honest while it is true, so a `pendiente` older than the
    configured window says so here and the panel renders that instead of an
    indefinite spinner.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pregunta: str
    estado: Literal[
        "pendiente",
        "respuesta",
        "abstencion",
        "redireccion",
        "generacion_fallida",
        "no_disponible",
    ]
    creada_en: datetime.datetime
    procesada_en: datetime.datetime | None = None
    demorado: bool = False
    #: Absent exactly while `estado='pendiente'` — nothing has been decided yet.
    respuesta: RespuestaConocimiento | None = None


class EstadoBuzon(BaseModel):
    """The admin diagnostic (`GET /estado`, tasks 7.6 + A3).

    This is where a permanently-misconfigured worker becomes visible, because
    under A3 it is no longer a per-question 503: a GPU that is not currently up
    is the normal case and items simply stay `pendiente`. The three queue fields
    are what separate "the worker is between batches" from "the worker has been
    down for a day", and neither is inferable from a single item.
    """

    model_config = ConfigDict(from_attributes=True)

    #: Provenance of the vectors in the active snapshot. `sintetico=True` is a
    #: snapshot serving REFUSES to answer from (task 7.6).
    corpus_sha: str | None = None
    embedding_modelo: str | None = None
    embedding_sintetico: bool | None = None
    embeddings_loaded_at: datetime.datetime | None = None
    #: The three ANDed enablement facts, reported rather than enforced here — a
    #: diagnostic that refuses when the thing it diagnoses is broken is not a
    #: diagnostic. `None` means "not checked", never "fine".
    terminos_verificados: bool | None = None
    credencial_presente: bool | None = None
    embedder_listo: bool | None = None
    causa_no_listo: str | None = None
    profundidad_cola: int = 0
    mas_antiguo_pendiente: datetime.datetime | None = None
    ultima_corrida_worker: datetime.datetime | None = None
    #: True when the oldest pending item has been waiting past the window. The
    #: operational fault A3 moved OFF the per-question path lands here.
    worker_demorado: bool = False
