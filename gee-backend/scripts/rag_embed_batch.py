#!/usr/bin/env python3
"""Embed an ingested snapshot into `vectors-{sha8}.copy` + sidecar (design.md D3).

This is the ONE step that needs a GPU, and it runs once per corpus revision on
the owner's workstation (Ops O.3). Nothing else in the pipeline imports torch.

    # once, in a SEPARATE virtualenv — requirements-rag.txt pulls the CUDA stack
    python -m venv venv-rag && venv-rag/bin/pip install -r requirements-rag.txt

    # the run (RTX 5060 Ti)
    venv-rag/bin/python scripts/rag_embed_batch.py \\
        --corpus-sha 12043582bf8016288a7e8084e85a4b713a97af2f \\
        --database-url postgresql://consorcio:consorcio_dev@localhost:5432/consorcio \\
        --output-dir artifacts/rag \\
        --device cuda --batch-size 8

Rehearse it first with `--preflight-only`: that loads the model and the real
tokenizer, reports the over-ceiling units, and writes nothing.

**No query/document prefix.** BGE-M3 is symmetric, unlike BGE-v1.5 and E5 which
require one; adding a prefix here degrades retrieval silently, and the symptom
looks like "the vector leg is mediocre" rather than like a bug.

**Nothing is ever truncated.** The MANIFEST forbids splitting long articles, so a
unit over the 8192-token ceiling is excluded from the embedding leg, recorded by
citation key in the sidecar, and printed on every run. It stays whole in the
database and fully retrievable through FTS. `--strict-token-ceiling` turns that
into a hard abort for operators who want the batch to stop instead.
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.domains.conocimiento.embedding import (  # noqa: E402
    DEFAULT_MODEL_ID,
    EMBEDDING_DIMENSIONS,
    TOKEN_CEILING,
    Embedder,
    VectorsManifest,
    batched,
    copy_line,
    get_embedder,
    manifest_path_for,
    runtime_versions,
    sha256_file,
)


class CeilingExceeded(RuntimeError):
    """A unit is over the model's context ceiling and `--strict-token-ceiling` is on."""


class NothingToEmbed(RuntimeError):
    """The snapshot is unknown or holds no units."""


def leer_unidades(session: Session, corpus_sha: str) -> list[tuple[str, str]]:
    """`(citation_key, texto_indexado)` for the snapshot, ordered by citation key.

    Ordering is what makes the dump reproducible: two runs over the same snapshot
    must produce byte-identical files, or "pinned corpus SHA" stops implying
    "pinned artifact".

    `texto_indexado` — title + structural path + verbatim text — is what the
    embedder sees, never `texto`. Enrichment belongs in the index and never in a
    citation (design.md, Technical Approach).
    """
    existe = session.execute(
        text("SELECT 1 FROM rag_corpus WHERE corpus_sha = :sha"), {"sha": corpus_sha}
    ).first()
    if existe is None:
        raise NothingToEmbed(
            f"snapshot {corpus_sha} is not in rag_corpus. Run scripts/rag_ingest.py first."
        )

    filas = session.execute(
        text(
            "SELECT citation_key, texto_indexado FROM rag_unidad "
            "WHERE corpus_sha = :sha ORDER BY citation_key ASC"
        ),
        {"sha": corpus_sha},
    ).all()
    if not filas:
        raise NothingToEmbed(f"snapshot {corpus_sha} holds no units")
    return [(fila[0], fila[1]) for fila in filas]


