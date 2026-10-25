#!/usr/bin/env python3
"""The mailbox's worker process: the cartero the queue did not have (U7).

    python scripts/rag_worker.py \\
        --database-url postgresql://consorcio:consorcio_dev@localhost:5432/consorcio

Amendment A3 moved every GPU-bound and hosted call off the request path and into
`app/domains/conocimiento/trabajador.procesar_uno`. Nothing called it: no loop,
no CLI, no scheduled task. `POST /preguntas` wrote `pendiente` rows that nothing
would ever pick up, `GET /estado` would have reported a permanently delayed
worker, and the honest reading of the shipped surface was a mailbox with no
postman. This script is that postman, and nothing else — every rule about how an
item is processed lives in `trabajador.py` and is not repeated here.

**Shutdown is trivial, and that is a property of the claim rather than of this
loop.** `buzon.reclamar_pendiente` never commits an intermediate state: the item
is held by a row lock inside the worker's own transaction and is still
`pendiente` the whole time. So a SIGTERM mid-item does not need to finish the
item, hand it off, or mark it anywhere — the transaction is abandoned, Postgres
releases the lock, and the item is exactly as it was found. Aborting costs the
work already spent on that item and loses nothing else. The signal handler
therefore only sets a flag, and the flag is read between items and while
sleeping; there is no drain phase to get wrong.

**What stops the worker rather than failing an item.** Three deployment facts —
a synthetic reranker, an unverified provider terms record, a provider adapter
that cannot be built — are refused by `procesar_uno` BEFORE it claims anything.
They are identical for every item in the queue, so failing an item on them would
tell a CD member their question could not be answered about a box that never
tried. The loop logs the cause and keeps polling: the items stay `pendiente`,
`GET /estado` shows them ageing, and flipping the terms record back or fixing the
credential resumes processing with nothing lost.

**A crash still kills the process — but it no longer wedges the queue (audit
RAG-5).** An unnamed exception propagates, `systemd` restarts the worker, and
the claim re-takes the SAME oldest item. Unbounded, that is a crash-loop every
~10 s with zero progress, and the only signal is `worker_demorado`. The
`ContadorDeCaidas` below caps the blast radius without softening anything: each
crash is counted against its item in a committed transaction AFTER the rollback,
and at `buzon.MAX_CAIDAS_WORKER` the item is terminalized to
`generacion_fallida` with a `motivo` naming the count. The traceback, the exit
code and the restart all still happen — a dead-lettered item is a capped blast
radius around a bug that is still live.

**Which interpreter.** The reranker is `bge-reranker-v2-m3` on CUDA, which needs
`requirements-rag.txt` — deliberately outside the app venv (D8). So this runs
under `venv-rag`:

    venv-rag/bin/python scripts/rag_worker.py --database-url …

Under the default `venv` it exits **2** naming `requirements-rag.txt` instead of
dying on an ImportError traceback. `--reranker-device cpu` is NOT offered: the
design authorises no CPU fallback and no smaller model, and a 98.9 s-per-query
rerank is an outage that answers rather than a degraded mode.

Exit codes: 0 a clean stop on a signal · 1 the run was refused before any item
was processed (unverified terms, unbuildable provider, no reranker) · 2 usage,
INCLUDING "this interpreter has no torch".
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Callable, ContextManager

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

# rag_consulta.usuario_id FKs users.id; without this mapper SQLAlchemy
# raises NoReferencedTableError on flush in the worker process.
from app.auth.models import User as _User  # noqa: E402, F401
from app.config import settings  # noqa: E402
from app.domains.conocimiento import buzon, routing, trabajador  # noqa: E402
from app.domains.conocimiento.embed_sidecar import (  # noqa: E402
    SidecarNoDisponible,
    conectar_sidecar,
)
from app.domains.conocimiento.models import ESTADO_PENDIENTE  # noqa: E402
from app.domains.conocimiento.eval.router import cargar_router_set  # noqa: E402
from app.domains.conocimiento.proveedores import (  # noqa: E402
    PresupuestoDeItem,
    ProveedorMalConfigurado,
    TerminosNoVerificados,
    conectar_puente,
)
from app.domains.conocimiento.recuperacion.reranker import (  # noqa: E402
    RerankerNoDisponible,
)
from app.domains.conocimiento.repository import corpus_activo  # noqa: E402

logger = logging.getLogger("conocimiento.worker")

#: Refused before any item is claimed, and therefore before any item can be
#: blamed for them. All four are deployment facts.
REFUSALES_DE_ARRANQUE = (
    TerminosNoVerificados,
    ProveedorMalConfigurado,
    RerankerNoDisponible,
    trabajador.RerankerSintetico,
)


class Parada:
    """A cooperative stop flag, set by SIGTERM/SIGINT and read between items.

    A `threading.Event` rather than a bare bool so the empty-queue sleep can WAIT
    on it: a worker polling every 5 s must not take up to 5 s to notice a
    SIGTERM, and `Event.wait(timeout)` returns the moment the flag is set.
    """

    def __init__(self) -> None:
        self._evento = threading.Event()
        self.senal: int | None = None

    def pedida(self) -> bool:
        return self._evento.is_set()

    def pedir(self, senal: int | None = None) -> None:
        self.senal = senal
        self._evento.set()

    def dormir(self, segundos: float) -> None:
        """Sleep, but wake immediately on a stop request."""
        self._evento.wait(segundos)


def instalar_senales(parada: Parada) -> None:
    """SIGTERM and SIGINT set the flag. They do NOT abort the item in flight.

    Aborting mid-item would be safe — see the module docstring — but it would
    also throw away an item that may be one provider call from being answered,
    for no gain: the item's own budget already bounds how long the loop can take
    to reach the flag.
    """
    for senal in (signal.SIGTERM, signal.SIGINT):
        signal.signal(senal, lambda numero, _marco: parada.pedir(numero))


class ContadorDeCaidas:
    """The dead-letter accountant: one integer per item that survives the crash.

    Why it exists (audit RAG-5): the claim deliberately writes no intermediate
    state, so a crash rolls back EVERYTHING — including any count kept in the
    crashed transaction — and `Restart=always` walks the worker straight back
    into the SAME oldest item, forever, with `worker_demorado` as the only
    symptom. This object breaks that loop without softening the crash: the bug
    still propagates, the process still dies, and what survives is
    `rag_consulta.caidas_worker`, incremented from a transaction COMMITTED
    after the rollback.

    Two hooks, one seam. `al_reclamar` records WHICH item the dying transaction
    claimed — in memory, the only place that survives the rollback, which is
    why `procesar_uno` exposes it. `al_caer` spends the record: one committed
    transaction that counts the crash or, at `buzon.MAX_CAIDAS_WORKER`,
    terminalizes the item to `generacion_fallida` through the normal
    `persistir_resultado`. Every crash logs the item id and the cause; the
    terminalization logs CRITICAL, because a dead-lettered item means a bug is
    STILL live and only its blast radius was capped.

    Never raises: an accountant that masked the bug it counts would be worse
    than no accountant. Its own failures are logged CRITICAL and swallowed —
    the original exception is the one that must reach journald.
    """

    def __init__(self, session_factory: Callable[[], Session], *, max_caidas: int | None = None):
        self._session_factory = session_factory
        self._max_caidas = buzon.MAX_CAIDAS_WORKER if max_caidas is None else max_caidas
        self._reclamado: list[uuid.UUID] = []

    def nueva_vuelta(self) -> None:
        """Called at the top of each `procesar`: the previous iteration's claim
        is spent history. A crash with an empty record is a crash that happened
        BEFORE any claim (a bug in the claim itself) and has no item to blame."""
        self._reclamado.clear()

    def al_reclamar(self, item: Any) -> None:
        self._reclamado.append(item.id)

    def al_caer(self, causa: BaseException) -> None:
        if not self._reclamado:
            return
        item_id = self._reclamado.pop()
        sesion = self._session_factory()
        try:
            item = buzon.registrar_caida(sesion, item_id, causa=causa, max_caidas=self._max_caidas)
            # Read BEFORE the commit: the factory expires instances on commit,
            # and this object must not depend on the caller's sessionmaker
            # configuration to be able to say what it just wrote.
            resumen = None if item is None else (item.estado, item.caidas_worker)
            sesion.commit()
        except Exception:
            sesion.rollback()
            logger.critical(
                "conocimiento.worker.contador_de_caidas_fallo item=%s — no se pudo "
                "registrar la caída; el bug original se mantiene alto",
                item_id,
                exc_info=True,
            )
            return
        finally:
            sesion.close()
        if resumen is None:
            logger.error(
                "conocimiento.worker.caida_no_contabilizada item=%s causa=%s: %s — el "
                "ítem ya no es un pendiente libre (otro worker lo tomó o terminó); "
                "no hay nada que contar",
                item_id,
                type(causa).__name__,
                causa,
            )
        elif resumen[0] != ESTADO_PENDIENTE:
            logger.critical(
                "conocimiento.worker.item_envenenado id=%s estado=%s caidas=%d/%d "
                "causa=%s: %s — el ítem se aparta de la cola como generacion_fallida; "
                "EL BUG SIGUE VIVO, el traceback de esta caída es la pista",
                item_id,
                resumen[0],
                resumen[1],
                self._max_caidas,
                type(causa).__name__,
                causa,
            )
        else:
            logger.error(
                "conocimiento.worker.caida id=%s caidas=%d/%d causa=%s: %s — el "
                "worker muere igual (los bugs son ruidosos); el ítem vuelve a "
                "pendiente",
                item_id,
                resumen[1],
                self._max_caidas,
                type(causa).__name__,
                causa,
            )


def bucle(
    session_factory: Callable[[], Session],
    procesar: Callable[[Session], Any],
    *,
    parada: Parada,
    intervalo_s: float,
    max_items: int = 0,
    registrar: Callable[[str, Any], None] | None = None,
    al_caer: Callable[[BaseException], None] | None = None,
) -> int:
    """Poll, process, commit, repeat until asked to stop. Returns items processed.

    ONE transaction per item, opened here and owned here: `procesar_uno`
    deliberately does not commit, so that a worker that dies mid-item releases
    its claim and leaves the item exactly as it found it. Committing per item and
    not per batch is the same property at the other end — an item that finished
    is durable even if the next one crashes the process.

    A `procesar` that RAISES is the interesting case and it is handled in two
    ways, because there are two kinds of exception here and treating them alike
    is how a worker becomes useless:

    * a deployment refusal (`REFUSALES_DE_ARRANQUE`) is logged with its cause and
      the loop keeps polling, because the ITEMS are fine and the operator can fix
      the deployment without losing them;
    * anything else propagates. An unnamed exception is a bug, and a loop that
      swallows bugs turns a crash into a worker that silently processes nothing
      while reporting itself alive.

    In both cases the transaction is rolled back first, so the claimed item goes
    back to `pendiente` rather than being held by a poisoned session.

    The propagation path carries ONE extra step before the `raise` (audit
    RAG-5): `al_caer`, when given, is called with the exception so the crash
    accountant can spend a committed transaction counting the crash against
    the item the dying run had claimed — and, at `buzon.MAX_CAIDAS_WORKER`,
    dead-lettering it. Without that count, `Restart=always` reclaims the SAME
    oldest item every ~10 s forever and the queue never moves again. The
    propagation itself is untouched: the traceback still hits journald, the
    process still exits non-zero, and the accountant failing must never mask
    the bug it is counting.
    """
    procesados = 0
    while not parada.pedida():
        sesion = session_factory()
        try:
            item = procesar(sesion)
            if item is None:
                sesion.rollback()
                sesion.close()
                parada.dormir(intervalo_s)
                continue
            sesion.commit()
            procesados += 1
            if registrar is not None:
                registrar("procesado", item)
            if max_items and procesados >= max_items:
                sesion.close()
                break
        except REFUSALES_DE_ARRANQUE as refusal:
            sesion.rollback()
            sesion.close()
            if registrar is not None:
                registrar("refusal", refusal)
            logger.error(
                "conocimiento.worker.refusal tipo=%s causa=%s — los ítems quedan "
                "pendientes; se reintenta en %.1fs",
                type(refusal).__name__,
                refusal,
                intervalo_s,
            )
            parada.dormir(intervalo_s)
            continue
        except BaseException as exc:  # noqa: BLE001 — the point is to die loudly
            sesion.rollback()
            sesion.close()
            if al_caer is not None:
                try:
                    al_caer(exc)
                except Exception:  # noqa: BLE001 — never mask the bug being counted
                    logger.critical(
                        "conocimiento.worker.contador_de_caidas_fallo — el bug "
                        "original se mantiene alto",
                        exc_info=True,
                    )
            raise
        sesion.close()
    return procesados


# ---------------------------------------------------------------------------
# Wiring — the real dependencies, built once
# ---------------------------------------------------------------------------


def construir_reranker() -> Any:
    """The real cross-encoder. No fallback, by design."""
    from app.domains.conocimiento.recuperacion.reranker import BGEReranker

    return BGEReranker()


def construir_router(embedder: Any) -> tuple[routing.Centroides, routing.ParametrosRuta]:
    """Centroids and thresholds fitted on the RATIFIED labeled set, at boot.

    The full-set fit — `centroides_shipped`/`parametros_shipped` in LOOCV's
    vocabulary — because that is what serving uses; the held-out folds are a
    MEASUREMENT and belong to `make rag-eval`, not to a worker's startup.

    Fitted at boot rather than read from a checked-in file because the centroids
    are vectors in the CURRENT embedder's space: a file would be a set of numbers
    with no way to prove which weights produced them, and a sidecar restarted
    onto a different model would silently classify against directions from
    another space. `cargar_router_set` refuses an unratified set, so a worker
    cannot boot against thresholds nobody reviewed.
    """
    senales = routing.senales_desde(cargar_router_set(), embedder)
    centroides = routing.centroides_desde(senales)
    return centroides, routing.seleccionar_parametros(senales, centroides)


def fabrica_de_generador(url: str) -> Callable[[PresupuestoDeItem], ContextManager[Any]]:
    """One adapter per item, bound to THAT item's budget, closed by the caller."""

    def _crear(presupuesto: PresupuestoDeItem) -> ContextManager[Any]:
        return conectar_puente(
            url,
            modelo=settings.conocimiento_modelo,
            pool=settings.conocimiento_pool,
            api_key=settings.conocimiento_proveedor_api_key,
            timeout_s=settings.conocimiento_provider_timeout_s,
            presupuesto=presupuesto,
        )

    return _crear


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Process queued conocimiento questions until stopped.",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", ""),
        help="postgresql://… (defaults to $DATABASE_URL)",
    )
    parser.add_argument(
        "--corpus-sha",
        default="",
        help=(
            "the snapshot to answer from. Defaults to the ACTIVE one; passing it "
            "explicitly pins the worker to a revision across an ingestion."
        ),
    )
    parser.add_argument(
        "--intervalo-s",
        type=float,
        default=None,
        help=(
            "seconds to sleep when the queue is empty "
            f"(default: conocimiento_worker_poll_s = {settings.conocimiento_worker_poll_s})"
        ),
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=0,
        help=(
            "stop after N items. 0 (the default) runs until a signal. Exists for "
            "a supervised one-shot drain, never as a substitute for the loop."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = build_parser().parse_args(argv)
    if not args.database_url:
        print("error: --database-url or $DATABASE_URL is required", file=sys.stderr)
        return 2

    parada = Parada()
    instalar_senales(parada)
    intervalo = (
        settings.conocimiento_worker_poll_s if args.intervalo_s is None else args.intervalo_s
    )

    try:
        reranker = construir_reranker()
    except RerankerNoDisponible as refusal:
        # Its own exit code path: "there is no GPU here" is a usage fact when it
        # means torch is missing, and a refusal when it means CUDA is absent.
        # Both are refusals to START, never a CPU rerank.
        print(f"\nWORKER NOT STARTED — no reranker.\n{refusal}", file=sys.stderr)
        return 2 if "not installed" in str(refusal) else 1

    engine = create_engine(args.database_url)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    procesados = 0
    try:
        with conectar_sidecar(
            settings.conocimiento_embed_url,
            timeout=settings.conocimiento_embed_timeout_s,
        ) as embedder:
            # The terms gate at STARTUP, so a worker that is not authorised to
            # send anything out of the box says so before it embeds 49 questions
            # and loads a 2 GB reranker's weights into a GPU. `procesar_uno`
            # checks it again per poll: this one is a boot failure, that one is
            # the guarantee for a record flipped while the worker is running.
            trabajador.verificar_terminos_vigentes()
            centroides, parametros = construir_router(embedder)

            corpus_sha = args.corpus_sha
            if not corpus_sha:
                with session_factory() as sesion:
                    corpus_sha = corpus_activo(sesion) or ""
            if not corpus_sha:
                print(
                    "error: no active corpus snapshot. Ingest one first "
                    "(scripts/rag_ingest.py) or pass --corpus-sha.",
                    file=sys.stderr,
                )
                return 1

            crear_generador = fabrica_de_generador(settings.conocimiento_proveedor_url)
            # The dead-letter accountant (audit RAG-5): sees the claim through
            # `al_reclamar`, counts the crash through `al_caer`, and at
            # `buzon.MAX_CAIDAS_WORKER` terminalizes the poison item so the
            # restart loop the systemd unit below implies cannot wedge the
            # queue on one item forever.
            contador = ContadorDeCaidas(session_factory)
            logger.info(
                "conocimiento.worker.arranque corpus_sha=%s embedder=%s reranker=%s intervalo=%.1fs",
                corpus_sha,
                embedder.model_id,
                getattr(reranker, "model_id", reranker),
                intervalo,
            )

            def _procesar(sesion: Session) -> Any:
                contador.nueva_vuelta()
                return trabajador.procesar_uno(
                    sesion,
                    corpus_sha=corpus_sha,
                    embedder=embedder,
                    centroides=centroides,
                    parametros=parametros,
                    reranker=reranker,
                    crear_generador=crear_generador,
                    item_deadline_s=settings.conocimiento_item_deadline_s,
                    al_reclamar=contador.al_reclamar,
                )

            def _registrar(evento: str, dato: Any) -> None:
                if evento == "procesado":
                    logger.info("conocimiento.worker.item id=%s estado=%s", dato.id, dato.estado)

            procesados = bucle(
                session_factory,
                _procesar,
                parada=parada,
                intervalo_s=intervalo,
                max_items=args.max_items,
                registrar=_registrar,
                al_caer=contador.al_caer,
            )
    except (SidecarNoDisponible, *REFUSALES_DE_ARRANQUE) as refusal:
        print(f"\nWORKER NOT STARTED — {type(refusal).__name__}.\n{refusal}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    logger.info(
        "conocimiento.worker.parada senal=%s items=%d",
        parada.senal,
        procesados,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ContadorDeCaidas",
    "Parada",
    "bucle",
    "construir_reranker",
    "construir_router",
    "fabrica_de_generador",
    "instalar_senales",
    "main",
]
