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
from app.domains.conocimiento.eval import barra_sin_gpu  # noqa: E402
from app.domains.conocimiento.gates import TOKEN_CEILING, GateFailure  # noqa: E402
from app.domains.conocimiento.rechunk import clave_identidad  # noqa: E402
from app.domains.conocimiento.schemas import (  # noqa: E402
    DocumentoIngestado,
    GateOutcome,
    IngestionSummary,
    UnidadSobreCeiling,
)
from app.domains.conocimiento.service import (  # noqa: E402
    gate_corpus,
    load_corpus,
    texto_sha256,
    verify_corpus_pin,
)

DEFAULT_REPO_URL = "https://github.com/JNZader/consorcio-corpus-legal"

# Printed on stderr by `--produccion-sin-orden`. It must never claim a cleared bar
# and never contain the state word of one.
BANNER_SIN_ORDEN = (
    "PRODUCTION INGEST UNDER A FAILED LAB BAR: the norms surface stays unranked "
    "(orden_presentado=false); this is not a cleared bar."
)


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
            "on a repeated corpus_sha, compare sha256 of texto AND "
            "texto_indexado per citation key and REPORT the divergence "
            "instead of overwriting it"
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
    parser.add_argument(
        "--entorno",
        choices=("laboratorio", "produccion"),
        default="laboratorio",
        help=(
            "laboratorio may ingest without the bar (measurement happens there). "
            "produccion refuses unless exactly one of --exigir-barra or "
            "--produccion-sin-orden is also set. The database URL does not decide this."
        ),
    )
    # Mutually exclusive: the ranked and the unranked path read the same artifact
    # and expect opposite outcomes, so naming both can only be a mistake.
    gate = parser.add_mutually_exclusive_group()
    gate.add_argument(
        "--exigir-barra",
        action="store_true",
        help=(
            "refuse to ingest unless eval/barra_sin_gpu.yaml shows the no-GPU arm's "
            "bar as `superada` for this exact --corpus-sha. Off by default; checked "
            "before the database, the corpus or the pin are touched, so it also "
            "applies to --dry-run."
        ),
    )
    gate.add_argument(
        "--produccion-sin-orden",
        action="store_true",
        help=(
            "only with --entorno produccion: ingest under an honest FAILED bar. "
            "Proceeds only if eval/barra_sin_gpu.yaml is `no_superada` for this exact "
            "--corpus-sha with at least one figure under its constant. This is NOT a "
            "cleared bar: the norms surface stays unranked. Checked before the "
            "database, the corpus or the pin are touched, so it also applies to "
            "--dry-run."
        ),
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
            over_ceiling=[
                UnidadSobreCeiling(citation_key=key, tokens=tokens)
                for key, tokens in report.over_ceiling
            ],
        ),
        documentos=[
            DocumentoIngestado(
                documento_id=doc.documento_id,
                archivo=doc.archivo,
                tipo=repository.normalize_tipo(str(doc.frontmatter["tipo"])),
                es_secundaria=repository.es_secundaria_for(str(doc.frontmatter["tipo"])),
                articulos=len(
                    {
                        clave_identidad(u.citation_key)
                        for u in doc.unidades
                        if u.tipo_chunk == "articulo"
                    }
                ),
                no_articulos=len(
                    {
                        clave_identidad(u.citation_key)
                        for u in doc.unidades
                        if u.tipo_chunk != "articulo"
                    }
                ),
            )
            for doc in corpus.documentos
        ],
    )

    # 3. `--verify-unchanged`: a re-emitted corpus that reused a SHA is the one
    #    case `ON CONFLICT DO UPDATE` would rewrite without leaving a trace.
    #    Report the difference instead of overwriting it.
    #
    #    The comparison is the FULL symmetric difference, not the intersection.
    #    An intersection-only check sees hash mismatches and nothing else, so a
    #    key the snapshot has and the parse does not produce raised no
    #    divergence — and the run then fell through to the upserts and
    #    `prune_unidades`, which DELETED exactly that key, reported
    #    "divergencias: []", committed and exited 0 (RAG2-003). The flag's
    #    contract is to report instead of overwriting; deleting is the strongest
    #    form of overwriting there is.
    #
    #    TWO surfaces are hashed, separately (RAG-4): `texto` is what a citation
    #    quotes; `texto_indexado` is what tsv/BM25/embeddings actually search.
    #    A parser or enrichment change under the same SHA rewrites the second
    #    with the first byte-identical, and a texto-only diff called that
    #    "unchanged", committed and exited 0 — the silent rewrite this flag
    #    exists to report, performed on the one surface retrieval reads.
    #    Separate hashes rather than one combined digest, because the report
    #    must say WHICH surface moved: `divergencias` = citation bytes changed,
    #    `divergencias_indexado` = enrichment changed with the citation bytes
    #    intact. A key is classified once — texto first — never into both.
    if verify_unchanged:
        previous = repository.existing_surface_hashes(session, corpus_sha)
        if previous:
            actuales = {
                unidad.citation_key: (
                    texto_sha256(unidad.texto),
                    texto_sha256(unidad.texto_indexado),
                )
                for doc in corpus.documentos
                for unidad in doc.unidades
            }
            summary.claves_agregadas = sorted(set(actuales) - set(previous))
            summary.claves_eliminadas = sorted(set(previous) - set(actuales))
            comunes = set(actuales) & set(previous)
            summary.divergencias = sorted(
                key for key in comunes if previous[key][0] != actuales[key][0]
            )
            summary.divergencias_indexado = sorted(
                key
                for key in comunes
                if previous[key][0] == actuales[key][0] and previous[key][1] != actuales[key][1]
            )
            if summary.verificacion_fallida:
                # Return BEFORE any write, including the prune.
                return summary

    if dry_run:
        return summary

    claves_nuevas = [unidad.citation_key for doc in corpus.documentos for unidad in doc.unidades]
    previas = repository.citation_keys(session, corpus_sha)
    procedencia = repository.leer_procedencia(session, corpus_sha)
    summary.procedencia_olvidada = repository.procedencia_queda_falsa(
        previas,
        claves_nuevas,
        cargado=procedencia is not None and procedencia.cargado,
    )

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
    for doc in corpus.documentos:
        row = repository.documento_row_from_frontmatter(
            corpus_sha, doc.documento_id, doc.frontmatter
        )
        repository.upsert_documento(session, corpus_sha, row)
        written += repository.upsert_unidades(
            session, corpus_sha, doc.documento_id, doc.archivo, doc.unidades
        )

    # Pruning is what makes "same SHA in, byte-identical state out" literal
    # rather than "a superset of it". The keep-list is the same set the
    # provenance check compared, so a split cannot prune a parent and still
    # claim the old vectors.
    summary.unidades_eliminadas = repository.prune_unidades(session, corpus_sha, claves_nuevas)
    if summary.procedencia_olvidada:
        repository.olvidar_procedencia(session, corpus_sha)
    summary.unidades_escritas = written
    summary.committed = True
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # A usage error, not a gate refusal: argparse owns invalid flag combinations,
    # so this exits 2 and never prints the ingest-abort banner.
    if args.produccion_sin_orden and args.entorno != "produccion":
        parser.error("--produccion-sin-orden solo es válido con --entorno produccion.")

    # Production is a choice, not a URL. A lab database can be pointed at with
    # the same flag shape; forgetting the bar on a production run must refuse
    # before any file or connection is touched.
    if args.entorno == "produccion" and not (args.exigir_barra or args.produccion_sin_orden):
        print(
            "\nINGESTION ABORTED — nothing was written.\n"
            "--entorno produccion exige --exigir-barra o --produccion-sin-orden. "
            "Laboratorio es el único entorno que puede ingerir sin la barra.\n",
            file=sys.stderr,
        )
        return 1

    # First, and before anything that can open a connection: the bar is a file
    # read, and a refusal here must cost nothing. The artifact is re-checked by
    # its figures (`exigir_superada`), not by its state word.
    if args.exigir_barra:
        try:
            barra_sin_gpu.exigir_superada(barra_sin_gpu.cargar_barra(), args.corpus_sha)
        except (barra_sin_gpu.BarraInvalida, barra_sin_gpu.BarraNoSuperada) as abort:
            print(
                "\nINGESTION ABORTED — nothing was written.\n"
                f"--exigir-barra: {abort}\n"
                "La barra del brazo bm25_sin_ce se deriva con scripts/rag_eval.py "
                "--modo bm25_sin_ce sobre una base de laboratorio; ver "
                "docs/rag/runbook-encendido.md.",
                file=sys.stderr,
            )
            return 1

    # The unranked path accepts a FAILED bar and nothing else. It never unlocks
    # rank order: `superada_para` still reads the same artifact and still says no.
    if args.produccion_sin_orden:
        try:
            barra = barra_sin_gpu.cargar_barra()
            barra_sin_gpu.exigir_no_superada_honesta(barra, args.corpus_sha)
        except (barra_sin_gpu.BarraInvalida, barra_sin_gpu.BarraSinOrdenRechazada) as abort:
            print(
                "\nINGESTION ABORTED — nothing was written.\n"
                f"--produccion-sin-orden: {abort}\n"
                "La barra del brazo bm25_sin_ce se deriva con scripts/rag_eval.py "
                "--modo bm25_sin_ce sobre una base de laboratorio; ver "
                "docs/rag/runbook-encendido.md.",
                file=sys.stderr,
            )
            return 1
        print(f"\n{BANNER_SIN_ORDEN}", file=sys.stderr)
        print(
            f"hit@5 {barra.hit_rate_at_5}, norma-vs-secundaria "
            f"{barra.separacion_norma_secundaria}, vigencia {barra.vigencia_correcta}, "
            f"corpus_sha {barra.corpus_sha}\n",
            file=sys.stderr,
        )

    if not args.database_url and not args.dry_run:
        print("error: --database-url or $DATABASE_URL is required", file=sys.stderr)
        return 2

    engine = create_engine(args.database_url) if args.database_url else None
    sha_servido: str | None = None
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
                if summary.verificacion_fallida:
                    # Roll back rather than overwrite a divergent snapshot.
                    session.rollback()
                elif summary.committed:
                    # Read in the SAME transaction that wrote the row, so the
                    # printed sha is what serving answers from the instant this
                    # commit lands — not what a later query would resolve. This
                    # is what makes a no-op rollback visible: before rotation
                    # (audit RAG-3), re-ingesting an older sha exited 0 with
                    # committed:true while serving kept answering from the
                    # newer snapshot; here the two lines disagree out loud.
                    sha_servido = repository.corpus_activo(session)
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
    if summary.committed:
        # The sha the serving path (ORDER BY ingested_at DESC over activo rows)
        # resolves to after this commit. Diverging from corpus_sha above means
        # serving is NOT answering from what this run just wrote.
        print(f"served sha           : {sha_servido}")
    if args.produccion_sin_orden:
        print("barra                : failed lab bar, served unranked")
    if summary.procedencia_olvidada:
        print(
            "embeddings           : CLEARED — citation keys changed under a loaded "
            "index. Re-run rag_embed_batch.py and rag_load_vectors.py before "
            "vector or hybrid. bm25_ce does not read those columns."
        )

    _print_over_ceiling(summary)

    if summary.verificacion_fallida:
        print(
            "\nVERIFICACIÓN FALLIDA (--verify-unchanged): the stored snapshot and "
            "this parse differ under an unchanged corpus_sha. Nothing was written.",
            file=sys.stderr,
        )
        _print_keys("contenido modificado", summary.divergencias)
        _print_keys(
            "superficie de búsqueda modificada (texto_indexado; el texto citado quedó igual)",
            summary.divergencias_indexado,
        )
        _print_keys("claves agregadas (en el parse, no en el snapshot)", summary.claves_agregadas)
        _print_keys(
            "claves eliminadas (en el snapshot, no en el parse — un run normal las PODARÍA)",
            summary.claves_eliminadas,
        )
        return 1
    return 0