def preflight(
    unidades: Sequence[tuple[str, str]],
    embedder: Embedder,
    *,
    strict: bool = False,
    ceiling: int = TOKEN_CEILING,
) -> tuple[list[tuple[str, str]], list[tuple[str, int]]]:
    """Split the snapshot into what gets embedded and what is exempt.

    Counted with the embedder's OWN tokenizer and with truncation disabled — the
    ceiling has to be measured before the model would silently enforce it.
    Returns `(a_embeber, exentas)` where `exentas` carries the real token count,
    so the operator sees how far over the ceiling each unit actually is.
    """
    a_embeber: list[tuple[str, str]] = []
    exentas: list[tuple[str, int]] = []

    for citation_key, texto in unidades:
        tokens = embedder.count_tokens(texto)
        if tokens > ceiling:
            exentas.append((citation_key, tokens))
            if strict:
                raise CeilingExceeded(
                    f"{citation_key} is {tokens} tokens, over the {ceiling} ceiling. "
                    "Aborting rather than embedding a truncated fragment of a law "
                    "under the law's own citation key."
                )
        else:
            a_embeber.append((citation_key, texto))

    return a_embeber, exentas


def embed_snapshot(
    session: Session,
    corpus_sha: str,
    embedder: Embedder,
    *,
    output_dir: Path,
    batch_size: int = 8,
    strict_token_ceiling: bool = False,
    device: str = "cpu",
) -> tuple[Path, VectorsManifest]:
    """Embed one snapshot and write `vectors-{sha8}.copy` + `.json`.

    Returns `(copy_path, manifest)`. The manifest is written to disk before this
    returns, so a crash after the dump cannot leave an unlabelled file that a
    later operator has no way to interpret.
    """
    unidades = leer_unidades(session, corpus_sha)
    # The ceiling comes from the EMBEDDER, not from the module constant: BGE-M3
    # takes 8192 tokens and multilingual-e5-large takes 512, so a fixed 8192
    # would exempt nothing under e5 and let the model truncate long articles
    # silently — the one thing the MANIFEST forbids.
    ceiling = embedder.token_ceiling
    a_embeber, exentas = preflight(unidades, embedder, strict=strict_token_ceiling, ceiling=ceiling)

    output_dir.mkdir(parents=True, exist_ok=True)
    copy_path = output_dir / f"vectors-{corpus_sha[:8]}.copy"

    escritos = 0
    with copy_path.open("w", encoding="utf-8") as handle:
        for lote in batched([texto for _, texto in a_embeber], batch_size):
            vectores = embedder.encode(lote)
            if len(vectores) != len(lote):
                raise RuntimeError(
                    f"embedder returned {len(vectores)} vectors for {len(lote)} texts"
                )
            for vector in vectores:
                citation_key = a_embeber[escritos][0]
                handle.write(copy_line(corpus_sha, citation_key, vector, dims=embedder.dims))
                escritos += 1

    versiones = runtime_versions()
    manifest = VectorsManifest(
        corpus_sha=corpus_sha,
        modelo=embedder.model_id,
        revision_hf=embedder.revision,
        dims=embedder.dims,
        normalized=True,
        sintetico=bool(getattr(embedder, "sintetico", False)),
        n_vectors=escritos,
        sha256=sha256_file(copy_path),
        over_ceiling=tuple(exentas),
        token_ceiling=ceiling,
        torch=versiones["torch"],
        transformers=versiones["transformers"],
        device=device,
        generado_en=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )
    manifest.write(manifest_path_for(copy_path))
    return copy_path, manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-sha", required=True)
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="defaults to $DATABASE_URL",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/rag"))
    parser.add_argument("--model", default=DEFAULT_MODEL_ID)
    parser.add_argument("--device", default="cuda", help="cuda | cuda:0 | cpu")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument(
        "--embedder",
        default="bge-m3",
        choices=("bge-m3", "e5-large", "deterministic"),
        help=(
            "'e5-large' is ASYMMETRIC and is built here with the `passage` "
            "prefix, because this script embeds the corpus. "
            "'deterministic' is a hash-derived FAKE for pipeline smoke tests; "
            "its artifacts are stamped sintetico=true and the loader refuses "
            "them without --allow-synthetic"
        ),
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="tokenize and report the ceiling, then stop. Writes no artifact.",
    )
    parser.add_argument(
        "--strict-token-ceiling",
        action="store_true",
        help="abort instead of exempting units over the ceiling",
    )
    return parser


