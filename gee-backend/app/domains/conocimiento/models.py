"""SQLAlchemy models for the conocimiento (RAG) domain.

See `openspec/changes/consorcio-rag/design.md` D1 for the full schema
rationale. Three deliberate deviations from the house convention
(`app/db/base.py:33`, `UUIDMixin` + timestamps on every table), all
load-bearing:

1. Natural composite primary keys (`corpus_sha` + a document/citation key)
   instead of `UUIDMixin`. The corpus's own citation keys ARE the identity —
   inventing a UUID on top would make idempotent upsert
   (`INSERT ... ON CONFLICT (corpus_sha, citation_key) DO UPDATE`) and the
   citation-key uniqueness gate need an extra join instead of being free.
2. No `TimestampMixin`. These rows are an immutable snapshot pinned to a git
   SHA — `rag_corpus.ingested_at` already records when the snapshot landed,
   and there is no mutation to timestamp afterwards.
3. `RagUnidad.embedding` (`vector(1024)`) is **not mapped** here at all. A
   mapped `Vector` column would make `Base.metadata.create_all()` try to
   create a `vector` column on the default vector-less test image
   (`postgis/postgis:16-3.4`), breaking the entire existing test suite that
   relies on that fixture. The column is created conditionally by migration
   `conocimiento_002_pgvector_embeddings` (see `ddl.py`) and is only ever
   queried via raw SQL in the retrieval repository's vector leg (design D7).
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import Computed

from app.db.base import Base

# Single source of truth for the generated FTS column expression, shared
# between this ORM mapping and migration `conocimiento_001_rag_corpus_schema`
# so the two can never drift apart. The 2-arg `to_tsvector(regconfig, text)`
# form is IMMUTABLE (required for a generated column) — the 1-arg form is
# only STABLE and Postgres rejects it here. The literal `'spanish'` is
# load-bearing, not style (design.md D1).
RAG_UNIDAD_TSV_EXPRESSION = (
    "setweight(to_tsvector('spanish', coalesce(epigrafe, '')), 'A') || "
    "setweight(to_tsvector('spanish', texto_indexado), 'B')"
)

# The non-article `tipo_chunk` taxonomy, plus `articulo` itself (design.md D2).
#
# `anexo-normativo` is the one addition to D2's six-value table, added when the
# real corpus was parsed. Three units in the pinned snapshot are normative
# content that is not articulado and belongs to no other class: the `## Anexo`
# of Ley 25.506 (the law's own definitions annex) and Anexos I and XI of Res.
# DNV 908/2026 (an un-articled procedure and a form). The MANIFEST names all
# three as content that must be indexed, and none is `seccion-secundaria` —
# they belong to derecho aplicable. They contribute 0 to the 1383 article count.
TIPO_CHUNK_VALUES = (
    "articulo",
    "considerando",
    "guia-de-uso",
    "nota-vigencia",
    "ficha-registral",
    "seccion-secundaria",
    "anexo-normativo",
)

CLASIFICACION_VALUES = ("publico", "privado")


class RagCorpus(Base):
    """A pinned snapshot of the `consorcio-corpus-legal` git repository.

    Every other table in this domain carries `corpus_sha` and every
    repository method takes it as a required positional argument — a
    forgotten snapshot filter is a `TypeError`, not silent double results
    (design.md D1).
    """

    __tablename__ = "rag_corpus"

    corpus_sha: Mapped[str] = mapped_column(CHAR(40), primary_key=True)
    repo_url: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_version: Mapped[str] = mapped_column(Text, nullable=False)
    # Counts `tipo_chunk='articulo'` units only — the MANIFEST's declared
    # total (1383). Distinct from the corpus's total row count in
    # `rag_unidad`, which also includes non-article `tipo_chunk` values
    # (considerando, guia-de-uso, nota-vigencia, ficha-registral,
    # seccion-secundaria). Renamed from `unidades_declaradas` to make that
    # scope explicit (review fold CRA-102/CRB-102).
    articulos_declarados: Mapped[int] = mapped_column(Integer, nullable=False)
    ingested_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ------------------------------------------------------------------
    # Embedding provenance (migration conocimiento_004, design.md D3)
    # ------------------------------------------------------------------
    # Which embedder produced the vectors currently sitting in
    # `rag_unidad.embedding` for THIS snapshot. All five are nullable and all
    # five are NULL together: NULL means "no vector artifact was ever loaded
    # into this snapshot", which is a real and common state (slices 1-2 ship a
    # fully ingested, fully un-embedded corpus).
    #
    # These columns exist because the sidecar used to be read, gated on, and
    # then THROWN AWAY. The dimension check that survived accepts any 1024-dim
    # model — e5-large is also 1024 and is prefix-asymmetric, so loading it
    # against a BGE-M3 corpus is a silent, total retrieval degradation — and
    # `sintetico` survived only as a CLI flag on the load, so a synthetic load
    # left no trace at all once the artifact file was overwritten. A guarantee
    # that lives only in an argv flag is one `--allow-synthetic` deep; written
    # here it survives the process, and `service.recuperar` can refuse an
    # embedder that does not match what the rows were built with (ledger
    # RAG3-001).
    embedding_modelo: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_revision_hf: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_sintetico: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # sha256 of the `vectors-{sha8}.copy` dump these vectors came from. The
    # artifact path is `vectors-{sha[:8]}.copy`, so a second batch over the same
    # snapshot OVERWRITES the first one's file and its sidecar; the hash is the
    # only record of which bytes were actually loaded.
    embedding_artifact_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    embeddings_loaded_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class RagDocumento(Base):
    """Legal-metadata row for one document inside a pinned corpus snapshot.

    PK is `(corpus_sha, documento_id)` — the same natural-key discipline D1
    applies to `rag_unidad`, extended here so a `rag_unidad` row can FK into
    exactly the document of its own snapshot, never a different one.
    """

    __tablename__ = "rag_documento"
    __table_args__ = (
        ForeignKeyConstraint(
            ["corpus_sha"],
            ["rag_corpus.corpus_sha"],
            name="fk_rag_documento_corpus",
        ),
        CheckConstraint(
            "clasificacion IN ('publico', 'privado')",
            name="ck_rag_documento_clasificacion",
        ),
        # Scoped NOT NULL (migration conocimiento_003): every document that IS
        # derecho aplicable must carry its vigencia state; only fuente
        # secundaria may omit it, because vigencia is a property of a norm.
        CheckConstraint(
            "es_secundaria OR estado_vigencia IS NOT NULL",
            name="ck_rag_documento_estado_vigencia_derecho_aplicable",
        ),
    )

    corpus_sha: Mapped[str] = mapped_column(CHAR(40), primary_key=True)
    documento_id: Mapped[str] = mapped_column(Text, primary_key=True)
    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    # Derived from `tipo` at ingestion time (D-22: `ley` == `ley-provincial`
    # is derecho aplicable; the five fuente-secundaria types never flip
    # this). Never re-derived at read time.
    es_secundaria: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # NOT NULL: one of the 11 common frontmatter keys, present in every
    # document (MANIFEST.md:230-233). A document missing it aborts
    # ingestion instead of defaulting (spec: Frontmatter Field Carriage).
    jurisdiccion: Mapped[str] = mapped_column(Text, nullable=False)
    # Nullable at the column level, NOT NULL for derecho aplicable — enforced
    # by `ck_rag_documento_estado_vigencia_derecho_aplicable` (migration
    # conocimiento_003). Three fuente-secundaria documents in the pinned corpus
    # carry no `estado_vigencia` frontmatter key at all (the two informes
    # operativos and the fallo), because vigencia is a property of a norm.
    # Inventing a placeholder for them would be exactly the fabrication the
    # ingestion spec forbids; the guarantee that matters — a norm always travels
    # with its vigencia state — is kept by the scoped CHECK.
    estado_vigencia: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Nullable: the schema must not lie about a document whose frontmatter
    # has no do-not-cite warning to carry. Carried verbatim, never derived
    # or summarized (design.md D1 — "carried, never interpreted").
    relevancia_consorcio: Mapped[str | None] = mapped_column(Text, nullable=True)
    verificacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Default-deny: the mechanical form of the privacy boundary (design.md
    # D3). A document must be explicitly marked `publico` to ever reach an
    # external embedding/judge call.
    clasificacion: Mapped[str] = mapped_column(Text, nullable=False, default="privado")
    fuente_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_sancion: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    fecha_bo: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)


class RagUnidad(Base):
    """One retrievable unit (article or non-article chunk) of a document.

    PK is the natural composite `(corpus_sha, citation_key)` — deliberate,
    documented deviation from `app/db/base.py:33`'s `UUIDMixin` default
    (design.md D1). `citation_key` is taken verbatim from the corpus's own
    MANIFEST convention, never re-derived or invented.
    """

    __tablename__ = "rag_unidad"
    __table_args__ = (
        ForeignKeyConstraint(
            ["corpus_sha", "documento_id"],
            ["rag_documento.corpus_sha", "rag_documento.documento_id"],
            name="fk_rag_unidad_documento",
        ),
        CheckConstraint(
            "tipo_chunk IN (" + ",".join(f"'{value}'" for value in TIPO_CHUNK_VALUES) + ")",
            name="ck_rag_unidad_tipo_chunk",
        ),
        Index("ix_rag_unidad_tsv", "tsv", postgresql_using="gin"),
        Index("ix_rag_unidad_documento", "corpus_sha", "documento_id"),
    )

    corpus_sha: Mapped[str] = mapped_column(CHAR(40), primary_key=True)
    citation_key: Mapped[str] = mapped_column(Text, primary_key=True)
    documento_id: Mapped[str] = mapped_column(Text, nullable=False)
    tipo_chunk: Mapped[str] = mapped_column(Text, nullable=False)
    # Nullable: not every unit has a distinct heading beyond its citation
    # key (e.g. a bare `Art. 5`). Weighted 'A' (higher) in the tsv when
    # present, coalesced to '' when absent.
    epigrafe: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Verbatim, byte-exact substring of `source_file` — the ONLY thing ever
    # shown as a citation (design.md "Verbatim vs indexable text").
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    # title + structural path + `texto` — what FTS and the embedder see.
    # Enrichment can never leak into a citation because `texto` (above) is
    # the only field ever surfaced as one.
    texto_indexado: Mapped[str] = mapped_column(Text, nullable=False)
    source_file: Mapped[str] = mapped_column(Text, nullable=False)
    source_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(RAG_UNIDAD_TSV_EXPRESSION, persisted=True),
        nullable=True,
    )

    # `embedding vector(1024)` is deliberately NOT mapped — see module
    # docstring point 3 and `ddl.py`.
