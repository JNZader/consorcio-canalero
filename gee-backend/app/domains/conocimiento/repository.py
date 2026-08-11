"""Data access for the conocimiento (RAG) domain: ingestion write path + retrieval.

Two rules govern everything here.

**Snapshot isolation.** Every function takes `corpus_sha` as a required
positional argument. A forgotten snapshot filter is a `TypeError`, not silent
double results (design.md D1).

**Carried, never interpreted.** `jurisdiccion`, `relevancia_consorcio`,
`estado_vigencia` and `verificacion` are copied verbatim out of the document
frontmatter and surfaced as-is. V0 derives no boolean from
`relevancia_consorcio`: a regex over legal prose is exactly the silent
misclassification this design refuses.

The retrieval half adds a third: **the vector leg fails loudly or not at all**
(design.md D4). It never falls back to FTS, because a hybrid mode that quietly
became FTS-only would make the whole three-mode ablation a comparison of FTS
against itself.
"""

from __future__ import annotations

import datetime
import hashlib
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.conocimiento.ddl import EMBEDDING_COLUMN, EMBEDDING_DIMENSIONS, EMBEDDING_TABLE
from app.domains.conocimiento.embedding import vector_literal
from app.domains.conocimiento.parser import Unidad

# D-22, registered in the MANIFEST and deliberately NOT fixed in the corpus:
# `ley-8803` declares `tipo: ley` while the other fourteen provincial laws
# declare `tipo: ley-provincial`. Correcting metadata by hand during
# consolidation is how silent errors get in, so the ingestor normalizes instead.
TIPO_SINONIMOS: dict[str, str] = {"ley": "ley-provincial"}

# The five fuente-secundaria types. NOT derecho aplicable: an answer that cites
# one of these as if it were a norm is citing someone's report with the face of
# a rule — the precise failure this corpus exists to prevent.
TIPOS_SECUNDARIOS: frozenset[str] = frozenset(
    {
        "informe-operativo",
        "jurisprudencia",
        "caso-testigo",
        "informe-auditoria",
        "artefacto-geoespacial-derivado",
    }
)

TIPOS_DERECHO_APLICABLE: frozenset[str] = frozenset(
    {
        "ley-provincial",
        "ley-nacional",
        "decreto",
        "decreto-provincial",
        "resolucion-ministerial",
        "resolucion-nacional",
        "resolucion-administrativa",
        "norma-tecnica",
        "registro-administrativo",
    }
)


class IngestionAbort(RuntimeError):
    """Base class for every condition that must stop ingestion before a write."""


class JurisdiccionFaltante(IngestionAbort):
    """A document's frontmatter has no `jurisdiccion` key.

    `jurisdiccion` is one of the MANIFEST's common frontmatter keys and is the
    declared provincial/nacional filter. Defaulting it would silently place a
    national norm in the provincial bucket, so ingestion aborts instead.
    """


def normalize_tipo(tipo: str) -> str:
    """Apply the MANIFEST's declared type synonyms (D-22)."""
    return TIPO_SINONIMOS.get(tipo, tipo)


def es_secundaria_for(tipo: str) -> bool:
    """Classify a document type as fuente secundaria or derecho aplicable.

    Unknown types raise rather than defaulting: a new `tipo` silently treated as
    derecho aplicable is how a future report starts being cited as a norm.
    """
    normalized = normalize_tipo(tipo)
    if normalized in TIPOS_SECUNDARIOS:
        return True
    if normalized in TIPOS_DERECHO_APLICABLE:
        return False
    raise ValueError(
        f"unknown document tipo {tipo!r}. Add it to TIPOS_SECUNDARIOS or "
        "TIPOS_DERECHO_APLICABLE explicitly — an unclassified type must never "
        "default to derecho aplicable."
    )


