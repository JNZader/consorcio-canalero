#!/usr/bin/env python3
"""MCP (stdio) mirror of `scripts/rag_normas.py`: exactly three read-only tools.

    venv-mcp/bin/python scripts/rag_normas_mcp.py --database-url "$DATABASE_URL"

The tools are `buscar`, `leer` and `chequear` — the three functions of
`app/domains/conocimiento/normas.py`, the same kernel the HTTP route and the CLI
call, so all three surfaces return identical units. There is no `redactar`: this
server never writes prose, and no tool takes a mode, a reranker or a vector.

The corpus this mirror serves is NOT all public: units classified `privado`
(internal/institutional documents) are returned too, labeled per unit with
`clasificacion`. The server instructions and the `buscar`/`leer` descriptions
(`INSTRUCCIONES`, `DESCRIPCION_*` module constants) say so: whoever pipes this
output into a third-party or cloud LLM is sending that content to an external
provider (audit finding RAG-1, 2026-10).

The protocol is spoken by the OFFICIAL SDK (`requirements-mcp.txt`, exact pin), not
by hand. That dependency lives in its own venv (`venv-mcp/`) outside the app image
and the lock-sync, the way `requirements-rag.txt` does. Importing this module does
NOT need the SDK; only running the server does, so the tool list and the
missing-install path stay testable in the plain app venv.

stdout belongs to the protocol: nothing in this file prints to it.

Exit codes: 0 server stopped · 2 the SDK is not installed here (or no database
URL) — nothing was opened, and the message says how to install it.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.domains.conocimiento import normas  # noqa: E402
from app.domains.conocimiento.schemas import BusquedaNormasEntrada  # noqa: E402
from app.domains.conocimiento.service import MODO_SIN_GPU  # noqa: E402

#: The kernel's three functions, one tool each. The CLI test pins that this equals
#: `rag_normas.SUBCOMANDOS`, so a fourth capability cannot land on one surface only.
TOOLS = ("buscar", "leer", "chequear")

#: Server instructions and tool descriptions, module-level so the SDK-free tests
#: can assert them without importing `mcp`. The private-content warning is the
#: MCP half of audit finding RAG-1 (2026-10): this mirror serves `privado`-
#: classified units, and possession of DATABASE_URL is its only authentication —
#: the client (and whoever operates it) must be told what it is holding before
#: the output is piped anywhere.
INSTRUCCIONES = (
    "Read-only access to the active legal corpus. `buscar` returns candidate "
    "units (ordered by relevance ONLY when the response says orden_presentado "
    "is true), `leer` returns one unit's exact text, `chequear` verifies a "
    "citation. None of them writes text. "
    "WARNING: results may include units whose `clasificacion` is `privado` "
    "(institutional/internal documents); every unit carries its `clasificacion`. "
    "Sending this output to a third-party or cloud LLM sends that content to an "
    "external provider — the operator is responsible for what leaves the machine."
)

#: `buscar` and `leer` return unit TEXT, so both carry the warning. `chequear`
#: returns a verdict only, no corpus text, so it states the label it carries.
DESCRIPCION_BUSCAR = (
    "Search the active corpus. Returns units, byte-exact, with their procedencia "
    "and `clasificacion`. Results may include `privado`-classified units: sending "
    "their text to a third-party/cloud LLM is an external disclosure the operator "
    "is responsible for."
)
DESCRIPCION_LEER = (
    "Read one unit of the active corpus by its citation key, byte-exact. The "
    "response carries `clasificacion`; a `privado` unit's text sent to a "
    "third-party/cloud LLM is an external disclosure the operator is responsible "
    "for."
)
DESCRIPCION_CHEQUEAR = (
    "Check a citation: sha, key, span, vigencia, in that order. A refusal is an "
    "answer. The verdict carries the unit's `clasificacion`; no corpus text is "
    "returned."
)

SALIDA_OK = 0
#: Same bucket and meaning as `rag_eval.SALIDA_SIN_DEPENDENCIA`: nothing ran, and
#: the fix is to invoke the script differently.
SALIDA_SIN_DEPENDENCIA = 2

#: Opens a database session for one tool call; a context manager so the connection
#: is released even when the tool refuses.
AbrirSesion = Callable[[], AbstractContextManager[Session]]


def _mensaje_sin_sdk() -> str:
    return (
        "ERROR: the MCP SDK is not installed in this interpreter.\n"
        "\n"
        "Install it in its own venv (it is deliberately not in the app image):\n"
        "    python -m venv venv-mcp\n"
        "    venv-mcp/bin/pip install -r requirements-mcp.txt\n"
        '    venv-mcp/bin/python scripts/rag_normas_mcp.py --database-url "$DATABASE_URL"\n'
        "\n"
        "The same three operations work without it:\n"
        "    python scripts/rag_normas.py buscar|leer|chequear …"
    )


def build_server(abrir_sesion: AbrirSesion):
    """Assemble the server. Requires the SDK; raises `ImportError` without it."""
    from mcp.server.mcpserver import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
    from mcp.types import ToolAnnotations

    servidor = MCPServer("normas", instructions=INSTRUCCIONES)
    solo_lectura = ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )

    def _rechazo(error: Exception) -> ToolError:
        # An anticipated refusal, so the model reads the reason instead of a
        # generic crash message. The kernel's messages carry no corpus text.
        return ToolError(str(error))

    @servidor.tool(annotations=solo_lectura, description=DESCRIPCION_BUSCAR)
    def buscar(consulta: str, k: int = 10) -> dict[str, Any]:
        """The client-facing description is the module constant `DESCRIPCION_BUSCAR`."""
        try:
            # The route's own body model, so this surface refuses exactly what
            # the route refuses.
            entrada = BusquedaNormasEntrada(consulta=consulta, k=k)
        except ValidationError as error:
            campos = ", ".join(str(e["loc"][-1]) for e in error.errors())
            raise ToolError(f"invalid arguments ({campos})") from None
        try:
            with abrir_sesion() as db:
                resultado = normas.buscar(db, entrada.consulta, modo=MODO_SIN_GPU, k=entrada.k)
        except normas.SinCorpusActivo as error:
            raise _rechazo(error) from None
        return resultado.model_dump(mode="json")

    @servidor.tool(annotations=solo_lectura, description=DESCRIPCION_LEER)
    def leer(citation_key: str) -> dict[str, Any]:
        """The client-facing description is the module constant `DESCRIPCION_LEER`."""
        try:
            with abrir_sesion() as db:
                unidad = normas.leer(db, citation_key)
        except (normas.SinCorpusActivo, normas.UnidadNoEncontrada) as error:
            raise _rechazo(error) from None
        return unidad.model_dump(mode="json")

    @servidor.tool(annotations=solo_lectura, description=DESCRIPCION_CHEQUEAR)
    def chequear(
        citation_key: str, span: str, sha: str, vigencia: str | None = None
    ) -> dict[str, Any]:
        """The client-facing description is the module constant `DESCRIPCION_CHEQUEAR`."""
        try:
            with abrir_sesion() as db:
                veredicto = normas.chequear(db, citation_key, span, vigencia, sha)
        except (normas.SinCorpusActivo, normas.UnidadNoEncontrada) as error:
            raise _rechazo(error) from None
        return veredicto.model_dump(mode="json")

    return servidor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    return parser


def main(argv: list[str] | None = None) -> int:
    # The SDK check goes FIRST: a missing install must be reported as that, not as
    # a missing database URL the operator will fix before hitting the real problem.
    try:
        import mcp  # noqa: F401
    except ImportError:
        print(_mensaje_sin_sdk(), file=sys.stderr)
        return SALIDA_SIN_DEPENDENCIA

    args = build_parser().parse_args(argv)
    if not args.database_url:
        print("ERROR: --database-url (or DATABASE_URL) is required", file=sys.stderr)
        return SALIDA_SIN_DEPENDENCIA

    engine = create_engine(args.database_url)
    try:
        build_server(lambda: Session(engine)).run()
    finally:
        engine.dispose()
    return SALIDA_OK


if __name__ == "__main__":  # pragma: no cover - thin stdio shim
    raise SystemExit(main())
