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
snapshot) · 2 usage, INCLUDING "this interpreter has no torch" · 4 the gold set
and the snapshot are not the same corpus revision, or the owner-side private
file belongs to a different set.

4 is its own code rather than another 1 because it is the one refusal that is
never about the database: nothing was queried, nothing was written, and the fix
is to correct an argument or an environment variable — not to load vectors or
re-ingest.

**Which interpreter to run this with.** `vector` and `hybrid` build a real
embedder, which needs `requirements-rag.txt` — the CUDA stack, deliberately kept
out of the app venv (D8). So the three-mode ablation runs under `venv-rag`:

    venv-rag/bin/python scripts/rag_eval.py --corpus-sha … --database-url …

`make rag-eval RAG_EVAL_PYTHON=venv-rag/bin/python` is the same thing. Under the
default `venv` the run exits **2** naming `requirements-rag.txt` instead of
dying on an ImportError traceback; `--modo fts` needs no torch and runs
anywhere.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
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
    CorpusShaMismatch,
    GoldSetInvalido,
    cargar_gold_set,
    decidir_go_no_go,
    evaluar,
    verificar_corpus_sha,
)
from app.domains.conocimiento.eval.report import (  # noqa: E402
    EvalSinteticoNoEsEval,
    escribir_reporte,
)
from app.domains.conocimiento.service import procedencia_embeddings  # noqa: E402

DESTINO_POR_DEFECTO = Path(__file__).resolve().parent.parent.parent / "docs" / "rag"

#: Exit code for "these two inputs do not describe the same corpus revision".
SALIDA_IDENTIDAD = 4