def _first_url(value: Any) -> str | None:
    """Frontmatter `fuente_url` is sometimes a scalar and sometimes a list."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else None
    return str(value)


def _as_date(value: Any) -> datetime.date | None:
    if value is None or isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError:
        # The corpus records a few dates as free text ("1965", "sin fecha").
        # Losing the ordering hint is acceptable; inventing a date is not.
        return None


def documento_row_from_frontmatter(
    corpus_sha: str,
    documento_id: str,
    frontmatter: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the `rag_documento` row for one document. Pure — no DB access."""
    if "jurisdiccion" not in frontmatter or not str(frontmatter["jurisdiccion"]).strip():
        raise JurisdiccionFaltante(
            f"{documento_id}: frontmatter has no `jurisdiccion`. Ingestion aborts "
            "before writing any row rather than defaulting it."
        )

    tipo = normalize_tipo(str(frontmatter["tipo"]))
    es_secundaria = es_secundaria_for(tipo)
    estado_vigencia = frontmatter.get("estado_vigencia")

    if estado_vigencia is None and not es_secundaria:
        raise IngestionAbort(
            f"{documento_id}: derecho aplicable with no `estado_vigencia`. Every "
            "norm must travel with its vigencia state; only fuente secundaria "
            "may omit it."
        )

    return {
        "corpus_sha": corpus_sha,
        "documento_id": documento_id,
        "tipo": tipo,
        "es_secundaria": es_secundaria,
        "jurisdiccion": str(frontmatter["jurisdiccion"]),
        "estado_vigencia": None if estado_vigencia is None else str(estado_vigencia),
        # Verbatim or NULL. Never summarized, never invented.
        "relevancia_consorcio": (
            None
            if frontmatter.get("relevancia_consorcio") is None
            else str(frontmatter["relevancia_consorcio"])
        ),
        "verificacion": (
            None if frontmatter.get("verificacion") is None else str(frontmatter["verificacion"])
        ),
        # Default-deny (design.md D3). Nothing in V0 promotes a document to
        # `publico`; the hosted-embedding leg stays unreachable by construction.
        "clasificacion": "privado",
        "fuente_url": _first_url(frontmatter.get("fuente_url")),
        "fecha_sancion": _as_date(frontmatter.get("fecha_sancion")),
        "fecha_bo": _as_date(frontmatter.get("fecha_bo")),
    }


UPSERT_CORPUS_SQL = text(
    """
    INSERT INTO rag_corpus (corpus_sha, repo_url, manifest_version,
                            articulos_declarados, activo)
    VALUES (:corpus_sha, :repo_url, :manifest_version, :articulos_declarados, :activo)
    ON CONFLICT (corpus_sha) DO UPDATE SET
        repo_url = EXCLUDED.repo_url,
        manifest_version = EXCLUDED.manifest_version,
        articulos_declarados = EXCLUDED.articulos_declarados,
        activo = EXCLUDED.activo
    """
)

UPSERT_DOCUMENTO_SQL = text(
    """
    INSERT INTO rag_documento (corpus_sha, documento_id, tipo, es_secundaria,
                               jurisdiccion, estado_vigencia, relevancia_consorcio,
                               verificacion, clasificacion, fuente_url,
                               fecha_sancion, fecha_bo)
    VALUES (:corpus_sha, :documento_id, :tipo, :es_secundaria, :jurisdiccion,
            :estado_vigencia, :relevancia_consorcio, :verificacion, :clasificacion,
            :fuente_url, :fecha_sancion, :fecha_bo)
    ON CONFLICT (corpus_sha, documento_id) DO UPDATE SET
        tipo = EXCLUDED.tipo,
        es_secundaria = EXCLUDED.es_secundaria,
        jurisdiccion = EXCLUDED.jurisdiccion,
        estado_vigencia = EXCLUDED.estado_vigencia,
        relevancia_consorcio = EXCLUDED.relevancia_consorcio,
        verificacion = EXCLUDED.verificacion,
        clasificacion = EXCLUDED.clasificacion,
        fuente_url = EXCLUDED.fuente_url,
        fecha_sancion = EXCLUDED.fecha_sancion,
        fecha_bo = EXCLUDED.fecha_bo
    """
)