def _print_exentas(exentas: Sequence[tuple[str, int]], ceiling: int = TOKEN_CEILING) -> None:
    if not exentas:
        print(f"sobre el ceiling      : 0 unidades (ceiling {ceiling} tokens)")
        return
    print(f"\nSOBRE EL CEILING DE EMBEDDING ({ceiling} tokens): {len(exentas)} unidad(es).")
    print(
        "  Quedan ENTERAS en la base y siguen siendo recuperables por FTS. NO se "
        "embeben y NUNCA se truncan. Sus claves quedan fijadas en el sidecar, y el "
        "loader verifica que las unidades sin vector sean EXACTAMENTE estas."
    )
    for citation_key, tokens in exentas:
        print(f"    - {citation_key} ({tokens} tokens)")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.database_url:
        print("error: --database-url or $DATABASE_URL is required", file=sys.stderr)
        return 2

    try:
        # `passage`: this script embeds the CORPUS. On an asymmetric model the
        # other role would produce a valid-looking index that ranks worse and
        # raises nothing (see `E5Embedder`).
        embedder = get_embedder(
            args.embedder, rol="passage", device=args.device, model_id=args.model
        )
    # Both classes, for the reason in `rag_eval.py` (ledger RJDA-104): the
    # embedders wrap the missing-dependency `ImportError` in a `RuntimeError`
    # today, and this branch must not depend on that staying true.
    except (RuntimeError, ImportError) as missing:  # pragma: no cover — environment-dependent
        print(f"\n{missing}", file=sys.stderr)
        return 2

    if embedder.dims != EMBEDDING_DIMENSIONS:
        print(
            f"error: {embedder.model_id} produces {embedder.dims} dimensions; the "
            f"column is vector({EMBEDDING_DIMENSIONS}). Changing the model means "
            "changing migration 002 and re-embedding everything.",
            file=sys.stderr,
        )
        return 2

    engine = create_engine(args.database_url)
    try:
        with Session(engine) as session:
            if args.preflight_only:
                unidades = leer_unidades(session, args.corpus_sha)
                a_embeber, exentas = preflight(
                    unidades,
                    embedder,
                    strict=args.strict_token_ceiling,
                    ceiling=embedder.token_ceiling,
                )
                print(f"corpus_sha            : {args.corpus_sha}")
                print(f"unidades              : {len(unidades)}")
                print(f"a embeber             : {len(a_embeber)}")
                _print_exentas(exentas, ceiling=embedder.token_ceiling)
                print("\n--preflight-only: no se escribió ningún artefacto.")
                return 0

            copy_path, manifest = embed_snapshot(
                session,
                args.corpus_sha,
                embedder,
                output_dir=args.output_dir,
                batch_size=args.batch_size,
                strict_token_ceiling=args.strict_token_ceiling,
                device=args.device,
            )
    except (NothingToEmbed, CeilingExceeded) as abort:
        print(f"\nBATCH ABORTED — nothing was written.\n{abort}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    print(f"corpus_sha            : {manifest.corpus_sha}")
    print(f"modelo                : {manifest.modelo} (rev {manifest.revision_hf})")
    print(f"dims                  : {manifest.dims} (normalizados)")
    print(f"device                : {manifest.device}")
    print(f"vectores              : {manifest.n_vectors}")
    print(f"dump                  : {copy_path}")
    print(f"sidecar               : {manifest_path_for(copy_path)}")
    print(f"sha256                : {manifest.sha256}")
    # The MEASURED counts, straight from the sidecar. This line used to print
    # `TOKEN_CEILING + 1` for every exempt unit — a fabricated 8193 in the same
    # format as the real counts `--preflight-only` prints, so the two were
    # indistinguishable on screen while only one of them was a measurement
    # (ledger RJDA-007). "How far over" decides whether a unit gets re-chunked
    # upstream or accepted as FTS-only, so a placeholder there is worse than no
    # number at all.
    _print_exentas(manifest.over_ceiling, ceiling=manifest.token_ceiling)

    if manifest.sintetico:
        print(
            "\nADVERTENCIA: --embedder deterministic produce RUIDO, no embeddings. "
            "Sirve para validar el pipeline y nada más.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
