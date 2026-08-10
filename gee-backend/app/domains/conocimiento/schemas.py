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