# `COPY` has no upsert and every row already exists after the first run, so the
# unit write path is an explicit ON CONFLICT DO UPDATE keyed on the natural PK.
UPSERT_UNIDAD_SQL = text(
    """
    INSERT INTO rag_unidad (corpus_sha, citation_key, documento_id, tipo_chunk,
                            epigrafe, texto, texto_indexado, source_file, source_offset)
    VALUES (:corpus_sha, :citation_key, :documento_id, :tipo_chunk, :epigrafe,
            :texto, :texto_indexado, :source_file, :source_offset)
    ON CONFLICT (corpus_sha, citation_key) DO UPDATE SET
        documento_id = EXCLUDED.documento_id,
        tipo_chunk = EXCLUDED.tipo_chunk,
        epigrafe = EXCLUDED.epigrafe,
        texto = EXCLUDED.texto,
        texto_indexado = EXCLUDED.texto_indexado,
        source_file = EXCLUDED.source_file,
        source_offset = EXCLUDED.source_offset
    """
)


def upsert_corpus(
    db: Session,
    corpus_sha: str,
    *,
    repo_url: str,
    manifest_version: str,
    articulos_declarados: int,
    activo: bool = True,
) -> None:
    db.execute(
        UPSERT_CORPUS_SQL,
        {
            "corpus_sha": corpus_sha,
            "repo_url": repo_url,
            "manifest_version": manifest_version,
            "articulos_declarados": articulos_declarados,
            "activo": activo,
        },
    )


def upsert_documento(db: Session, corpus_sha: str, row: Mapping[str, Any]) -> None:
    if row["corpus_sha"] != corpus_sha:
        raise IngestionAbort(
            f"document row belongs to snapshot {row['corpus_sha']}, not {corpus_sha}"
        )
    db.execute(UPSERT_DOCUMENTO_SQL, dict(row))


def upsert_unidades(
    db: Session,
    corpus_sha: str,
    documento_id: str,
    source_file: str,
    unidades: Iterable[Unidad],
) -> int:
    rows = [
        {
            "corpus_sha": corpus_sha,
            "citation_key": unidad.citation_key,
            "documento_id": documento_id,
            "tipo_chunk": unidad.tipo_chunk,
            "epigrafe": unidad.epigrafe,
            "texto": unidad.texto,
            "texto_indexado": unidad.texto_indexado,
            "source_file": source_file,
            "source_offset": unidad.source_offset,
        }
        for unidad in unidades
    ]
    if rows:
        db.execute(UPSERT_UNIDAD_SQL, rows)
    return len(rows)


def prune_unidades(db: Session, corpus_sha: str, keep: Sequence[str]) -> int:
    """Delete units of this snapshot that the current run did NOT produce.

    `ON CONFLICT DO UPDATE` alone makes re-ingestion *additive*: a unit that
    disappeared between two runs of the same `corpus_sha` would survive forever
    as a stale row that still answers queries. Pruning is what makes the
    determinism claim literal — same corpus SHA in, byte-identical DB state out,
    not merely a superset of it.
    """
    result = db.execute(
        text(
            "DELETE FROM rag_unidad WHERE corpus_sha = :corpus_sha "
            "AND NOT (citation_key = ANY(:keep))"
        ),
        {"corpus_sha": corpus_sha, "keep": list(keep)},
    )
    # `rowcount` lives on CursorResult, which is what a DELETE returns; the
    # base Result protocol mypy infers does not declare it.
    return getattr(result, "rowcount", 0) or 0


def existing_text_hashes(db: Session, corpus_sha: str) -> dict[str, str]:
    """`{citation_key: sha256(texto)}` for an already-present snapshot.

    Backs `--verify-unchanged`: it turns a silent rewrite into a diff. Hashed in
    Python rather than with `digest()` so it does not depend on `pgcrypto` being
    installed — at ~1.4 k rows the transfer cost is irrelevant, and an optional
    extension is not worth a hard dependency.
    """
    rows = db.execute(
        text("SELECT citation_key, texto FROM rag_unidad WHERE corpus_sha = :corpus_sha"),
        {"corpus_sha": corpus_sha},
    ).all()
    return {row[0]: hashlib.sha256(row[1].encode("utf-8")).hexdigest() for row in rows}


def count_unidades(db: Session, corpus_sha: str, tipo_chunk: str | None = None) -> int:
    sql = "SELECT count(*) FROM rag_unidad WHERE corpus_sha = :corpus_sha"
    params: dict[str, Any] = {"corpus_sha": corpus_sha}
    if tipo_chunk is not None:
        sql += " AND tipo_chunk = :tipo_chunk"
        params["tipo_chunk"] = tipo_chunk
    return int(db.execute(text(sql), params).scalar_one())


