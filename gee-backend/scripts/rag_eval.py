#!/usr/bin/env python3
"""Run the three-mode ablation over the gold set and write the eval report.

Thin entry point (house precedent: `scripts/rag_ingest.py`) — every rule lives in
`app/domains/conocimiento/eval/`.

    python scripts/rag_eval.py \\
        --corpus-sha 12043582bf8016288a7e8084e85a4b713a97af2f \\
        --database-url postgresql://consorcio:consorcio_dev@localhost:5432/consorcio

Needs, in this order and for reasons that are refusals rather than warnings:

* an INGESTED snapshot (`scripts/rag_ingest.py`);
* LOADED vectors for the `vector` and `hybrid` modes — `service.recuperar` raises
  `EmbeddingsNoCargadas` on a never-embedded snapshot rather than letting the leg
  contribute an empty list under a hybrid label;
* the query embedder that WROTE those vectors — a mismatch raises
  `EmbedderMismatch` in both directions;
* `RAG_GOLD_PRIVADO_PATH` for the gold items whose text is not in this public
  repository. Without it the run still produces diagnostics and refuses to emit a
  go/no-go, because a pair computed over 26 of 52 questions is a different
  measurement wearing the ratified one's name.

Exit codes: 0 success · 1 run refused (privacy gate, synthetic snapshot, missing
snapshot) · 2 usage.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.domains.conocimiento.embedding import (  # noqa: E402
    DEFAULT_MODEL_ID,
    DeterministicEmbedder,
    get_embedder,
)
from app.domains.conocimiento.eval.harness import (  # noqa: E402
    MODOS_ABLACION,
    cargar_gold_set,
    decidir_go_no_go,
    evaluar,
)
from app.domains.conocimiento.eval.report import (  # noqa: E402
    EvalSinteticoNoEsEval,
    escribir_reporte,
)
from app.domains.conocimiento.service import procedencia_embeddings  # noqa: E402

DESTINO_POR_DEFECTO = Path(__file__).resolve().parent.parent.parent / "docs" / "rag"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-sha", required=True)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument(
        "--modo",
        action="append",
        choices=MODOS_ABLACION,
        help="repeatable; defaults to all three (the ablation)",
    )
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--destino", type=Path, default=DESTINO_POR_DEFECTO)
    parser.add_argument(
        "--embedder",
        default="bge-m3",
        choices=("bge-m3", "e5-large", "deterministic"),
        help="query embedder; MUST be the one that wrote the vectors",
    )
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--device", default="cpu")
    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        help=(
            "render a clearly-labelled SMOKE RUN over synthetic vectors. The "
            "output carries no verdict and its filename says SINTETICO."
        ),
    )
    parser.add_argument(
        "--generado-en",
        help=(
            "ISO-8601 timestamp for the report header. Defaults to the wall "
            "clock; pass it to get a byte-identical artifact from a byte-"
            "identical database."
        ),
    )
    return parser


def _embedder(nombre: str, *, device: str, model_id: str):
    """The deterministic fake is selectable, and only selectable ON PURPOSE.

    It is not a fallback: `--embedder deterministic` against a real snapshot is
    refused by `service.verificar_embedder`, and a smoke snapshot queried with
    the real model is refused just as loudly in the other direction.
    """
    if nombre == "deterministic":
        return DeterministicEmbedder()
    return get_embedder(nombre, device=device, model_id=model_id)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.database_url:
        print("ERROR: --database-url (or DATABASE_URL) is required", file=sys.stderr)
        return 2

    modos = tuple(args.modo) if args.modo else MODOS_ABLACION
    # The timestamp is read ONCE, here at the edge, and threaded through as a
    # value. Nothing downstream touches a clock, which is what makes "same
    # database in, same report out" checkable.
    generado_en = (
        dt.datetime.fromisoformat(args.generado_en)
        if args.generado_en
        else dt.datetime.now(dt.timezone.utc)
    )

    gold = cargar_gold_set()
    precondicion = gold.precondicion()
    print(
        f"gold set: {len(gold.items)} ítems "
        f"(respondibles {gold.n_respondibles} · abstención {gold.n_unanswerable})"
    )
    if not precondicion.evaluable:
        print("gold set NO evaluable — el reporte saldrá sin veredicto:")
        for motivo in precondicion.motivos:
            print(f"  - {motivo}")

    # Ordering is the usability property, and it mirrors `rag_ingest.py`'s: every
    # cheap refusal runs BEFORE the expensive step. Building the embedder first
    # meant a mistyped `--corpus-sha` reported "install torch" instead of "that
    # snapshot does not exist", and a synthetic snapshot spent two minutes and
    # 2.2 GB loading BGE-M3 before the report refused it.
    engine = create_engine(args.database_url)
    with Session(engine) as db:
        procedencia = procedencia_embeddings(db, args.corpus_sha)
        if procedencia is None:
            print(
                f"ERROR: snapshot {args.corpus_sha} is not in rag_corpus. Run "
                "scripts/rag_ingest.py first.",
                file=sys.stderr,
            )
            return 1
        if procedencia.sintetico and not args.allow_synthetic:
            print(
                f"ERROR: snapshot {args.corpus_sha} holds SYNTHETIC vectors "
                f"(embedding_modelo={procedencia.modelo!r}). Refusing before "
                "running anything: the report would be shaped like a measurement "
                "and would not be one. Load real vectors, or pass "
                "--allow-synthetic for a labelled SMOKE RUN.",
                file=sys.stderr,
            )
            return 1

        embedder = None
        if any(modo in ("vector", "hybrid") for modo in modos):
            embedder = _embedder(args.embedder, device=args.device, model_id=args.model_id)

        resultado = evaluar(db, args.corpus_sha, gold, modos=modos, k=args.k, embedder=embedder)

    try:
        escrito = escribir_reporte(
            resultado,
            procedencia,
            destino=args.destino,
            generado_en=generado_en,
            device_consulta=args.device,
            permitir_sintetico=args.allow_synthetic,
        )
    except EvalSinteticoNoEsEval as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    for modo in resultado.modos:
        corrida = resultado.por_modo[modo]
        decision = decidir_go_no_go(corrida, gold)
        veredicto = "NO EVALUABLE" if procedencia.sintetico else decision.veredicto
        print(f"  {modo:<7} {veredicto}", end="")
        if decision.barras_fallidas:
            print(f"  (fallan: {', '.join(decision.barras_fallidas)})", end="")
        if corrida.cobertura.leg_fts_degradada:
            print("  [LEG FTS DEGRADADA — ver RAG4-001]", end="")
        print()

    print(f"\nreporte: {escrito.markdown}")
    print(f"json   : {escrito.json}")
    return 0


if __name__ == "__main__":  # pragma: no cover - thin CLI shim
    raise SystemExit(main())