#: Exit code for "this interpreter cannot build the requested embedder". Shares
#: 2 with the usage errors, and that is the right bucket rather than a laxity:
#: nothing was queried and nothing was written, and the fix is to invoke the
#: script differently (`venv-rag/bin/python`, or `--modo fts`) — exactly what an
#: argument error means. `scripts/rag_query_latency.py` already used 2 for it.
SALIDA_SIN_DEPENDENCIA = 2


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
        "--latencia",
        type=Path,
        default=None,
        help=(
            "JSON written by scripts/rag_query_latency.py --json. Its p50/p95 and "
            "its LOCAL/ESTIMATE label are rendered into the report; without it "
            "the report states that the latency criterion was not evaluated."
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


#: Fields of the latency JSON that the report renders through a float format.
#: A string here does not degrade the block, it kills the run inside
#: `report.py::_bloque_latencia` — `f"{'lento':.1f}"` raises — and it kills it
#: AFTER the 52-question ablation has already been paid for. A bool is worse:
#: `f"{True:.1f}"` renders `1.0`, so a malformed file publishes a latency figure
#: that was never measured. Both are caught here, at the edge, next to the read.
CAMPOS_NUMERICOS_LATENCIA = (
    "p50_ms",
    "p95_ms",
    "min_ms",
    "max_ms",
    "n",
    "preguntas",
    "repeticiones",
    "calentamientos",
    "cpu_count",
    "torch_threads",
)

#: Without these two the block has nothing to say: they ARE the criterion.
CAMPOS_LATENCIA_OBLIGATORIOS = ("p50_ms", "p95_ms")


def problemas_de_latencia(datos: object) -> list[str]:
    """Everything wrong with a parsed `--latencia` payload, or an empty list."""
    if not isinstance(datos, dict):
        return [f"el JSON es {type(datos).__name__}, se esperaba un objeto"]

    problemas = [f"falta `{campo}`" for campo in CAMPOS_LATENCIA_OBLIGATORIOS if campo not in datos]
    for campo in CAMPOS_NUMERICOS_LATENCIA:
        if campo not in datos:
            continue
        valor = datos[campo]
        if valor is None:
            continue
        # `bool` is an `int` in Python, and `True` formats as `1.0` — exactly the
        # fabricated number this check exists to refuse.
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            problemas.append(f"`{campo}` es {valor!r}, se esperaba un número")
    return problemas


def _embedder(nombre: str, *, device: str, model_id: str):
    """The deterministic fake is selectable, and only selectable ON PURPOSE.

    It is not a fallback: `--embedder deterministic` against a real snapshot is
    refused by `service.verificar_embedder`, and a smoke snapshot queried with
    the real model is refused just as loudly in the other direction.
    """
    if nombre == "deterministic":
        return DeterministicEmbedder()
    # `query`: the eval turns gold QUESTIONS into vectors. Ignored by the
    # symmetric models, load-bearing for e5 (see `E5Embedder`).
    return get_embedder(nombre, rol="query", device=device, model_id=model_id)


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

    # Identity before anything else: this is a string comparison, it needs no
    # database, no directory and no 2.2 GB model, and getting it wrong produces a
    # NO-GO that looks like a retrieval failure. Same ordering principle as the
    # snapshot checks below — cheapest refusal first — applied one step earlier
    # because these two inputs must describe the same corpus revision before it
    # is worth asking a database anything (ledger RAG4-003).
    try:
        gold = cargar_gold_set()
        verificar_corpus_sha(gold, args.corpus_sha)
    except (CorpusShaMismatch, GoldSetInvalido) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return SALIDA_IDENTIDAD

    # Read at the edge, like the timestamp, and read EARLY: a typo in the path
    # must not be discovered after a 52-question ablation has run. Absent, the
    # report says the latency criterion was not evaluated rather than omitting
    # the section, which would read as "not applicable".
    #
    # Parsing is not validation, and reading the file early bought nothing while
    # the SHAPE was still checked at render time (ledger RJDB-102 ≡ RJDA-105):
    # any JSON at all parsed here, and a list — or a dict with a string where a
    # float belongs — took the ablation down at the last block of the report.
    latencia = None
    if args.latencia is not None:
        try:
            crudo = json.loads(args.latencia.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            print(
                f"ERROR: --latencia {args.latencia}: {error}\n"
                "Produce it with: scripts/rag_query_latency.py … --json <path>",
                file=sys.stderr,
            )
            return 2
        problemas = problemas_de_latencia(crudo)
        if problemas:
            print(
                f"ERROR: --latencia {args.latencia} no tiene la forma que "
                "escribe scripts/rag_query_latency.py --json:",
                file=sys.stderr,
            )
            for problema in problemas:
                print(f"  - {problema}", file=sys.stderr)
            print(
                f"Regeneralo con: scripts/rag_query_latency.py … --json {args.latencia}",
                file=sys.stderr,
            )
            return 2
        latencia = crudo

    precondicion = gold.precondicion()
    print(
        f"gold set: {len(gold.items)} ítems "
        f"(respondibles {gold.n_respondibles} · abstención {gold.n_unanswerable}) "
        f"· corpus_sha {gold.corpus_sha}"
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
            try:
                embedder = _embedder(args.embedder, device=args.device, model_id=args.model_id)
            except (RuntimeError, ImportError) as falta:
                # `BGEM3Embedder.__init__` raises this when torch/transformers are
                # absent, which is the DEFAULT state of `venv/` by design: the
                # ingestion extra pulls the whole CUDA stack and is deliberately
                # kept out of the app image (design.md D8). So the common way to
                # run this script is also the way that hits this branch, and
                # before it existed the CLI answered with a raw ImportError
                # traceback — an environment problem presented as a crash, with
                # the one-line fix buried in the exception's own message.
                # `scripts/rag_query_latency.py` already handled it this way.
                #
                # `ImportError` is caught alongside `RuntimeError` (ledger
                # RJDA-104) because the guarantee this branch depends on lives in
                # another module: the embedders happen to WRAP the ImportError
                # today, and the day one of them re-raises or a new backend
                # forgets the wrapper, the failure mode is the raw traceback this
                # branch was written to remove — a silent regression, since
                # nothing in the happy path changes. Catching both makes the CLI's
                # contract independent of the raise site's choice of class.
                print(f"\nERROR: {falta}", file=sys.stderr)
                print(
                    "\nO bien corré la ablación sólo con la pierna léxica, que no "
                    "necesita torch:\n"
                    "    python scripts/rag_eval.py --modo fts …",
                    file=sys.stderr,
                )
                return SALIDA_SIN_DEPENDENCIA

        resultado = evaluar(db, args.corpus_sha, gold, modos=modos, k=args.k, embedder=embedder)

    try:
        escrito = escribir_reporte(
            resultado,
            procedencia,
            destino=args.destino,
            generado_en=generado_en,
            device_consulta=args.device,
            permitir_sintetico=args.allow_synthetic,
            latencia=latencia,
        )
    except EvalSinteticoNoEsEval as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    for modo in resultado.modos:
        corrida = resultado.por_modo[modo]
        decision = decidir_go_no_go(corrida, gold)
        # The scoped form, not the bare word: a `GO` printed one line above a
        # degraded-leg warning is the line that gets quoted without the warning.
        veredicto = "NO EVALUABLE" if procedencia.sintetico else decision.veredicto_con_alcance
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