# ---------------------------------------------------------------------------
# Retrieval — two independent legs (design.md D4)
# ---------------------------------------------------------------------------

#: Per-leg candidate depth. Deep enough that RRF has something to fuse, shallow
#: enough that the fused list stays interpretable in the eval report.
LEG_LIMIT = 50


class VectorSupportUnavailable(RuntimeError):
    """The vector leg cannot run here — and that is an error, never a fallback.

    Raised when the `vector` extension is not installed or `rag_unidad.embedding`
    does not exist (the CI-safe, vector-less image, or a database where migration
    002 took its no-op branch). Degrading to FTS instead would make `--mode
    hybrid` silently identical to `--mode fts`, and the ablation would report a
    comparison it never ran (design.md D4).
    """


@dataclass(frozen=True)
class LegHit:
    """One leg's opinion about one unit.

    `valor` is the leg's OWN metric — `ts_rank_cd` for FTS (higher is better),
    cosine distance for the vector leg (lower is better). The two are not
    commensurable and are never combined: only `rango` reaches fusion. `valor`
    is carried purely so the eval report can show what each leg actually saw
    (design.md D6).
    """

    citation_key: str
    rango: int
    valor: float


def vector_support(db: Session) -> bool:
    """Is the vector leg runnable in THIS database right now?

    Checks both halves, because either one alone is a false positive: the
    extension can be installed while the column is missing (migration 002
    no-opped on an earlier boot), and the column cannot exist without the
    extension but the reverse is exactly the stranded-volume case design D7
    documents.
    """
    return bool(
        db.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') "
                "AND EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :tabla AND column_name = :columna)"
            ),
            {"tabla": EMBEDDING_TABLE, "columna": EMBEDDING_COLUMN},
        ).scalar_one()
    )


def require_vector_support(db: Session) -> None:
    if not vector_support(db):
        raise VectorSupportUnavailable(
            "the `vector` extension or `rag_unidad.embedding` is missing from this "
            "database, so the vector leg cannot run. This is NOT a reason to fall "
            "back to FTS: a hybrid run that silently became FTS-only would report "
            "an ablation it never performed. Start the dev database with "
            "`make rag-db` (consorcio-postgres:16-vector) and re-run "
            "`alembic upgrade head`."
        )


#: The lexical leg's query operator, named here so the eval report can print it.
#: The ablation compares legs, and a leg whose operator is not disclosed is a
#: measurement of something the reader cannot name (ledger RAG4-001).
FTS_OPERADOR = "OR — disyunción de los lexemas que parsea websearch_to_tsquery"

FTS_SEARCH_SQL = text(
    """
    WITH terminos AS (
        SELECT unnest(
            string_to_array(websearch_to_tsquery('spanish', :consulta)::text, ' & ')
        ) AS termino
    ),
    partes AS (
        SELECT
            string_agg(termino, ' | ') FILTER (WHERE left(termino, 1) <> '!') AS positivos,
            string_agg(termino, ' & ') FILTER (WHERE left(termino, 1) = '!') AS exclusiones
        FROM terminos
    ),
    consulta AS (
        SELECT CAST(
            CASE
                WHEN positivos IS NULL OR positivos = '' THEN ''
                WHEN exclusiones IS NULL THEN positivos
                ELSE '(' || positivos || ') & ' || exclusiones
            END AS tsquery
        ) AS q
        FROM partes
    )
    SELECT u.citation_key, ts_rank_cd(u.tsv, consulta.q, 32) AS valor
    FROM rag_unidad u, consulta
    WHERE u.corpus_sha = :corpus_sha AND u.tsv @@ consulta.q
    ORDER BY ts_rank_cd(u.tsv, consulta.q, 32) DESC, u.citation_key ASC
    LIMIT :limite
    """
)


