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
from app.domains.conocimiento.eval.answers import (  # noqa: E402
    ConjuntoRespuestasInvalido,
    ConjuntoRespuestasNoRatificado,
    EntradaRespuestas,
    PayloadDivergente,
    PinRespuestasDivergente,
    RespuestasSinteticas,
    cargar_y_puntuar,
)
from app.domains.conocimiento.eval.report import (  # noqa: E402
    EvalSinteticoNoEsEval,
    escribir_reporte,
)
from app.domains.conocimiento.eval.router import (  # noqa: E402
    EntradaRouter,
    correr_eval_router,
)
from app.domains.conocimiento.generacion import PLANTILLAS  # noqa: E402
from app.domains.conocimiento.recuperacion.reranker import (  # noqa: E402
    BGEReranker,
    RerankerDeterministico,
    RerankerNoDisponible,
)
from app.domains.conocimiento.routing import SetRouterNoRatificado  # noqa: E402
from app.domains.conocimiento.service import MODOS, procedencia_embeddings  # noqa: E402

DESTINO_POR_DEFECTO = Path(__file__).resolve().parent.parent.parent / "docs" / "rag"

#: Exit code for "these two inputs do not describe the same corpus revision".
SALIDA_IDENTIDAD = 4

#: Exit code for "this interpreter cannot build the requested embedder". Shares
#: 2 with the usage errors, and that is the right bucket rather than a laxity:
#: nothing was queried and nothing was written, and the fix is to invoke the
#: script differently (`venv-rag/bin/python`, or `--modo fts`) — exactly what an
#: argument error means. `scripts/rag_query_latency.py` already used 2 for it.
SALIDA_SIN_DEPENDENCIA = 2


#: Why the report says the router was not scored on a run that built no
#: embedder. Named at the edge, so the document states the command that WOULD
#: score it instead of leaving a silent gap where a section belongs.
MOTIVO_ROUTER_SIN_EMBEDDER = (
    "El bloque del router no se puntuó: esta corrida no construyó un embebedor "
    "(`--modo fts` no necesita uno). Para puntuarlo: "
    "`make rag-eval RAG_EVAL_PYTHON=venv-rag/bin/python`."
)


