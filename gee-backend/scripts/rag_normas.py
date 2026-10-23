#!/usr/bin/env python3
"""Search, read and check legal units from the active corpus, from a workstation.

Thin entry point (house precedent: `scripts/rag_eval.py`) — every rule lives in
`app/domains/conocimiento/normas.py`, the same three functions the HTTP route and
the MCP mirror call. Exactly three subcommands, because the kernel has exactly
three functions; there is no `redactar` and no subcommand that writes prose.

    python scripts/rag_normas.py buscar "canal de riego" --k 5
    python scripts/rag_normas.py leer "9750#1"
    python scripts/rag_normas.py chequear "9750#1" --span "administra" \\
        --vigencia vigente --sha 12043582bf8016288a7e8084e85a4b713a97af2f

Database access comes only from `--database-url` / `$DATABASE_URL`. Nothing here
spawns a subprocess, opens a socket other than the database connection, or touches
a VCS.

**Output is JSON on stdout and nothing else**, byte-for-byte the shape the route
returns, so a script can pipe it. Diagnostics go to stderr.

**Whether the units are ordered is not decided here.** `normas.buscar` returns them
sorted by citation key with no rank unless the recorded bar for the no-GPU arm is
`superada` for the active SHA. That includes `--modo bm25_ce`: the artifact
measures the other arm and says nothing about this one.

Exit codes: 0 success (and, for `chequear`, a PASSING verdict) · 1 refused (no
active corpus, unknown key, a failing verdict) · 2 usage, INCLUDING "this
interpreter cannot build the cross-encoder" for `--modo bm25_ce`.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.domains.conocimiento import normas  # noqa: E402
from app.domains.conocimiento.recuperacion.reranker import (  # noqa: E402
    BGEReranker,
    RerankerNoDisponible,
)
from app.domains.conocimiento.schemas import BusquedaNormasEntrada  # noqa: E402
from app.domains.conocimiento.service import MODO_SIN_GPU  # noqa: E402

#: The kernel's three functions, and so this CLI's three subcommands. A fourth
#: would be a fourth tool on every surface, which the kernel spec forbids.
SUBCOMANDOS = ("buscar", "leer", "chequear")

#: The two arms a workstation may ask for. `bm25_ce` is here because the CLI is
#: the one surface that can run it (the route and the MCP are pinned to the
#: no-GPU arm), and it builds the cross-encoder only when asked.
MODOS_CLI = (MODO_SIN_GPU, "bm25_ce")

SALIDA_OK = 0
SALIDA_RECHAZADO = 1
SALIDA_USO = 2


def _comun() -> argparse.ArgumentParser:
    comun = argparse.ArgumentParser(add_help=False)
    comun.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    return comun


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="subcomando", required=True, metavar="|".join(SUBCOMANDOS))

    buscar = sub.add_parser("buscar", parents=[_comun()], help="search the active corpus")
    buscar.add_argument("consulta")
    buscar.add_argument("--k", type=int, default=10)
    buscar.add_argument(
        "--modo",
        choices=MODOS_CLI,
        default=MODO_SIN_GPU,
        help=(
            "`bm25_sin_ce` (default) needs no GPU. `bm25_ce` builds the cross-encoder "
            "and needs requirements-rag.txt; it is never presented as ranked."
        ),
    )
    buscar.add_argument(
        "--reranker-device",
        default="cuda",
        help="device for the cross-encoder under --modo bm25_ce. CPU is ~99 s/query.",
    )

    leer = sub.add_parser("leer", parents=[_comun()], help="read one unit, byte-exact")
    leer.add_argument("citation_key")

    chequear = sub.add_parser(
        "chequear", parents=[_comun()], help="verify a citation: sha, key, span, vigencia"
    )
    chequear.add_argument("citation_key")
    chequear.add_argument("--span", required=True)
    chequear.add_argument(
        "--vigencia",
        default=None,
        help="the estado_vigencia the citation claims; omit to claim none",
    )
    chequear.add_argument("--sha", required=True, help="the corpus SHA the citation was made at")
    return parser


def _reranker(nombre: str, *, device: str):
    """Built only for `--modo bm25_ce`, and only ever the real one: no stand-in here.

    Unlike `rag_eval.py` this surface has no smoke mode, so there is no
    deterministic option to select by accident.
    """
    if nombre != "bge":  # pragma: no cover - the only caller passes "bge"
        raise ValueError(f"unknown reranker {nombre!r}")
    return BGEReranker(device=device)


def _imprimir(modelo) -> None:
    print(modelo.model_dump_json(indent=2))


def _buscar(db: Session, args: argparse.Namespace) -> int:
    reranker = None
    if args.modo == "bm25_ce":
        try:
            reranker = _reranker("bge", device=args.reranker_device)
        except (RerankerNoDisponible, RuntimeError, ImportError) as falta:
            # Same bucket and same reason as `rag_eval.py`: nothing was queried,
            # and the fix is to invoke the script differently. No CPU fallback.
            print(f"ERROR: {falta}", file=sys.stderr)
            print(
                f"\nO bien buscá sin cross-encoder:\n    python scripts/rag_normas.py "
                f"buscar {args.consulta!r} --modo {MODO_SIN_GPU}",
                file=sys.stderr,
            )
            return SALIDA_USO
    _imprimir(normas.buscar(db, args.consulta, modo=args.modo, k=args.k, reranker=reranker))
    return SALIDA_OK


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.database_url:
        print("ERROR: --database-url (or DATABASE_URL) is required", file=sys.stderr)
        return SALIDA_USO

    if args.subcomando == "buscar":
        # The route's own body model, so the CLI refuses exactly what the route
        # refuses (blank query, `k` outside 1..50) instead of drifting from it.
        try:
            entrada = BusquedaNormasEntrada(consulta=args.consulta, k=args.k)
        except ValidationError as error:
            campos = ", ".join(str(e["loc"][-1]) for e in error.errors())
            print(f"ERROR: invalid arguments ({campos}); see --help", file=sys.stderr)
            return SALIDA_USO
        args.consulta, args.k = entrada.consulta, entrada.k

    engine = create_engine(args.database_url)
    try:
        with Session(engine) as db:
            try:
                if args.subcomando == "buscar":
                    return _buscar(db, args)
                if args.subcomando == "leer":
                    _imprimir(normas.leer(db, args.citation_key))
                    return SALIDA_OK
                veredicto = normas.chequear(
                    db, args.citation_key, args.span, args.vigencia, args.sha
                )
                _imprimir(veredicto)
                return SALIDA_OK if veredicto.pasa else SALIDA_RECHAZADO
            except (normas.SinCorpusActivo, normas.UnidadNoEncontrada) as rechazo:
                # A refusal, not a crash: nothing is printed to stdout, so a
                # pipeline cannot read an empty result as an answer.
                print(f"ERROR: {rechazo}", file=sys.stderr)
                return SALIDA_RECHAZADO
    finally:
        engine.dispose()


if __name__ == "__main__":  # pragma: no cover - thin CLI shim
    raise SystemExit(main())