def fts_search(
    db: Session,
    corpus_sha: str,
    consulta: str,
    limite: int = LEG_LIMIT,
) -> list[LegHit]:
    """FTS-español leg. Runs on the CI-safe image — no pgvector anywhere near it.

    **The leg ORs its lexemes, and that is the whole point of it (ledger
    RAG4-001).** `websearch_to_tsquery` builds a CONJUNCTION, and a conjunction
    over a colloquial question is not a weak ranking — it is an empty result set,
    because the `&` sits in the `WHERE` clause and `ts_rank_cd` never runs.
    Measured against the pinned corpus, six of six sampled gold questions
    returned **zero rows**: gold item D-1 compiles to eleven ANDed lexemes and no
    article in 1 448 units carries all eleven. Under that operator the FTS-only
    arm of the ablation measures the query builder, `hybrid` silently degenerates
    into vector-only while keeping the fused label, and the premise slices 1-2
    were justified on ("FTS-only still works") is false. Same six questions under
    the disjunction: a full 50-candidate leg every time, and the gold key inside
    the candidate set for four of them.

    **Why the parse is round-tripped through `::tsquery` and not through
    `to_tsquery`.** The obvious construction — feed the parsed text back into
    `to_tsquery('spanish', …)` — re-applies the Spanish dictionary to lexemes
    that were already stemmed, and the Snowball stemmer is NOT idempotent.
    Measured: `intervenir` indexes as `interven`, which matches 13 units; stem it
    twice and it becomes `interv`, which matches **zero**. That construction
    looks like a fix and silently loses recall on exactly the words the question
    is about. `tsquery_in` (the `CAST(… AS tsquery)`) applies no dictionary at
    all, so `websearch_to_tsquery(…)::text::tsquery` is a pure round trip:
    tsquery_out wrote the text, tsquery_in reads it back, and the only edit in
    between is which operator joins the top-level terms.

    **Injection.** The user's question reaches SQL only as the bound parameter of
    `websearch_to_tsquery`, which is total (it never raises on syntax) and whose
    output is a tsquery whose lexemes are already quoted and escaped. Nothing
    that comes back out is user text; it is a normalised lexeme list. The split
    on `' & '` is safe because the default parser cannot emit a lexeme containing
    a space, so the separator cannot occur inside a quoted term.

    **Exclusions survive.** `websearch`'s `-palabra` compiles to `!'palabr'`, and
    ORing that in would match every document NOT containing the word — a recall
    explosion wearing the fix's name. The terms are partitioned instead: the
    positives are ORed, the exclusions stay ANDed, so `canal -riego` keeps
    meaning "canal, but not riego". When a question mixes `or` and `-` in a way
    the top-level split cannot cleanly partition, the result is websearch's own
    query unchanged — never invalid, never MORE restrictive than the conjunction
    it replaces. Every one of those shapes is pinned in
    `test_rag_retrieval.py::TestFtsOperador`.

    **There is no retry and no fallback.** One operator runs, always, and the
    report names it (`FTS_OPERADOR`). An automatic AND-then-OR retry would be the
    silent degradation design D4 forbids for the vector leg, arriving on the
    lexical side.

    A question that reduces to nothing — empty, whitespace, only stopwords, only
    an exclusion — builds the empty tsquery, which matches no row. Zero hits is a
    legitimate answer here and stays distinguishable from a refusal.

    `citation_key ASC` is the secondary sort and it is load-bearing, not tidiness:
    PostgreSQL leaves tied rows unordered, and this corpus holds 45 articles whose
    entire body is the words "Sin Reglamentar" (`MANIFEST.md:658-660`). They tie
    on `ts_rank_cd`, so at the `LIMIT` boundary an arbitrary order decides which
    of them enters fusion at all.
    """
    filas = db.execute(
        FTS_SEARCH_SQL,
        {"consulta": consulta, "corpus_sha": corpus_sha, "limite": limite},
    ).all()
    return [
        LegHit(citation_key=fila[0], rango=i, valor=float(fila[1])) for i, fila in enumerate(filas)
    ]


VECTOR_SEARCH_SQL = text(
    """
    SELECT citation_key, embedding <=> CAST(:qvec AS vector) AS valor
    FROM rag_unidad
    WHERE corpus_sha = :corpus_sha AND embedding IS NOT NULL
    ORDER BY embedding <=> CAST(:qvec AS vector) ASC, citation_key ASC
    LIMIT :limite
    """
)

