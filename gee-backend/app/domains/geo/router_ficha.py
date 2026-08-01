"""Dedicated public router for the ficha territorial (design §2).

Why a router of its own instead of one more route on ``router_analysis``:

* the rate limiter must throttle THIS endpoint and nothing else. Hanging
  ``dependencies=[enforce_ficha_rate_limit]`` on the shared analysis router
  would throttle ``/zonal-stats`` and every other operator analysis route for
  any IP that clicked parcels on the public map (JDB-003);
* this is the ONLY route under ``/api/v2/geo`` without an operator dependency.
  Isolating it makes that fact structural — and a route-table test asserts every
  sibling still carries its auth dependency.

Enforcement order (design §2.5), implemented as ordered router dependencies:

    feature gate (503) → Content-Length / stream guard (413) → rate limit (429)
    → schema validation (422) → [service] assert_within_caps (422) → audit
    committed → semaphore (503) → compute

The handler is sync ``def`` on purpose: Starlette offloads it to the threadpool
so rasterio never blocks the loop. The guard dependencies are ``async def``,
which FastAPI allows on a sync handler.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Request
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session
from starlette.requests import ClientDisconnect

from app.config import settings
from app.core.logging import get_logger
from app.core.rate_limit import DistributedRateLimiter
from app.db.session import get_db
from app.domains.geo import ficha_errors, ficha_service
from app.domains.geo.schemas_ficha import FichaOverlayResponse, FichaRequest, FichaResponse

logger = get_logger(__name__)

router = APIRouter(tags=["Ficha Territorial"])

_ficha_adapter: TypeAdapter[Any] = TypeAdapter(FichaRequest)

# ── OpenAPI: the request body is described by hand, so its $refs are ours ──
# The body is validated inside ``parse_ficha_body`` instead of through a
# declared parameter (so the §2.6 codes survive), which means FastAPI never
# sees the request models and never registers them. Pydantic's default
# ``json_schema()`` emits ``#/$defs/...`` refs plus a sibling ``$defs`` block —
# legal JSON Schema, but ``openapi_extra`` splices ONLY the schema into the
# operation, so ``$defs`` is dropped and every ref (including the four in the
# discriminator ``mapping``) dangles. Generators then fail or silently emit an
# untyped body — and A4's author reads exactly this contract (F3).
#
# Fix: point the refs at ``#/components/schemas/{model}`` and hoist the
# definitions there via ``install_ficha_openapi_schemas``.
_ficha_json_schema: dict[str, Any] = _ficha_adapter.json_schema(
    ref_template="#/components/schemas/{model}"
)
_FICHA_DEFS: dict[str, Any] = _ficha_json_schema.pop("$defs", {})


def install_ficha_openapi_schemas(app: FastAPI) -> None:
    """Hoist the ficha request models into ``components.schemas``.

    Called by ``app.main`` and by any test app that mounts this router, the same
    way ``install_ficha_error_handler`` is. Wrapping ``app.openapi`` is the
    standard recipe: only an app owns ``components``, and FastAPI builds the
    document lazily. ``setdefault`` keeps it idempotent — FastAPI caches the
    result in ``app.openapi_schema``, so the wrapper may see an
    already-hoisted document on later calls.
    """
    generar_original = app.openapi

    def openapi_con_ficha() -> dict[str, Any]:
        esquema = generar_original()
        componentes = esquema.setdefault("components", {}).setdefault("schemas", {})
        for nombre, definicion in _FICHA_DEFS.items():
            componentes.setdefault(nombre, definicion)
        return esquema

    app.openapi = openapi_con_ficha  # type: ignore[method-assign]


# Cost per ``tipo`` — a drawn polygon, a canal buffer and a catchment all cost
# the same raster work as each other and ~5x a parcel click (design §2.2).
COSTO_POR_TIPO: dict[str, int] = {
    "parcela": 1,
    "poligono": 5,
    "canal_buffer": 5,
    "canal_cuenca": 5,
}

_limiter: DistributedRateLimiter | None = None


def get_ficha_rate_limiter() -> DistributedRateLimiter:
    """Own limiter instance, own Redis key namespace.

    Redis-down policy (design §2.2, explicit): ``DistributedRateLimiter``
    degrades to a per-process in-memory window and logs a warning. It does NOT
    fail open and does NOT fail the request.

    Degraded ceiling, concretely (R4-002): the fallback window is per PROCESS,
    and ``app/server.py`` runs uvicorn with ``workers=2``, so with Redis down
    the real limit is 2 x ``ficha_rate_limit_requests`` = 60 req/min per IP, not
    30 — and it grows linearly with workers and replicas. Accepted because the
    limiter is the THIRD line of defense: the caps and the in-flight semaphore
    are what actually bound cost. Note the semaphore is per-process too, so the
    box-wide compute bound is 2 x ``ficha_max_concurrency`` = 8.
    """
    global _limiter
    if _limiter is None:
        _limiter = DistributedRateLimiter(
            redis_url=settings.redis_url,
            max_requests=settings.ficha_rate_limit_requests,
            window_seconds=settings.ficha_rate_limit_window,
            key_prefix="ratelimit:ficha:",
        )
    return _limiter


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def enforce_ficha_enabled() -> None:
    """503 ``funcionalidad_no_disponible`` while the ficha is switched off (F4).

    FIRST dependency on purpose, so a disabled deployment answers before the
    body is read, before the limiter is consulted, before any audit row is
    written and before a compute slot is taken.

    Why a gate exists at all: ``ficha_service.analizar_zona`` currently returns
    a placeholder — ``area_ha=0.0`` with every dataset ``sin_cobertura``. The
    route is public and advertised in ``/openapi.json``, so with no gate the
    only thing standing between a deployed branch and the UI rendering "0 ha"
    as a measured fact is that nobody clicked. The route stays MOUNTED (the
    contract and its tests are the point of this slice) but inert; A3b flips
    the default once the compute is real.
    """
    if not settings.ficha_enabled:
        raise ficha_errors.funcionalidad_no_disponible("ficha territorial")


async def enforce_body_limit(request: Request) -> None:
    """413 ``cuerpo_excedido`` BEFORE parsing (JDB-007).

    The vertex cap only fires once the whole body is deserialized, so a 50 MB
    "polygon" would be parsed in full before any validator saw it. A declared
    ``Content-Length`` over the cap is rejected outright; a chunked body with no
    ``Content-Length`` is read through a counting guard that aborts at the same
    threshold. The bytes read here are cached on the request, so the limiter and
    the parser below reuse them instead of re-reading a consumed stream.
    """
    maximo = settings.ficha_max_body_bytes
    declarado = request.headers.get("content-length")
    if declarado is not None:
        try:
            if int(declarado) > maximo:
                raise ficha_errors.cuerpo_excedido(maximo)
        except ValueError:
            raise ficha_errors.geometria_invalida("content-length invalido")

    if hasattr(request, "_body"):
        return

    trozos: list[bytes] = []
    leido = 0
    try:
        async for trozo in request.stream():
            leido += len(trozo)
            if leido > maximo:
                raise ficha_errors.cuerpo_excedido(maximo)
            trozos.append(trozo)
    except ClientDisconnect:
        # The peer hung up mid-body. Letting this propagate reached
        # ``generic_exception_handler``, which logs with ``logger.exception``
        # and ships a Sentry event — three ERROR records and a 500 nobody can
        # read, per hit. And this guard runs BEFORE the rate limiter by design,
        # so it was a free, unauthenticated, unthrottled way to flood the error
        # budget: open a request with a large Content-Length, send one chunk,
        # drop the socket, repeat (F1).
        logger.info("Cliente desconectado durante la lectura del cuerpo", leido=leido)
        raise ficha_errors.cliente_desconectado() from None
    request._body = b"".join(trozos)


async def _cuerpo_crudo(request: Request) -> Any:
    try:
        return json.loads(await request.body() or b"null")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


async def enforce_ficha_rate_limit(request: Request) -> None:
    """429 ``limite_de_tasa`` per IP, priced by ``tipo``."""
    if settings.rate_limit_disabled:
        return

    crudo = await _cuerpo_crudo(request)
    tipo = crudo.get("tipo") if isinstance(crudo, dict) else None
    costo = COSTO_POR_TIPO.get(tipo, 1) if isinstance(tipo, str) else 1

    permitido, _restantes, reset = await get_ficha_rate_limiter().check(
        _client_ip(request), cost=costo
    )
    if not permitido:
        raise ficha_errors.limite_de_tasa(max(1, int(reset)))


async def parse_ficha_body(request: Request) -> Any:
    """422 with the §2.6 codes instead of FastAPI's generic envelope.

    Validation runs here rather than through a declared body parameter so an
    unknown ``tipo`` answers ``tipo_desconocido`` and a malformed geometry
    answers ``geometria_invalida`` — both stable machine codes the UI switches
    on. The cheap ``poligono`` validators raise their own ``FichaError`` from
    inside the schema and propagate untouched.
    """
    crudo = await _cuerpo_crudo(request)
    if not isinstance(crudo, dict):
        raise ficha_errors.geometria_invalida("el cuerpo debe ser un objeto JSON")
    tipo = crudo.get("tipo")
    if tipo not in ficha_errors.TIPOS_VALIDOS:
        raise ficha_errors.tipo_desconocido(tipo)
    try:
        return _ficha_adapter.validate_python(crudo)
    except ValidationError as exc:
        primero = exc.errors()[0]
        campo = ".".join(str(parte) for parte in primero.get("loc", ()) if parte != tipo)
        raise ficha_errors.geometria_invalida(f"{campo or 'cuerpo'}: {primero.get('msg', '')}")


# Overlay datasets this slice serves. Slice 1 = soils only (exact PostGIS vector);
# flood_risk / drainage_need raster vectorization is slice 2.
_OVERLAY_DATASETS: tuple[str, ...] = ("suelos",)


async def parse_overlay_body(request: Request) -> tuple[Any, str]:
    """Validate the overlay body: the SAME ficha discriminated union + ``dataset``.

    Mirrors ``parse_ficha_body`` so the §2.6 codes survive (``tipo_desconocido`` /
    ``geometria_invalida``), and adds the ``dataset`` selector: only ``"suelos"``
    is served in this slice, any other value is a clean 422 ``dataset_no_soportado``.
    ``dataset`` is popped before the ficha adapter runs because the request models
    are ``extra="forbid"`` and would otherwise reject the extra key.
    """
    crudo = await _cuerpo_crudo(request)
    if not isinstance(crudo, dict):
        raise ficha_errors.geometria_invalida("el cuerpo debe ser un objeto JSON")
    dataset = crudo.get("dataset")
    if dataset not in _OVERLAY_DATASETS:
        raise ficha_errors.dataset_no_soportado(dataset, _OVERLAY_DATASETS)
    cuerpo_ficha = {clave: valor for clave, valor in crudo.items() if clave != "dataset"}
    tipo = cuerpo_ficha.get("tipo")
    if tipo not in ficha_errors.TIPOS_VALIDOS:
        raise ficha_errors.tipo_desconocido(tipo)
    try:
        payload = _ficha_adapter.validate_python(cuerpo_ficha)
    except ValidationError as exc:
        primero = exc.errors()[0]
        campo = ".".join(str(parte) for parte in primero.get("loc", ()) if parte != tipo)
        raise ficha_errors.geometria_invalida(f"{campo or 'cuerpo'}: {primero.get('msg', '')}")
    return payload, dataset


@router.post(
    "/analisis-zona/overlay",
    response_model=FichaOverlayResponse,
    summary="Analisis clipado a la zona para pintar en el mapa (publico)",
    dependencies=[
        Depends(enforce_ficha_enabled),
        Depends(enforce_body_limit),
        Depends(enforce_ficha_rate_limit),
    ],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "description": (
                            "El mismo cuerpo que /analisis-zona mas un selector "
                            "`dataset` (por ahora solo `suelos`)."
                        ),
                        "required": ["dataset"],
                        "properties": {
                            "dataset": {"type": "string", "enum": list(_OVERLAY_DATASETS)}
                        },
                        "allOf": [_ficha_json_schema],
                    }
                }
            },
        }
    },
)
def overlay_zona(
    request: Request,
    parsed: tuple[Any, str] = Depends(parse_overlay_body),
    db: Session = Depends(get_db),
) -> FichaOverlayResponse:
    """Public, opt-in. Reuses the ficha dependency chain and geometry resolvers."""
    payload, dataset = parsed
    return ficha_service.overlay_zona(db, payload, dataset=dataset, client_ip=_client_ip(request))


@router.post(
    "/analisis-zona",
    response_model=FichaResponse,
    summary="Ficha territorial integrada de una zona (publico)",
    dependencies=[
        Depends(enforce_ficha_enabled),
        Depends(enforce_body_limit),
        Depends(enforce_ficha_rate_limit),
    ],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": _ficha_json_schema}},
        }
    },
)
def analizar_zona(
    request: Request,
    payload: Any = Depends(parse_ficha_body),
    db: Session = Depends(get_db),
) -> FichaResponse:
    """Public. No auth dependency — by design, and asserted by a route-table test."""
    return ficha_service.analizar_zona(db, payload, client_ip=_client_ip(request))
