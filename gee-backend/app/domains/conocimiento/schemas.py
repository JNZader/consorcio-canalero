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


class GateOutcome(BaseModel):
    """Aggregate gate result. `ok` False means nothing was committed."""

    model_config = ConfigDict(from_attributes=True)

    ok: bool
    articulos_total: int
    no_articulos_total: int
    documentos: int
    failures: list[str] = Field(default_factory=list)


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
    #: Populated only by `--verify-unchanged`: citation keys whose `texto`
    #: changed while the corpus_sha did not. A non-empty list means the run
    #: reported a divergence INSTEAD of overwriting it.
    divergencias: list[str] = Field(default_factory=list)
    committed: bool = False