#: HNSW query-time search width, pinned per transaction on the vector leg.
#:
#: pgvector's default is 40. It is a CANDIDATE budget, not a filter: an HNSW
#: index scan returns at most `ef_search` rows, so `LIMIT 50` against
#: `ef_search = 40` silently yields 40 — a leg that is 20 % shallower than the
#: number the eval report prints, with no error and no warning anywhere.
#: Measured, not assumed (ledger RAG3-002): 1 400 seeded vectors, forced index
#: scan, `LIMIT 50` → `rows=40` at the default and `rows=50` at 100.
#:
#: Derived from `LEG_LIMIT` rather than hardcoded so raising the leg depth
#: cannot silently outgrow the budget. 2x is headroom, not superstition: HNSW is
#: approximate, and a budget merely EQUAL to the requested k is the worst place
#: on the recall curve to sit.
HNSW_EF_SEARCH = 2 * LEG_LIMIT

#: `SET LOCAL` takes no bind parameters; `set_config(..., is_local => true)` is
#: the same thing as a function call, so the value stays a bound parameter and
#: the pin dies with the transaction instead of leaking into a pooled session.
SET_EF_SEARCH_SQL = text("SELECT set_config('hnsw.ef_search', :ef, true)")


def vector_search(
    db: Session,
    corpus_sha: str,
    qvec: Sequence[float],
    limite: int = LEG_LIMIT,
    ef_search: int = HNSW_EF_SEARCH,
) -> list[LegHit]:
    """Vector leg — raw SQL with an explicit `::vector` cast (the column is unmapped).

    Raises `VectorSupportUnavailable` when the extension or the column is absent.
    It NEVER returns an empty list to mean "no vector support": an empty result
    is a legitimate answer (no unit has an embedding yet) and must stay
    distinguishable from "this database cannot answer".

    **`hnsw.ef_search` is pinned for the transaction, whatever plan runs.**
    At the pinned corpus's scale this query plans as a sequential scan plus a
    top-N heapsort — exact, 100 % recall, and the pin is a no-op. That is a
    property of TODAY's plan, not of the query: it holds because the `LIMIT`
    sits above a full scan, and the moment the planner picks the HNSW index
    instead, `ef_search` becomes the leg's real depth. Setting it here costs one
    round trip and removes the difference between "the leg returned 50" and "the
    leg returned whatever the index budget allowed" (ledger RAG3-002).
    """
    require_vector_support(db)
    if len(qvec) != EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"query vector has {len(qvec)} dimensions, the column is vector({EMBEDDING_DIMENSIONS})"
        )
    if ef_search < limite:
        raise ValueError(
            f"hnsw.ef_search={ef_search} is below the leg limit {limite}: an index "
            "scan would return at most ef_search rows and the leg would be "
            "silently truncated."
        )

    db.execute(SET_EF_SEARCH_SQL, {"ef": str(ef_search)})
    filas = db.execute(
        VECTOR_SEARCH_SQL,
        {"qvec": vector_literal(qvec), "corpus_sha": corpus_sha, "limite": limite},
    ).all()
    return [
        LegHit(citation_key=fila[0], rango=i, valor=float(fila[1])) for i, fila in enumerate(filas)
    ]


# ---------------------------------------------------------------------------
# Embedding provenance (migration conocimiento_004, design.md D3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProcedenciaEmbeddings:
    """What produced the vectors currently in this snapshot's `embedding` column.

    `modelo is None` means no artifact was ever loaded — the normal state of a
    freshly ingested corpus, and a state the vector leg must refuse to answer
    from rather than return an empty list that reads like "nothing matched".
    """

    corpus_sha: str
    modelo: str | None
    revision_hf: str | None
    sintetico: bool | None
    artifact_sha256: str | None
    loaded_at: datetime.datetime | None

    @property
    def cargado(self) -> bool:
        return self.modelo is not None


LEER_PROCEDENCIA_SQL = text(
    """
    SELECT corpus_sha, embedding_modelo, embedding_revision_hf, embedding_sintetico,
           embedding_artifact_sha256, embeddings_loaded_at
    FROM rag_corpus
    WHERE corpus_sha = :corpus_sha
    """
)

REGISTRAR_PROCEDENCIA_SQL = text(
    """
    UPDATE rag_corpus
    SET embedding_modelo = :modelo,
        embedding_revision_hf = :revision_hf,
        embedding_sintetico = :sintetico,
        embedding_artifact_sha256 = :artifact_sha256,
        embeddings_loaded_at = now()
    WHERE corpus_sha = :corpus_sha
    """
)


