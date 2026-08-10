#!/usr/bin/env python3
"""Load a `vectors-{sha8}.copy` artifact into `rag_unidad.embedding` (design.md D3).

    python scripts/rag_load_vectors.py \\
        --vectors artifacts/rag/vectors-12043582.copy \\
        --database-url postgresql://consorcio:consorcio_dev@localhost:5432/consorcio

**COPY goes into a staging table, never into `rag_unidad`.** Ingestion already
created every row, the PK is `(corpus_sha, citation_key)`, and `COPY` has no
`ON CONFLICT`: a direct `COPY rag_unidad (...)` would attempt ~1,400 inserts and
fail on the primary key for every one of them. So the dump lands in a
`ON COMMIT DROP` temp table and an `UPDATE … FROM` joins it back.

Everything is one transaction and every check is a refusal, not a warning:
nothing commits unless every key in the dump resolved to a unit AND every unit
that ends up without a vector is one the artifact declared exempt.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.domains.conocimiento.embedding import (  # noqa: E402
    VectorsManifest,
    escape_copy_field,
    manifest_path_for,
    sha256_file,
)
from app.domains.conocimiento.repository import (  # noqa: E402
    VectorSupportUnavailable,
    require_vector_support,
)

STAGING_TABLE = "rag_embedding_staging"


class ArtifactMismatch(RuntimeError):
    """The dump on disk is not the dump the sidecar describes."""


class PreflightFailure(RuntimeError):
    """A pre- or post-check refused the load. Nothing was written."""


def leer_claves(copy_path: Path) -> set[str]:
    """Citation keys present in the dump, un-escaped.

    Read separately from the `COPY` itself so the exemption identity check can
    run BEFORE the transaction opens — a load that would be rejected must never
    have touched the database.
    """
    claves: set[str] = set()
    with copy_path.open("r", encoding="utf-8") as handle:
        for numero, linea in enumerate(handle, start=1):
            if not linea.strip():
                continue
            partes = linea.rstrip("\n").split("\t")
            if len(partes) != 3:
                raise ArtifactMismatch(
                    f"{copy_path.name}:{numero}: expected 3 tab-separated columns, "
                    f"got {len(partes)}"
                )
            clave = partes[1].replace("\\t", "\t").replace("\\n", "\n").replace("\\\\", "\\")
            if clave in claves:
                raise ArtifactMismatch(f"{copy_path.name}:{numero}: duplicate key {clave!r}")
            claves.add(clave)
    return claves


def verificar_dump(copy_path: Path, manifest: VectorsManifest) -> None:
    real = sha256_file(copy_path)
    if real != manifest.sha256:
        raise ArtifactMismatch(
            f"{copy_path.name}: sha256 is {real}, sidecar declares {manifest.sha256}. "
            "The dump and its manifest disagree, so nothing about the dump can be "
            "trusted — not the model it came from, not the dimensions, not the "
            "exemption list."
        )


def preflight(
    session: Session,
    manifest: VectorsManifest,
    claves_dump: set[str],
    *,
    permitir_sintetico: bool = False,
) -> None:
    """Refuse the load unless the artifact matches this snapshot EXACTLY.

    The exemption identity check is the one that matters (design.md D3, ledger
    R3-104). The ratified V0 behaviour leaves over-ceiling units un-embedded, so
    a correct dump is always short by exactly those units — but a check that only
    verified the COUNT would accept **any** equally-sized shortfall. A batch that
    lost its last shard to an OOM would then load clean, and three unrelated
    articles would be silently unreachable through the vector leg while every
    number in the eval report looked right.

    So identity, in both directions:

    * every declared exempt key IS a unit of this snapshot;
    * no declared exempt key appears in the dump;
    * `dump ∪ exempt` is exactly the snapshot's unit set.

    The third subsumes the count, and it is what turns "three are missing" into
    "these three are missing, and they are the three we said".
    """
    if manifest.sintetico and not permitir_sintetico:
        raise PreflightFailure(
            f"{manifest.modelo} produced SINTÉTICO vectors: they are hash noise, not "
            "embeddings. An eval report built on them would be indistinguishable "
            "from a real one. Pass --allow-synthetic if you are deliberately "
            "smoke-testing the pipeline."
        )

    if manifest.dims != _dims_esperadas():
        raise PreflightFailure(
            f"manifest declares dims={manifest.dims}; the column is vector({_dims_esperadas()})."
        )

    fila = session.execute(
        text("SELECT activo FROM rag_corpus WHERE corpus_sha = :sha"),
        {"sha": manifest.corpus_sha},
    ).first()
    if fila is None:
        raise PreflightFailure(
            f"snapshot {manifest.corpus_sha} is not in rag_corpus. Ingest it before "
            "loading vectors for it."
        )
    if not fila[0]:
        raise PreflightFailure(
            f"snapshot {manifest.corpus_sha} exists but is not activo. Loading "
            "vectors into a retired snapshot would embed a corpus nothing queries."
        )

    if len(claves_dump) != manifest.n_vectors:
        raise PreflightFailure(
            f"the dump holds {len(claves_dump)} keys but the sidecar declares "
            f"n_vectors={manifest.n_vectors}."
        )

    todas = {
        row[0]
        for row in session.execute(
            text("SELECT citation_key FROM rag_unidad WHERE corpus_sha = :sha"),
            {"sha": manifest.corpus_sha},
        ).all()
    }
    exentas = set(manifest.over_ceiling)

    inventadas = sorted(exentas - todas)
    if inventadas:
        raise PreflightFailure(
            f"the artifact declares {len(inventadas)} exempt key(s) that are not "
            f"units of this snapshot: {inventadas[:5]}. An exemption naming a "
            "non-existent unit is a claim about a different corpus."
        )

    embebidas_pese_a_exentas = sorted(exentas & claves_dump)
    if embebidas_pese_a_exentas:
        raise PreflightFailure(
            f"{embebidas_pese_a_exentas[:5]} are declared over-ceiling AND present "
            "in the dump. The ceiling was applied to a different set than the one "
            "disclosed."
        )

    huerfanas = sorted(claves_dump - todas)
    if huerfanas:
        raise PreflightFailure(
            f"the dump holds {len(huerfanas)} key(s) that are not units of snapshot "
            f"{manifest.corpus_sha}: {huerfanas[:5]}. Aborting before the "
            "transaction opens."
        )

    sin_cubrir = sorted(todas - claves_dump - exentas)
    if sin_cubrir:
        raise PreflightFailure(
            f"{len(sin_cubrir)} unit(s) have neither a vector in the dump nor an "
            f"exemption in the manifest: {sin_cubrir[:5]}. A count-only check "
            "would have accepted this — which is precisely why it is not the "
            "check (design.md D3)."
        )


def _dims_esperadas() -> int:
    from app.domains.conocimiento.ddl import EMBEDDING_DIMENSIONS

    return EMBEDDING_DIMENSIONS


def load_vectors(
    session: Session,
    copy_path: Path,
    *,
    permitir_sintetico: bool = False,
) -> int:
    """Load one artifact. Returns the number of rows updated, or raises.

    The caller owns the transaction (the CLI opens one; the tests use the
    rollback-per-test `db` fixture), which is what makes "all-or-nothing" true:
    every failure below leaves the session dirty but uncommitted, so nothing
    reaches the database.
    """
    manifest = VectorsManifest.load(manifest_path_for(copy_path))
    verificar_dump(copy_path, manifest)
    claves_dump = leer_claves(copy_path)

    require_vector_support(session)
    preflight(session, manifest, claves_dump, permitir_sintetico=permitir_sintetico)

    session.execute(
        text(
            f"CREATE TEMP TABLE {STAGING_TABLE} ("
            "corpus_sha CHAR(40), citation_key TEXT, "
            f"embedding vector({manifest.dims})) ON COMMIT DROP"
        )
    )

    raw = session.connection().connection
    cursor = raw.cursor()
    try:
        with copy_path.open("r", encoding="utf-8") as handle:
            cursor.copy_expert(
                f"COPY {STAGING_TABLE} (corpus_sha, citation_key, embedding) FROM STDIN",
                handle,
            )
    finally:
        cursor.close()

    # `rowcount` lives on CursorResult, which is what an UPDATE returns; the base
    # Result protocol mypy infers does not declare it (same accommodation as
    # `repository.prune_unidades`).
    resultado = session.execute(
        text(
            "UPDATE rag_unidad u SET embedding = s.embedding "
            f"FROM {STAGING_TABLE} s "
            "WHERE u.corpus_sha = s.corpus_sha AND u.citation_key = s.citation_key"
        )
    )
    actualizadas = getattr(resultado, "rowcount", 0) or 0

    if actualizadas != manifest.n_vectors:
        raise PreflightFailure(
            f"the UPDATE touched {actualizadas} rows, the sidecar declares "
            f"n_vectors={manifest.n_vectors}. Rolling back."
        )

    huerfanas = [
        row[0]
        for row in session.execute(
            text(
                f"SELECT s.citation_key FROM {STAGING_TABLE} s WHERE NOT EXISTS ("
                "SELECT 1 FROM rag_unidad u WHERE u.corpus_sha = s.corpus_sha "
                "AND u.citation_key = s.citation_key) ORDER BY s.citation_key"
            )
        ).all()
    ]
    if huerfanas:
        raise PreflightFailure(
            f"{len(huerfanas)} staging key(s) resolved to no unit: {huerfanas[:5]}. Rolling back."
        )

    sin_vector = {
        row[0]
        for row in session.execute(
            text(
                "SELECT citation_key FROM rag_unidad WHERE corpus_sha = :sha AND embedding IS NULL"
            ),
            {"sha": manifest.corpus_sha},
        ).all()
    }
    if sin_vector != set(manifest.over_ceiling):
        inesperadas = sorted(sin_vector - set(manifest.over_ceiling))
        raise PreflightFailure(
            "after the load, the units without a vector are not the units the "
            f"artifact declared exempt. Unexpectedly empty: {inesperadas[:5]}. "
            "Rolling back."
        )

    return actualizadas


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vectors", required=True, type=Path, help="path to vectors-*.copy")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="defaults to $DATABASE_URL",
    )
    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        help=(
            "accept an artifact produced by the deterministic fake embedder. "
            "For pipeline smoke tests ONLY — the vectors are hash noise."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.database_url:
        print("error: --database-url or $DATABASE_URL is required", file=sys.stderr)
        return 2

    engine = create_engine(args.database_url)
    try:
        with Session(engine) as session, session.begin():
            actualizadas = load_vectors(
                session, args.vectors, permitir_sintetico=args.allow_synthetic
            )
            manifest = VectorsManifest.load(manifest_path_for(args.vectors))
    except (ArtifactMismatch, PreflightFailure, VectorSupportUnavailable) as abort:
        print(f"\nLOAD ABORTED — nothing was written.\n{abort}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    print(f"corpus_sha           : {manifest.corpus_sha}")
    print(f"modelo               : {manifest.modelo} (rev {manifest.revision_hf})")
    print(f"dims                 : {manifest.dims}")
    print(f"vectores cargados    : {actualizadas}")
    print(f"unidades exentas     : {len(manifest.over_ceiling)}")
    for clave in manifest.over_ceiling:
        print(f"    - {clave} (sobre el ceiling de {manifest.token_ceiling} tokens)")
    if manifest.sintetico:
        print(
            "\nADVERTENCIA: estos vectores son SINTÉTICOS (embedder determinista de "
            "prueba). Sirven para validar el pipeline, NUNCA para medir "
            "recuperación.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# `escape_copy_field` is re-exported so an operator inspecting a dump can reuse
# exactly the escaping that produced it.
__all__ = [
    "ArtifactMismatch",
    "PreflightFailure",
    "escape_copy_field",
    "leer_claves",
    "load_vectors",
    "main",
    "preflight",
]
