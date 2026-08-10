"""Data access for the conocimiento (RAG) domain: the ingestion write path.

Two rules govern everything here.

**Snapshot isolation.** Every function takes `corpus_sha` as a required
positional argument. A forgotten snapshot filter is a `TypeError`, not silent
double results (design.md D1).

**Carried, never interpreted.** `jurisdiccion`, `relevancia_consorcio`,
`estado_vigencia` and `verificacion` are copied verbatim out of the document
frontmatter and surfaced as-is. V0 derives no boolean from
`relevancia_consorcio`: a regex over legal prose is exactly the silent
misclassification this design refuses.
"""

from __future__ import annotations

import datetime
import hashlib
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

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
