"""Error contract for the ficha territorial endpoint (design §2.6, JD-A-006).

Every ficha failure answers with a FLAT body::

    {"detail": "<mensaje humano, en castellano>", "codigo": "<codigo estable>", ...}

Neither of the two handlers the app already owns produces that shape:
``AppException`` nests everything under ``{"error": {...}}`` and FastAPI's
``HTTPException`` would nest the extras under ``detail``. A dedicated leaf
exception plus one handler is therefore the cheapest way to honour the contract
WITHOUT changing the response shape of any existing route.

The module is a leaf on purpose (no service, no router, no shapely import) so
both the router and the service can raise from it without a cycle.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger(__name__)

TIPOS_VALIDOS = ("parcela", "poligono", "canal_buffer", "canal_cuenca")

# 5xx codes that describe a state somebody CHOSE, not something that broke.
# Logged at WARNING so a switched-off deployment does not emit an ERROR per
# public request (the gate runs before the rate limiter). ``sobrecarga``,
# ``dataset_no_cargado``, ``raster_ilegible`` and ``base_de_datos_no_disponible``
# stay ERROR on purpose: those are real capacity / installation / infrastructure
# faults an operator has to act on. ``analisis_timeout`` joins the WARNING set:
# the per-request statement_timeout is the DESIGN's protective bound on a public
# endpoint, so an abusive polygon tripping it is an expected outcome, not a fault
# — logging it at ERROR would just hand that caller a Sentry amplifier.
_ESTADOS_DELIBERADOS = frozenset({"funcionalidad_no_disponible", "analisis_timeout"})


class FichaError(Exception):
    """One row of the §2.6 error table."""

    def __init__(
        self,
        *,
        status_code: int,
        codigo: str,
        detail: str,
        retry_after: int | None = None,
        **extra: Any,
    ) -> None:
        self.status_code = status_code
        self.codigo = codigo
        self.detail = detail
        self.retry_after = retry_after
        self.extra = extra
        super().__init__(detail)

    def payload(self) -> dict[str, Any]:
        body: dict[str, Any] = {"detail": self.detail, "codigo": self.codigo}
        if self.retry_after is not None:
            body["retry_after"] = self.retry_after
        body.update(self.extra)
        return body


def parcela_no_encontrada(nomenclatura: str) -> FichaError:
    return FichaError(
        status_code=404,
        codigo="parcela_no_encontrada",
        detail=f"No existe una parcela con nomenclatura {nomenclatura}",
        nomenclatura=nomenclatura,
    )


def canal_no_encontrado(canal_id: int) -> FichaError:
    return FichaError(
        status_code=404,
        codigo="canal_no_encontrado",
        detail=f"No existe un canal con id {canal_id}",
        canal_id=canal_id,
    )


def variante_no_disponible(canal_id: int, disponibles: list[str]) -> FichaError:
    return FichaError(
        status_code=409,
        codigo="variante_no_disponible",
        detail="La variante de cuenca solicitada no esta precalculada para este canal",
        canal_id=canal_id,
        variantes_disponibles=disponibles,
    )


def cuerpo_excedido(max_bytes: int) -> FichaError:
    return FichaError(
        status_code=413,
        codigo="cuerpo_excedido",
        detail=f"El cuerpo del pedido supera el maximo de {max_bytes} bytes",
        max_bytes=max_bytes,
    )


def cliente_desconectado() -> FichaError:
    """400 when the peer vanished mid-body (F1).

    Raised by the streaming half of the body guard when Starlette reports
    ``http.disconnect`` before the body finished arriving. There is nobody left
    to read the response, so this exists only to unwind the request WITHOUT the
    generic 500 path: an unhandled ``ClientDisconnect`` reaches
    ``generic_exception_handler``, which calls ``logger.exception`` and ships a
    Sentry event. That turned a free, unauthenticated, pre-rate-limit action —
    the guard runs BEFORE the limiter by design — into an error-log amplifier.
    """
    return FichaError(
        status_code=400,
        codigo="cliente_desconectado",
        detail="El cliente corto la conexion antes de terminar de enviar el cuerpo",
    )


def funcionalidad_no_disponible(funcionalidad: str) -> FichaError:
    """503 when the route is mounted but switched off (F4).

    Its own codigo rather than ``dataset_no_cargado`` so the UI can tell "this
    deployment has not enabled the ficha yet" apart from "a raster is missing",
    which is an operable, install-time problem with a different remedy.
    """
    return FichaError(
        status_code=503,
        codigo="funcionalidad_no_disponible",
        detail=f"La funcionalidad {funcionalidad} no esta habilitada en esta instalacion",
        funcionalidad=funcionalidad,
    )


def tipo_desconocido(recibido: Any) -> FichaError:
    return FichaError(
        status_code=422,
        codigo="tipo_desconocido",
        detail=f"Tipo de analisis desconocido: {recibido!r}",
        tipos_validos=list(TIPOS_VALIDOS),
    )


def geometria_invalida(motivo: str) -> FichaError:
    return FichaError(
        status_code=422,
        codigo="geometria_invalida",
        detail="La geometria enviada no es utilizable",
        motivo=motivo,
    )


def cap_excedido(cap: str, limite: float, valor: float) -> FichaError:
    return FichaError(
        status_code=422,
        codigo="cap_excedido",
        detail=f"Se supero el limite de {cap}: {valor} > {limite}",
        cap=cap,
        limite=limite,
        valor=valor,
    )


def limite_de_tasa(retry_after: int) -> FichaError:
    return FichaError(
        status_code=429,
        codigo="limite_de_tasa",
        detail="Demasiados pedidos. Reintente en unos segundos.",
        retry_after=retry_after,
    )


def dataset_no_cargado(dataset: str) -> FichaError:
    return FichaError(
        status_code=503,
        codigo="dataset_no_cargado",
        detail=f"El dataset {dataset} no esta cargado en esta instalacion",
        dataset=dataset,
    )


def raster_ilegible(dataset: str) -> FichaError:
    return FichaError(
        status_code=503,
        codigo="raster_ilegible",
        detail=f"No se pudo leer el raster de {dataset}",
        dataset=dataset,
    )


def sobrecarga(retry_after: int = 2) -> FichaError:
    return FichaError(
        status_code=503,
        codigo="sobrecarga",
        detail="El servicio esta procesando el maximo de analisis simultaneos",
        retry_after=retry_after,
    )


def analisis_timeout(retry_after: int = 2) -> FichaError:
    """503 when this request's LOCAL statement_timeout fired (SQLSTATE 57014).

    The ficha sets a transaction-local ``statement_timeout`` per request
    (``ficha_service._aplicar_statement_timeout``); a caller-drawn polygon too
    expensive to intersect trips it, PostgreSQL cancels the query
    (psycopg2 ``QueryCanceled`` → SQLAlchemy ``OperationalError``, pgcode 57014).
    That ceiling is DELIBERATE — the protective bound on a public, unauthenticated
    endpoint — so it is a caller-facing "try a smaller area / retry", not an
    infrastructure fault. Logged at WARNING (see ``_ESTADOS_DELIBERADOS``) so an
    abusive polygon cannot flood Sentry with ERRORs. Distinct ``codigo`` from
    ``sobrecarga`` (which means concurrency saturation, not a per-query timeout).
    """
    return FichaError(
        status_code=503,
        codigo="analisis_timeout",
        detail="El analisis del area supero el tiempo maximo permitido. Reduzca el area o reintente.",
        retry_after=retry_after,
    )


def base_de_datos_no_disponible(retry_after: int = 2) -> FichaError:
    """503 for a DB fault that is NOT the deliberate statement_timeout.

    A dropped connection or a deadlock (any ``DBAPIError`` whose pgcode is not
    57014) is real infrastructure trouble an operator has to see, so unlike
    ``analisis_timeout`` this stays ERROR. It still answers with the flat FichaError
    contract instead of escaping to ``generic_exception_handler`` as a bare 500.
    """
    return FichaError(
        status_code=503,
        codigo="base_de_datos_no_disponible",
        detail=(
            "No se pudo completar el analisis por un problema temporal de la base "
            "de datos. Reintente en unos segundos."
        ),
        retry_after=retry_after,
    )


async def ficha_error_handler(_request: Any, exc: FichaError) -> JSONResponse:
    """Render the flat body and leave ONE structured line per failure (R4-005).

    Without ``codigo`` in the log there is no way to answer the two questions
    that actually get asked in an incident: which validation is rejecting real
    users (422 ``geometria_invalida`` vs ``cap_excedido`` vs ``tipo_desconocido``)
    and whether a 503 is load (``sobrecarga``) or infrastructure
    (``dataset_no_cargado`` / ``raster_ilegible``). 4xx is caller error → WARNING;
    5xx is ours → ERROR. ``logger.error`` (not ``exception``) on purpose: these
    are expected, handled outcomes, so a traceback would be noise.

    ``_ESTADOS_DELIBERADOS`` is the one exception, and it exists for the same
    reason ``cliente_desconectado`` does: the feature gate answers BEFORE the
    rate limiter, so on a deployment with the ficha switched off every public
    request would emit an unthrottled ERROR. A configuration state that an
    operator chose is not a fault, and after the first line it carries no new
    information — WARNING keeps it visible without handing anyone an error-log
    amplifier.
    """
    ruta = getattr(getattr(_request, "url", None), "path", None)
    es_falla = exc.status_code >= 500 and exc.codigo not in _ESTADOS_DELIBERADOS
    registrar = logger.error if es_falla else logger.warning
    registrar(
        "Ficha territorial rechazada",
        codigo=exc.codigo,
        status_code=exc.status_code,
        path=ruta,
    )
    response = JSONResponse(status_code=exc.status_code, content=exc.payload())
    if exc.retry_after is not None:
        response.headers["Retry-After"] = str(exc.retry_after)
    return response


def install_ficha_error_handler(app: FastAPI) -> None:
    """Register the handler. Called by ``app.main`` and by test apps."""
    app.add_exception_handler(FichaError, ficha_error_handler)
