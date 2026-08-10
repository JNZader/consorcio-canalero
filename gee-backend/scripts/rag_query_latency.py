#!/usr/bin/env python3
"""Measure CPU query-embedding latency for the V1 serving question (design.md D3).

    venv-rag/bin/python scripts/rag_query_latency.py \\
        --preguntas docs/rag/preguntas-latencia.txt \\
        --device cpu --threads 2

The question this answers is narrow and worth stating: **can a CPU-only box turn
a question into a query vector fast enough to serve?** Corpus vectors come from
the GPU once; query vectors would have to be computed per request on the CX33,
which has 2 shared vCPUs and no GPU. p50/p95 over the gold questions is the
number that decides whether V0's local-only posture can become a V1 endpoint.

`--threads` exists because `torch.set_num_threads` dominates this measurement and
leaving it implicit makes two runs on the same machine disagree. It is recorded
in the output for the same reason.

**Every reported number carries its conditions.** A latency figure without core
count, thread setting and device is not a measurement, it is a rumour — and the
CX33 comparison in particular is an ESTIMATE unless it was taken on the CX33
(Ops O.4 resolved it as: measure locally for V0, labelled; on-box measurement
deferred to the V1 gate).
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domains.conocimiento.embedding import DEFAULT_MODEL_ID, get_embedder  # noqa: E402

CALENTAMIENTOS = 3
REPETICIONES = 3


def leer_preguntas(path: Path) -> list[str]:
    """One question per line; blanks and `#` comments ignored.

    A plain text file rather than the gold set because the gold set is a slice-4
    artifact and this measurement must not wait for owner curation to be
    runnable. `--gold-set` reads that file instead once it exists.
    """
    preguntas = [
        linea.strip()
        for linea in path.read_text(encoding="utf-8").splitlines()
        if linea.strip() and not linea.lstrip().startswith("#")
    ]
    if not preguntas:
        raise ValueError(f"{path} holds no questions")
    return preguntas


def leer_gold_set(path: Path) -> list[str]:
    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = raw.get("items", raw if isinstance(raw, list) else [])
    preguntas = [str(item["pregunta"]) for item in items if item.get("pregunta")]
    if not preguntas:
        raise ValueError(f"{path} holds no `pregunta` entries")
    return preguntas


def medir(embedder, preguntas: Sequence[str]) -> dict[str, float]:
    """Latency of ONE question at a time — the shape a request would have.

    Batching would report a throughput number and quietly answer a different
    question than the one asked: a served endpoint embeds one query per request.
    """
    for pregunta in preguntas[:CALENTAMIENTOS]:
        embedder.encode([pregunta])

    muestras: list[float] = []
    for _ in range(REPETICIONES):
        for pregunta in preguntas:
            inicio = time.perf_counter()
            embedder.encode([pregunta])
            muestras.append((time.perf_counter() - inicio) * 1000)

    ordenadas = sorted(muestras)
    return {
        "n": len(muestras),
        "p50_ms": statistics.median(ordenadas),
        "p95_ms": ordenadas[min(len(ordenadas) - 1, int(round(0.95 * (len(ordenadas) - 1))))],
        "min_ms": ordenadas[0],
        "max_ms": ordenadas[-1],
        "media_ms": statistics.fmean(ordenadas),
    }


def _configurar_threads(threads: int | None) -> int | None:
    if threads is None:
        return None
    try:
        import torch
    except ImportError:  # pragma: no cover — environment-dependent
        return None
    torch.set_num_threads(threads)
    return int(torch.get_num_threads())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    fuente = parser.add_mutually_exclusive_group(required=True)
    fuente.add_argument("--preguntas", type=Path, help="text file, one question per line")
    fuente.add_argument("--gold-set", type=Path, help="eval/gold_set.yaml (slice 4)")
    parser.add_argument("--model", default=DEFAULT_MODEL_ID)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--threads", type=int, default=None)
    parser.add_argument(
        "--embedder",
        default="bge-m3",
        choices=("bge-m3", "deterministic"),
        help="'deterministic' measures the harness, not the model — plumbing only",
    )
    parser.add_argument("--json", type=Path, default=None, help="also write results here")
    parser.add_argument(
        "--etiqueta",
        default="LOCAL",
        help=(
            "how the report must label these numbers. Use ESTIMATE for anything "
            "that is not the target machine (Ops O.4)."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    preguntas = leer_preguntas(args.preguntas) if args.preguntas else leer_gold_set(args.gold_set)
    threads = _configurar_threads(args.threads)

    try:
        embedder = get_embedder(args.embedder, device=args.device, model_id=args.model)
    except RuntimeError as missing:  # pragma: no cover — environment-dependent
        print(f"\n{missing}", file=sys.stderr)
        return 2

    metricas = medir(embedder, preguntas)
    reporte = {
        "etiqueta": args.etiqueta,
        "modelo": embedder.model_id,
        "sintetico": bool(getattr(embedder, "sintetico", False)),
        "device": args.device,
        "cpu_count": os.cpu_count(),
        "torch_threads": threads,
        "preguntas": len(preguntas),
        "calentamientos": CALENTAMIENTOS,
        "repeticiones": REPETICIONES,
        **metricas,
    }

    ancho = max(len(clave) for clave in reporte)
    for clave, valor in reporte.items():
        print(f"{clave.ljust(ancho)} : {valor}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(reporte, indent=2) + "\n", encoding="utf-8")
        print(f"\nescrito: {args.json}")

    if reporte["sintetico"]:
        print(
            "\nADVERTENCIA: --embedder deterministic mide el arnés, no el modelo. "
            "No es un número de latencia de BGE-M3.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
