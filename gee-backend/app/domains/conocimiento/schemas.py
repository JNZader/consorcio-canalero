"""Pydantic v2 result shapes for the conocimiento ingestion pipeline.

House pattern (`app/domains/*/schemas.py`) minus a `router.py`: V0 ships no HTTP
surface at all, so these are script/report shapes, not request/response bodies
(design.md D8).
"""

from __future__ import annotations

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
