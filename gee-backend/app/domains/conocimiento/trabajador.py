"""The mailbox worker: one queued item, from question to terminal state (U7).

Amendment A3 moved everything that needs a GPU or a hosted call off the request
path and into here. `procesar_uno` is the whole processing story for ONE item:

    claim → route (U4) → [redirect | retrieve (U2, B50) → generate (U5/U6)] → persist

**Every named refusal in that chain lands as an ITEM STATE, never as a loose
exception.** That is the contract this module exists to keep. The chain has four
sources of named refusals — the sidecar, the retrieval layer, the cost ceilings
and the provider — and each of them already refuses precisely, with a cause. The
failure mode this module is arranged against is any one of them escaping as a
traceback: a worker that dies on a named refusal turns a diagnosable item state
into a log line, and leaves the item `pendiente` forever with no explanation,
which is exactly A3's honesty obligation inverted.

**What is deliberately NOT caught:** an unnamed exception. A `KeyError` in this
code is a bug, and swallowing it into `no_disponible` would report an outage the
operator would then go looking for in a healthy dependency. It propagates, the
transaction rolls back, and the item is still `pendiente` — the state it never
left (see `buzon.reclamar_pendiente`).

**A reranker that is not up is NOT an item failure.** A3: "a GPU that is not
currently available is the normal case, not an outage: items stay `pendiente`."
So the reranker is a REQUIRED argument here rather than something this function
builds and rescues. A caller that cannot build one processes no items at all,
which is the queue absorbing the GPU's intermittence — the entire point of the
amendment. Fail-closed still holds: no CPU fallback, no smaller model, and a
SYNTHETIC ranker is refused outright below rather than quietly ordering a real
answer.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Callable, ContextManager, Sequence

from sqlalchemy.orm import Session

from app.domains.conocimiento import buzon, repository, routing, service
from app.domains.conocimiento.embed_sidecar import SidecarNoDisponible
from app.domains.conocimiento.generacion import (
    ESTADO_GENERACION_FALLIDA,
    ESTADO_NO_DISPONIBLE,
    ESTADO_REDIRECCION,
    Generador,
    GeneracionNoDisponible,
    PresupuestoAgotado,
    assert_generador_publicable,
    generar_respuesta,
)
from app.domains.conocimiento.proveedores import PresupuestoDeItem
from app.domains.conocimiento.recuperacion.reranker import RerankerNoDisponible
from app.domains.conocimiento.schemas import Redireccion, RespuestaConocimiento

#: How many units reach the generator. The serving configuration is `bm25_ce`:
#: BM25 selects the candidate pool and the cross-encoder orders it.
K_SERVING = 10

#: Build one adapter per item, with THAT item's budget. `conectar_puente`'s
#: docstring is explicit that a long-lived adapter sharing one `PresupuestoDeItem`
#: would bound the wrong item, and that an unclosed pool per item is a descriptor
#: leak — so the factory returns a context manager and this module always uses it
#: as one.
CrearGenerador = Callable[[PresupuestoDeItem], ContextManager[Generador]]


class RerankerSintetico(RuntimeError):
    """A stand-in ranker reached the serving path. Refused, never used.

    Not an item state: this is a wiring fault, the same class as the synthetic
    GENERATOR that `assert_generador_publicable` refuses. Failing an item would
    say "your question could not be answered" about a deployment that answered it
    with a placeholder.
    """


def procesar_uno(
    db: Session,
    *,
    corpus_sha: str,
    embedder: Any,
    centroides: routing.Centroides,
    parametros: routing.ParametrosRuta,
    reranker: Any,
    crear_generador: CrearGenerador,
    k: int = K_SERVING,
    item_deadline_s: float = 60.0,
    ahora: datetime.datetime | None = None,
) -> Any | None:
    """Process the oldest waiting item, or return `None` when none is waiting.

    The caller owns the transaction: on return the item is written but not
    committed, so a worker that crashes before committing releases the claim and
    leaves the item exactly as it found it.
    """
    assert_generador_publicable_de(reranker)

    item = buzon.reclamar_pendiente(db)
    if item is None:
        return None

    # The budget starts when the item is picked up, monotonic. Everything below
    # is inside it, including retrieval — an item that spends its whole budget in
    # BM25 has still spent it, and discovering that only at the provider call
    # would make the budget a property of the generator rather than of the item.
    presupuesto = PresupuestoDeItem(item_deadline_s)
    pregunta = item.pregunta
    decision_id: uuid.UUID | None = None

    try:
        decision = routing.clasificar(
            pregunta,
            embedder=embedder,
            centroides=centroides,
            parametros=parametros,
        )
    except SidecarNoDisponible as exc:
        # No classification happened, so there is nothing honest to redirect to
        # and `redireccion_parcial` stays absent (`design.md:787`).
        return _terminar(
            db,
            item,
            _no_disponible(str(exc)),
            decision_ruta_id=None,
            ahora=ahora,
        )

    decision_id = repository.registrar_decision_ruta(db, decision)

    if decision.clase in (routing.CLASE_OPERATIONAL, routing.CLASE_GEOESPACIAL):
        # A pure redirect needs neither GPU nor provider. It is terminal here.
        return _terminar(
            db,
            item,
            RespuestaConocimiento(
                estado=ESTADO_REDIRECCION,
                redireccion=Redireccion(
                    superficie=decision.superficie or "",
                    motivo=decision.motivo,
                ),
            ),
            decision_ruta_id=decision_id,
            ahora=ahora,
        )

    parcial = (
        Redireccion(superficie=decision.superficie or "", motivo=decision.motivo)
        if decision.clase == routing.CLASE_MIXTO
        else None
    )

    try:
        presupuesto.exigir_vigente()
        hits = _recuperar(db, corpus_sha, pregunta, k=k, reranker=reranker)
    except PresupuestoAgotado as exc:
        return _terminar(
            db,
            item,
            _fallida(f"presupuesto_item_agotado: {exc}", parcial),
            decision_ruta_id=decision_id,
            ahora=ahora,
        )
    except (
        service.EmbeddingsNoCargadas,
        service.EmbedderMismatch,
        service.EmbedderRequerido,
        service.RerankerRequerido,
        repository.VectorSupportUnavailable,
        RerankerNoDisponible,
        service.CorpusNoServible,
    ) as exc:
        # Retrieval refusals are DEPENDENCY facts, never "no applicable norm".
        # Converting any of them into an abstention would tell a CD member the
        # corpus has nothing for them, which is a false statement about the law
        # (`design.md:711-712`).
        return _terminar(
            db,
            item,
            _no_disponible(f"{type(exc).__name__}: {exc}", parcial),
            decision_ruta_id=decision_id,
            ahora=ahora,
        )

    with crear_generador(presupuesto) as generador:
        assert_generador_publicable(generador)
        try:
            respuesta = generar_respuesta(
                db,
                corpus_sha,
                pregunta,
                hits,
                generador=generador,
                redireccion_parcial=parcial,
            )
        except PresupuestoAgotado as exc:
            # `generar_respuesta` already ends a spent budget in
            # `generacion_fallida`. This is the belt for the paths that reach the
            # budget OUTSIDE its try — the same escape that made a spent budget
            # crash the worker in U6.
            respuesta = _fallida(f"presupuesto_item_agotado: {exc}", parcial)
        except GeneracionNoDisponible as exc:
            # The cost ceilings (`CuotaAgotada`, `TechoDeGasto`,
            # `TechoNoConfigurado`, `VentanaNoConfigurada`) are subclasses of this
            # and are raised by the meter BEFORE an attempt is issued, which is
            # outside anything `generar_respuesta` wraps.
            respuesta = _no_disponible(f"{type(exc).__name__}: {exc}", parcial)

    return _terminar(db, item, respuesta, decision_ruta_id=decision_id, ahora=ahora)


def assert_generador_publicable_de(reranker: Any) -> None:
    """Refuse a synthetic ranker on the serving path.

    The eval harness already refuses to PUBLISH a figure produced by a stand-in
    ranker (`report._gate_sintetico`). Serving an ANSWER ordered by one is the
    same lie with a smaller audience and no report to catch it.
    """
    if getattr(reranker, "sintetico", False):
        raise RerankerSintetico(
            f"{getattr(reranker, 'model_id', reranker)!r} is a synthetic ranker. "
            "The ratified serving configuration is BM25 + cross-encoder and the "
            "design authorises no fallback: no CPU rerank, no smaller model, and "
            "certainly not a deterministic stand-in ordering a real legal answer."
        )


def _recuperar(
    db: Session,
    corpus_sha: str,
    pregunta: str,
    *,
    k: int,
    reranker: Any,
) -> Sequence[Any]:
    """B50 retrieval, and the synthetic-embeddings refusal that precedes it."""
    procedencia = service.procedencia_embeddings(db, corpus_sha)
    if procedencia is not None and procedencia.sintetico:
        raise service.CorpusNoServible(
            f"snapshot {corpus_sha} carries SYNTHETIC embeddings. Serving from "
            "them would answer a legal question from vectors nobody trained "
            "(task 7.6, `design.md:751-752`)."
        )
    resultado = service.recuperar(
        db,
        corpus_sha,
        pregunta,
        modo="bm25_ce",
        k=k,
        reranker=reranker,
    )
    return resultado.hits


def _no_disponible(motivo: str, parcial: Redireccion | None = None) -> RespuestaConocimiento:
    return RespuestaConocimiento(
        estado=ESTADO_NO_DISPONIBLE,
        motivo=motivo,
        redireccion_parcial=parcial,
    )


def _fallida(motivo: str, parcial: Redireccion | None = None) -> RespuestaConocimiento:
    return RespuestaConocimiento(
        estado=ESTADO_GENERACION_FALLIDA,
        motivo=motivo,
        redireccion_parcial=parcial,
    )


def _terminar(
    db: Session,
    item: Any,
    respuesta: RespuestaConocimiento,
    *,
    decision_ruta_id: uuid.UUID | None,
    ahora: datetime.datetime | None,
) -> Any:
    return buzon.persistir_resultado(
        db,
        item,
        respuesta,
        decision_ruta_id=decision_ruta_id,
        ahora=ahora,
    )