def leer_procedencia(db: Session, corpus_sha: str) -> ProcedenciaEmbeddings | None:
    """Provenance of this snapshot's vectors, or None if the snapshot is unknown.

    None (no snapshot row) and a row with `modelo IS NULL` (snapshot exists, was
    never embedded) are different facts and stay different: conflating them
    would let a typo in a corpus SHA read as "not embedded yet".
    """
    fila = db.execute(LEER_PROCEDENCIA_SQL, {"corpus_sha": corpus_sha}).first()
    if fila is None:
        return None
    return ProcedenciaEmbeddings(
        corpus_sha=fila[0],
        modelo=fila[1],
        revision_hf=fila[2],
        sintetico=fila[3],
        artifact_sha256=fila[4],
        loaded_at=fila[5],
    )


CLAVES_SIN_EMBEDDING_SQL = text(
    """
    SELECT citation_key
    FROM rag_unidad
    WHERE corpus_sha = :corpus_sha AND embedding IS NULL
    ORDER BY citation_key ASC
    """
)


def claves_sin_embedding(db: Session, corpus_sha: str) -> frozenset[str]:
    """Units of this snapshot the vector leg cannot reach: they have no vector.

    On a LOADED snapshot this set is exactly the artifact's declared
    `over_ceiling` exemptions — `rag_load_vectors.verificar_post_carga` rolls the
    whole load back, in both directions, unless the units without a vector are
    precisely the units the sidecar declared exempt. So this query reads a fact
    the loader already guaranteed rather than re-deriving one, which is why it
    can be a plain `IS NULL` and not a join against a manifest that, by design,
    does not survive a second batch (design.md D3).

    Requires the dev-only `embedding` column, so callers must have established
    vector capability first (`require_vector_support`). Ordered for determinism,
    like every other leg in this module.
    """
    return frozenset(
        fila[0] for fila in db.execute(CLAVES_SIN_EMBEDDING_SQL, {"corpus_sha": corpus_sha}).all()
    )


def registrar_procedencia(
    db: Session,
    corpus_sha: str,
    *,
    modelo: str,
    revision_hf: str | None,
    sintetico: bool,
    artifact_sha256: str,
) -> int:
    """Stamp the snapshot with what produced its vectors. Returns rows updated.

    Called by `scripts/rag_load_vectors.py` **inside the load transaction**, so
    the provenance and the vectors it describes commit together or not at all. A
    provenance row that outlived a rolled-back load would be worse than no row:
    it would claim a model for vectors that were never written.
    """
    resultado = db.execute(
        REGISTRAR_PROCEDENCIA_SQL,
        {
            "corpus_sha": corpus_sha,
            "modelo": modelo,
            "revision_hf": revision_hf,
            "sintetico": sintetico,
            "artifact_sha256": artifact_sha256,
        },
    )
    # `rowcount` lives on CursorResult (same accommodation as `prune_unidades`).
    return getattr(resultado, "rowcount", 0) or 0


HYDRATE_SQL = text(
    """
    SELECT u.citation_key, u.documento_id, u.tipo_chunk, u.epigrafe, u.texto,
           u.source_file, u.source_offset,
           d.tipo, d.es_secundaria, d.jurisdiccion, d.estado_vigencia,
           d.relevancia_consorcio, d.verificacion, d.fuente_url
    FROM rag_unidad u
    JOIN rag_documento d
      ON d.corpus_sha = u.corpus_sha AND d.documento_id = u.documento_id
    WHERE u.corpus_sha = :corpus_sha AND u.citation_key = ANY(:claves)
    """
)


def hydrate_citations(
    db: Session,
    corpus_sha: str,
    claves: Sequence[str],
) -> dict[str, dict[str, Any]]:
    """Full provenance for a set of citation keys, keyed by citation key.

    One query for the whole page rather than one per hit, and an INNER JOIN on
    `(corpus_sha, documento_id)` so a hit can only ever carry the metadata of a
    document from its OWN snapshot.
    """
    if not claves:
        return {}
    filas = db.execute(HYDRATE_SQL, {"corpus_sha": corpus_sha, "claves": list(claves)}).all()
    return {fila[0]: dict(fila._mapping) for fila in filas}
