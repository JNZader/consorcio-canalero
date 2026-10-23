"""The mute kernel: `buscar`, `leer`, `chequear` over a database `Session`.

Exactly three functions, shared by the norms route, the CLI and the MCP mirror.
They find, read and verify legal units, and they never write prose: there is no
`redactar`, no generation provider, no prompt. A fourth function here would be a
fourth tool on every surface, which is the thing the kernel spec forbids.

**Order policy lives here, not on each surface** (`design.md`, "Order policy
location"). The route, the CLI and the MCP must return identical units and fields
for the same query, mode and active SHA, so the decision to show a rank is made
once, below all of them:

* ranked ONLY when the mode is the no-GPU arm AND `eval/barra_sin_gpu.yaml` is
  `superada` for the active SHA (the loader re-checks every figure). Units are
  then in BM25 order with a 1-based `rango`; scores are never shown.
* otherwise units are sorted by `citation_key` and carry no `rango`. A mode with
  no matching artifact is unranked, and that includes `bm25_ce` from the CLI: the
  artifact measures the no-GPU arm and says nothing about any other.

An empty retrieval sets `sin_unidades`. It is not an abstention and carries no
abstention field.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domains.conocimiento import repository, service
from app.domains.conocimiento.eval import barra_sin_gpu
from app.domains.conocimiento.recuperacion.reranker import Reranker
from app.domains.conocimiento.schemas import (
    CitaRecuperada,
    CondicionChequeo,
    ResultadoNormas,
    ResultadoNormasOrdenado,
    UnidadLeida,
    UnidadNorma,
    UnidadNormaOrdenada,
    VeredictoChequeo,
)

#: Shown whenever no rank order is presented. Spanish because the admin panel
#: renders it as is.
NOTA_SIN_ORDEN = (
    "No se presenta orden de relevancia: las unidades se listan por clave de cita. "
    "El orden solo se muestra cuando la medición registrada del brazo sin GPU "
    "supera la barra para este corpus."
)

#: Shown when a rank order IS presented. It names what the order is and is not.
NOTA_CON_ORDEN = (
    "Orden del brazo {modo} (BM25, sin cross-encoder). Es un orden, no un puntaje de relevancia."
)


class SinCorpusActivo(RuntimeError):
    """No `rag_corpus` row is active, so there is nothing to search, read or check."""


class UnidadNoEncontrada(LookupError):
    """The key is not a unit of the active snapshot. No text is returned with it."""


def _corpus_activo(db: Session) -> repository.CorpusActivo:
    activo = repository.leer_corpus_activo(db)
    if activo is None:
        raise SinCorpusActivo(
            "no active corpus: rag_corpus has no row with activo=true. Refusing to pick "
            "the newest snapshot as a fallback."
        )
    return activo


def buscar(
    db: Session,
    consulta: str,
    *,
    modo: str,
    k: int = 10,
    reranker: Reranker | None = None,
) -> ResultadoNormas:
    """Retrieve units from the ACTIVE snapshot and apply the order policy.

    `modo` is explicit on purpose: there is no default arm in the kernel. The
    surfaces choose (the route is pinned to the no-GPU arm), and `service.recuperar`
    keeps every refusal it already has: `bm25_ce` without a reranker still raises
    `RerankerRequerido`, and the no-GPU arm refuses a reranker or a `qvec`.
    """
    activo = _corpus_activo(db)
    resultado = service.recuperar(
        db, activo.corpus_sha, consulta, modo=modo, k=k, reranker=reranker
    )

    ordenado = (
        modo == service.MODO_SIN_GPU
        and bool(resultado.hits)
        and barra_sin_gpu.superada_para(activo.corpus_sha)
    )
    if ordenado:
        return _ordenado(activo, modo, resultado.hits)
    return _sin_orden(activo, modo, resultado.hits)


def _ordenado(
    activo: repository.CorpusActivo, modo: str, hits: list[CitaRecuperada]
) -> ResultadoNormasOrdenado:
    """BM25 order with a 1-based `rango`. The BM25 value itself is dropped here."""
    por_rango = sorted(hits, key=lambda hit: (hit.rango_bm25 is None, hit.rango_bm25 or 0))
    return ResultadoNormasOrdenado(
        modo=modo,
        corpus_sha=activo.corpus_sha,
        ingested_at=activo.ingested_at,
        unidades=[
            UnidadNormaOrdenada(**UnidadNorma.model_validate(hit).model_dump(), rango=posicion)
            for posicion, hit in enumerate(por_rango, start=1)
        ],
        sin_unidades=False,
        nota_orden=NOTA_CON_ORDEN.format(modo=modo),
        orden_modo=modo,
    )


def _sin_orden(
    activo: repository.CorpusActivo, modo: str, hits: list[CitaRecuperada]
) -> ResultadoNormas:
    """Sorted by `citation_key`: a position that implies nothing about relevance."""
    unidades = sorted(
        (UnidadNorma.model_validate(hit) for hit in hits), key=lambda unidad: unidad.citation_key
    )
    return ResultadoNormas(
        modo=modo,
        corpus_sha=activo.corpus_sha,
        ingested_at=activo.ingested_at,
        unidades=unidades,
        sin_unidades=not unidades,
        nota_orden=NOTA_SIN_ORDEN,
    )


def leer(db: Session, citation_key: str) -> UnidadLeida:
    """The byte-exact unit and its provenance, for a key of the ACTIVE snapshot.

    A key that exists only in another snapshot is "not found": the lookup is
    scoped by the active `corpus_sha`, never by a global key search.
    """
    activo = _corpus_activo(db)
    fila = repository.leer_unidad(db, activo.corpus_sha, citation_key)
    if fila is None:
        raise UnidadNoEncontrada(
            f"{citation_key!r} is not a unit of the active snapshot {activo.corpus_sha}."
        )
    return UnidadLeida(**fila, corpus_sha=activo.corpus_sha, ingested_at=activo.ingested_at)


def _rechazo(
    condicion: CondicionChequeo, detalle: str, clasificacion: str | None = None
) -> VeredictoChequeo:
    return VeredictoChequeo(
        pasa=False,
        condicion_fallida=condicion,
        clasificacion=clasificacion,
        detalle=f"{condicion}: {detalle}",
    )


def chequear(
    db: Session,
    citation_key: str,
    span: str,
    vigencia: str | None,
    sha: str,
) -> VeredictoChequeo:
    """Verify a citation. Passes only when ALL four conditions hold, checked in order.

    1. `sha` is the active corpus SHA. A stale SHA is a refusal, never a warning.
    2. `citation_key` exists at that SHA.
    3. `span` is a NON-EMPTY, literal substring of that unit's `texto`. No case or
       whitespace normalisation: a citation is a quote, and a normalised quote is
       a paraphrase.
    4. `vigencia` equals the unit's stored `estado_vigencia`.

    The first failed condition is the one named, so a refusal says what to fix
    first. The verdict carries the unit's `clasificacion` whenever the unit was
    found, which is what lets the editor refuse a `privado` unit.
    """
    activo = repository.leer_corpus_activo(db)
    if activo is None:
        return _rechazo("sha", "there is no active corpus, so no SHA can be the active one.")
    if sha != activo.corpus_sha:
        return _rechazo("sha", f"{sha!r} is not the active corpus SHA {activo.corpus_sha!r}.")

    fila = repository.leer_unidad(db, activo.corpus_sha, citation_key)
    if fila is None:
        return _rechazo("clave", f"{citation_key!r} is not a unit of snapshot {sha}.")

    clasificacion = fila["clasificacion"]
    if not span:
        return _rechazo("span", "the span is empty.", clasificacion)
    if span not in fila["texto"]:
        return _rechazo(
            "span", f"the span is not a substring of the text of {citation_key!r}.", clasificacion
        )
    if vigencia != fila["estado_vigencia"]:
        return _rechazo(
            "vigencia",
            f"the unit's estado_vigencia is {fila['estado_vigencia']!r}, not {vigencia!r}.",
            clasificacion,
        )
    return VeredictoChequeo(pasa=True, clasificacion=clasificacion, detalle="ok")