def _entrada_router(embedder, *, pasos: int) -> EntradaRouter:
    """Score the ratified router set, or state why this run cannot.

    Reuses the embedder the ablation already built rather than making a second
    one: two embedders in one process is two model loads, and — the part that
    matters — a report whose retrieval and router figures could quietly come
    from different weights.
    """
    if embedder is None:
        return EntradaRouter.no_evaluable(MOTIVO_ROUTER_SIN_EMBEDDER)
    try:
        resultado = correr_eval_router(embedder, pasos=pasos)
    except SetRouterNoRatificado as motivo:
        # The set is not ratified, or is ratified and too thin. Either way this
        # is `not-evaluable` in the report, never a missing section.
        return EntradaRouter.no_evaluable(str(motivo))
    return EntradaRouter(resultado=resultado, embedder=embedder)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-sha", required=True)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument(
        "--modo",
        action="append",
        choices=MODOS,
        help=(
            "repeatable; defaults to the three-mode ablation. `bm25_ce` is the "
            "GATED arm (task 9.1b) and needs a reranker — see --reranker."
        ),
    )
    parser.add_argument(
        "--reranker",
        default="bge",
        choices=("bge", "deterministic"),
        help=(
            "cross-encoder for `--modo bm25_ce`. `deterministic` is a stand-in "
            "for smoke runs ONLY: the report it produces carries no verdict and "
            "its filename says SINTETICO, because in `bm25_ce` the order is the "
            "cross-encoder's alone and a stand-in replaces the ranking entirely."
        ),
    )
    parser.add_argument(
        "--reranker-device",
        default="cuda",
        help="device for the real cross-encoder. CPU at depth 50 is ~99 s/query.",
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
        "--router-pasos",
        type=int,
        default=7,
        help=(
            "grid resolution for the router's LOOCV calibration. 7 is the "
            "shipped value (~3 min at 1024 dimensions over the ratified n=49 "
            "set); lower it for a quick smoke, never to publish a figure."
        ),
    )
    parser.add_argument(
        "--answer-set",
        type=Path,
        default=None,
        help=(
            "graded answer set (tasks 9.1-9.4). Defaults to NOT scoring the "
            "answer-level block, which the report then states in words. The "
            "answers themselves come from the GPU worker through the runbook; "
            "this command grades nothing and scores what it is handed."
        ),
    )
    parser.add_argument(
        "--provider-model-pin",
        default=None,
        help=(
            "the model this run's answers were produced by, compared against the "
            "artifact's pin. Defaults to `settings.conocimiento_modelo`."
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


#: Why the report says the answer-level block was not scored on a run that was
#: not handed an answer set. Same discipline as `MOTIVO_ROUTER_SIN_EMBEDDER`: the
#: document states the command that WOULD score it, rather than leaving a gap
#: where a section belongs — an absent section reads as a section that was fine.
MOTIVO_SIN_ANSWER_SET = (
    "El bloque de métricas por respuesta no se puntuó: esta corrida no recibió "
    "`--answer-set`. Las respuestas las produce el worker con GPU (runbook G9) "
    "contra el pin real, y el owner las gradúa; recién entonces hay artefacto "
    "que pasarle a este comando."
)


def _entrada_respuestas(db, args) -> EntradaRespuestas:
    """Load, pin-check and score the graded answer set, or say why there is none.

    Every refusal degrades into a STATED `not-evaluable` rather than killing the
    run, and that asymmetry is deliberate: the retrieval ablation is a separate,
    complete measurement, and losing it because an answer set is unratified would
    make the report's most expensive half hostage to its cheapest.

    The one thing that never happens is a figure with no provenance behind it.
    """
    if args.answer_set is None:
        return EntradaRespuestas.no_evaluable(MOTIVO_SIN_ANSWER_SET)

    from app.config import settings

    pin = args.provider_model_pin or settings.conocimiento_modelo
    try:
        return cargar_y_puntuar(
            db,
            ruta=args.answer_set,
            prompt_version=PLANTILLAS.version,
            provider_model_pin=pin,
            corpus_sha=args.corpus_sha,
        )
    except (
        ConjuntoRespuestasNoRatificado,
        ConjuntoRespuestasInvalido,
        PinRespuestasDivergente,
        PayloadDivergente,
        RespuestasSinteticas,
    ) as motivo:
        return EntradaRespuestas.no_evaluable(str(motivo))


def _reranker(nombre: str, *, device: str):
    """The stand-in is selectable, and only selectable ON PURPOSE.

    Exactly like `_embedder`: it is not a fallback. A `bm25_ce` arm ordered by
    `RerankerDeterministico` is refused at the publish gate
    (`report._gate_sintetico`) unless `--allow-synthetic` is also passed, and what
    comes out then is a SMOKE RUN with no verdict.
    """
    if nombre == "deterministic":
        return RerankerDeterministico()
    return BGEReranker(device=device)


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

        reranker = None
        if "bm25_ce" in modos:
            try:
                reranker = _reranker(args.reranker, device=args.reranker_device)
            except (RerankerNoDisponible, RuntimeError, ImportError) as falta:
                # Same bucket and same reason as the embedder branch above:
                # nothing was queried, nothing was written, and the fix is to
                # invoke the script differently. There is deliberately NO CPU
                # fallback — the ratified numbers were measured on this model,
                # and 99 s/query at depth 50 is an outage that answers.
                print(f"\nERROR: {falta}", file=sys.stderr)
                print(
                    "\nO bien corré la ablación sin el arm gateado:\n"
                    "    python scripts/rag_eval.py --modo fts …\n"
                    "Para un smoke SIN GPU (sin veredicto, archivo SINTETICO-):\n"
                    "    python scripts/rag_eval.py --modo bm25_ce "
                    "--reranker deterministic --allow-synthetic …",
                    file=sys.stderr,
                )
                return SALIDA_SIN_DEPENDENCIA

        resultado = evaluar(
            db,
            args.corpus_sha,
            gold,
            modos=modos,
            k=args.k,
            embedder=embedder,
            reranker=reranker,
        )

        # Inside the session, because `verificar_payload` re-derives the
        # shippable set from the LIVE classification with the same call the
        # request path makes. That is the check that catches a reclassification
        # with `corpus_sha` unmoved, and it cannot be done from a header.
        entrada_respuestas = _entrada_respuestas(db, args)

    entrada_router = _entrada_router(embedder, pasos=args.router_pasos)

    try:
        escrito = escribir_reporte(
            resultado,
            procedencia,
            destino=args.destino,
            generado_en=generado_en,
            device_consulta=args.device,
            permitir_sintetico=args.allow_synthetic,
            latencia=latencia,
            router=entrada_router,
            respuestas=entrada_respuestas,
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
        if decision.barras_no_evaluables:
            # Separate line item, never merged into "fallan": these were not
            # measured at all, and an operator who reads them as failures goes
            # looking for a retrieval bug that does not exist (task 9.1b/9.5).
            print(f"  (not-evaluable: {', '.join(decision.barras_no_evaluables)})", end="")
        if corrida.cobertura.leg_fts_degradada:
            print("  [LEG FTS DEGRADADA — ver RAG4-001]", end="")
        print()

    evaluacion_router = entrada_router.evaluacion()
    if evaluacion_router is None:
        print(f"  {'router':<7} NO EVALUABLE")
    elif evaluacion_router.veredicto is None:
        print(f"  {'router':<7} SIN VEREDICTO (barra_no_ratificada)")
    else:
        print(
            f"  {'router':<7} {'PASA' if evaluacion_router.veredicto else 'NO PASA'}"
            + (
                ""
                if evaluacion_router.veredicto
                else f"  (fallan: {'; '.join(evaluacion_router.componentes_fallidos)})"
            )
        )

    print(f"\nreporte: {escrito.markdown}")
    print(f"json   : {escrito.json}")
    return 0


if __name__ == "__main__":  # pragma: no cover - thin CLI shim
    raise SystemExit(main())
