#!/usr/bin/env python3
"""Ingest a SHA-pinned corpus checkout into `rag_corpus`/`rag_documento`/`rag_unidad`.

Thin entry point (house precedent: `scripts/mutation_test.py`) — every rule
lives in `app/domains/conocimiento/`.

    python scripts/rag_ingest.py \\
        --corpus-path /path/to/consorcio-corpus-legal \\
        --corpus-sha 12043582bf8016288a7e8084e85a4b713a97af2f

The corpus location is a required argument, never a baked path: nothing under
`~/Escritorio/...` may appear in this repository (design.md D2).

Ordering is the safety property. The pin is verified, the corpus is parsed and
every gate runs BEFORE the transaction opens, so a drifted or unpinned corpus
cannot write a single row.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.domains.conocimiento import repository  # noqa: E402
from app.domains.conocimiento.gates import GateFailure  # noqa: E402
from app.domains.conocimiento.schemas import (  # noqa: E402
    DocumentoIngestado,
    GateOutcome,
    IngestionSummary,
)
from app.domains.conocimiento.service import (  # noqa: E402
    gate_corpus,
    load_corpus,
    texto_sha256,
    verify_corpus_pin,
)

DEFAULT_REPO_URL = "https://github.com/JNZader/consorcio-corpus-legal"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-path", required=True, type=Path)
    parser.add_argument("--corpus-sha", required=True)
    parser.add_argument("--repo-url", default=DEFAULT_REPO_URL)
    parser.add_argument("--manifest-version", default="2")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="defaults to $DATABASE_URL",
    )
    parser.add_argument(
        "--verify-unchanged",
        action="store_true",
        help=(
            "on a repeated corpus_sha, compare sha256(texto) per citation key "
            "and REPORT the divergence instead of overwriting it"
        ),
    )
    parser.add_argument(
        "--strict-token-ceiling",
        action="store_true",
        help="treat over-8192-token units as a hard gate failure",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="parse and gate, then stop without writing",
    )
    return parser


def ingest(
    session: Session,
    corpus_path: Path,
    corpus_sha: str,
    *,
    repo_url: str = DEFAULT_REPO_URL,
    manifest_version: str = "2",
    verify_unchanged: bool = False,
    strict_token_ceiling: bool = False,
    dry_run: bool = False,
) -> IngestionSummary:
    """Run one ingestion. Raises before writing anything if a precondition fails."""
    # 1. The pin, first. An unresolvable SHA or a dirty tree stops here, with
    #    the transaction never opened.
    verify_corpus_pin(corpus_path, corpus_sha)

    # 2. Parse, then gate. Still no writes.
    corpus = load_corpus(corpus_path)
    if corpus.corpus_sha != corpus_sha:
        raise repository.IngestionAbort(
            f"corpus_expectations.yaml pins {corpus.corpus_sha}, not {corpus_sha}"
        )
    report = gate_corpus(corpus, strict_token_ceiling=strict_token_ceiling)
    report.raise_if_failed()

    summary = IngestionSummary(
        corpus_sha=corpus_sha,
        repo_url=repo_url,
        manifest_version=manifest_version,
        articulos_declarados=report.articulos_total,
        unidades_escritas=0,
        gates=GateOutcome(
            ok=report.ok,
            articulos_total=report.articulos_total,
            no_articulos_total=report.no_articulos_total,
            documentos=report.documentos,
            failures=list(report.failures),
        ),
        documentos=[
            DocumentoIngestado(
                documento_id=doc.documento_id,
                archivo=doc.archivo,
                tipo=repository.normalize_tipo(str(doc.frontmatter["tipo"])),
                es_secundaria=repository.es_secundaria_for(str(doc.frontmatter["tipo"])),
                articulos=sum(1 for u in doc.unidades if u.tipo_chunk == "articulo"),
                no_articulos=sum(1 for u in doc.unidades if u.tipo_chunk != "articulo"),
            )
            for doc in corpus.documentos
        ],
    )

    # 3. `--verify-unchanged`: a re-emitted corpus that reused a SHA is the one
    #    case `ON CONFLICT DO UPDATE` would rewrite without leaving a trace.
    #    Report the divergence instead of overwriting it.
    if verify_unchanged:
        previous = repository.existing_text_hashes(session, corpus_sha)
        if previous:
            divergentes = [
                unidad.citation_key
                for doc in corpus.documentos
                for unidad in doc.unidades
                if unidad.citation_key in previous
                and previous[unidad.citation_key] != texto_sha256(unidad.texto)
            ]
            if divergentes:
                summary.divergencias = sorted(divergentes)
                return summary

    if dry_run:
        return summary

    # 4. One transaction. Nothing commits unless every write succeeds.
    repository.upsert_corpus(
        session,
        corpus_sha,
        repo_url=repo_url,
        manifest_version=manifest_version,
        articulos_declarados=report.articulos_total,
        activo=True,
    )

    written = 0
    keys: list[str] = []
    for doc in corpus.documentos:
        row = repository.documento_row_from_frontmatter(
            corpus_sha, doc.documento_id, doc.frontmatter
        )
        repository.upsert_documento(session, corpus_sha, row)
        written += repository.upsert_unidades(
            session, corpus_sha, doc.documento_id, doc.archivo, doc.unidades
        )
        keys.extend(unidad.citation_key for unidad in doc.unidades)

    # Pruning is what makes "same SHA in, byte-identical state out" literal
    # rather than "a superset of it".
    summary.unidades_eliminadas = repository.prune_unidades(session, corpus_sha, keys)
    summary.unidades_escritas = written
    summary.committed = True
    return summary


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.database_url and not args.dry_run:
        print("error: --database-url or $DATABASE_URL is required", file=sys.stderr)
        return 2

    engine = create_engine(args.database_url) if args.database_url else None
    try:
        if engine is None:  # noqa: SIM108 — the two branches differ in more than the value
            summary = ingest(
                None,  # type: ignore[arg-type]
                args.corpus_path,
                args.corpus_sha,
                repo_url=args.repo_url,
                manifest_version=args.manifest_version,
                strict_token_ceiling=args.strict_token_ceiling,
                dry_run=True,
            )
        else:
            with Session(engine) as session, session.begin():
                summary = ingest(
                    session,
                    args.corpus_path,
                    args.corpus_sha,
                    repo_url=args.repo_url,
                    manifest_version=args.manifest_version,
                    verify_unchanged=args.verify_unchanged,
                    strict_token_ceiling=args.strict_token_ceiling,
                    dry_run=args.dry_run,
                )
                if summary.divergencias:
                    # Roll back rather than overwrite a divergent snapshot.
                    session.rollback()
    except (repository.IngestionAbort, GateFailure) as abort:
        # Every one of these is a deliberate refusal to write, not a crash.
        # Report it as such instead of a traceback.
        print(f"\nINGESTION ABORTED — nothing was written.\n{abort}", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()

    print(f"corpus_sha           : {summary.corpus_sha}")
    print(f"documentos           : {summary.gates.documentos}")
    print(f"articulo units       : {summary.gates.articulos_total}")
    print(f"non-article units    : {summary.gates.no_articulos_total}")
    print(f"unidades escritas    : {summary.unidades_escritas}")
    print(f"unidades eliminadas  : {summary.unidades_eliminadas}")
    print(f"committed            : {summary.committed}")

    if summary.divergencias:
        print(
            f"\nDIVERGENCIA: {len(summary.divergencias)} unit(s) changed content "
            f"under an unchanged corpus_sha. Nothing was written.",
            file=sys.stderr,
        )
        for key in summary.divergencias[:20]:
            print(f"  - {key}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