def _print_keys(label: str, keys: list[str], limit: int = 20) -> None:
    if not keys:
        return
    print(f"\n  {label}: {len(keys)}", file=sys.stderr)
    for key in keys[:limit]:
        print(f"    - {key}", file=sys.stderr)
    if len(keys) > limit:
        print(f"    … +{len(keys) - limit} more", file=sys.stderr)


def _print_over_ceiling(summary: IngestionSummary) -> None:
    """Surface units over the embedding ceiling. Never silent, never truncated.

    An empty list prints nothing. After F1 the pinned corpus has no such unit:
    the old three (`10593#1`, `8560#5`, and the char-estimate false positive)
    are parts under 8192. A unit that is still over the ceiling still prints.
    """
    if not summary.gates.over_ceiling:
        return
    print(
        f"\nSOBRE EL CEILING DE EMBEDDING ({TOKEN_CEILING} tokens): "
        f"{len(summary.gates.over_ceiling)} unidad(es)."
    )
    print(
        "  Se ingestan ENTERAS y siguen siendo recuperables por FTS. En V0 quedan "
        "FUERA del embedding (slice 3) — nunca truncadas. Use "
        "--strict-token-ceiling para abortar en su lugar."
    )
    for unidad in summary.gates.over_ceiling:
        print(f"    - {unidad.citation_key} (~{unidad.tokens} tokens)")


if __name__ == "__main__":
    raise SystemExit(main())
