"""HTTP layer for the informe de área — thin, authenticated, rate-limited.

Mounted under ``/api/v2/geo`` by the geo router aggregator. Every route is
behind ``current_active_user`` because an informe is PRIVATE data (S11): the
service enforces creator-or-admin on every read.

The per-user rate limit lives on POST only, like the GEE analysis throttle
(#713): GET status/list are cheap polling reads a UI fires while a report
builds, and throttling them would punish exactly the waiting the design asks
for. The limiter keys by USER, not IP — the route is authenticated and
several operators share an office NAT.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, TypeVar

from fastapi import APIRouter, Depends, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.logging import get_logger
from app.core.middleware import etag_for_body, if_none_match_hits
from app.core.rate_limit import DistributedRateLimiter
from app.db.session import get_db
from app.domains.geo.informe_area import service
from app.domains.geo.informe_area.schemas import (
    InformeAreaCreate,
    InformeAreaListResponse,
    InformeAreaPreviewRequest,
    InformeAreaPreviewResponse,
    InformeAreaResponse,
    respuesta_informe,
)
from app.domains.geo.router_common import _require_operator, cache_bounded_request_body

logger = get_logger(__name__)

router = APIRouter(prefix="/informes-area", tags=["Informe de Área"])
_ModelT = TypeVar("_ModelT", bound=BaseModel)


def _body_openapi(model: type[BaseModel]) -> dict[str, Any]:
    return {
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": model.model_json_schema(),
                }
            },
        }
    }


_limiter: DistributedRateLimiter | None = None


def get_informe_rate_limiter() -> DistributedRateLimiter:
    """Own limiter instance, own Redis key namespace.

    Redis-down policy (same as the ficha and GEE analysis limiters): degrade
    to a per-process in-memory window, warn, never fail open and never fail
    the request. The degraded ceiling is ``workers x requests`` — accepted
    because the limiter is the THIRD cost bound here, after the caps and the
    3-in-progress ceiling, both of which live in the database.
    """
    global _limiter
    if _limiter is None:
        _limiter = DistributedRateLimiter(
            redis_url=settings.redis_url,
            max_requests=settings.informe_area_rate_limit_requests,
            window_seconds=settings.informe_area_rate_limit_window,
            key_prefix="ratelimit:informe_area:",
        )
    return _limiter


def _clave_usuario(usuario: Any) -> str:
    return str(getattr(usuario, "id", "") or "desconocido")


async def enforce_informe_body_limit(request: Request) -> None:
    """413 BEFORE parsing/validating huge JSON bodies (Content-Length and chunked)."""
    maximum = settings.informe_area_max_body_bytes
    await cache_bounded_request_body(
        request,
        maximum=maximum,
        too_large_detail=f"Cuerpo mayor a {maximum} bytes",
        invalid_length_detail="content-length invalido",
        disconnected_detail="Cliente desconectado",
    )


async def _parse_informe_model(request: Request, model_cls: type[_ModelT]) -> _ModelT:
    raw = await request.body()
    try:
        data = json.loads(raw or b"null")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RequestValidationError(
            [{"loc": ("body",), "msg": f"JSON invalido: {exc}", "type": "json_invalid"}]
        ) from exc
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


async def parse_informe_create_body(request: Request) -> InformeAreaCreate:
    """Validate ``InformeAreaCreate`` from the pre-bounded request body."""
    return await _parse_informe_model(request, InformeAreaCreate)


async def parse_informe_preview_body(request: Request) -> InformeAreaPreviewRequest:
    """Validate ``InformeAreaPreviewRequest`` from the pre-bounded request body."""
    return await _parse_informe_model(request, InformeAreaPreviewRequest)


async def enforce_informe_rate_limit(
    request: Request,  # noqa: ARG001 — kept for dependency symmetry
    usuario: Any = Depends(_require_operator()),
) -> None:
    """429 per USER on informe creation (S5 “rate limit en la creación”)."""
    if settings.rate_limit_disabled:
        return
    permitido, _restantes, reset = await get_informe_rate_limiter().check(_clave_usuario(usuario))
    if not permitido:
        from app.domains.geo.informe_area.errors import InformeAreaError

        raise InformeAreaError(
            status_code=429,
            codigo="limite_de_tasa",
            detail="Demasiados informes en poco tiempo; esperá un rato",
            retry_after=max(1, int(reset)),
        )


@router.post(
    "",
    response_model=InformeAreaResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generar un informe de área en segundo plano (privado)",
    dependencies=[
        Depends(_require_operator()),
        Depends(enforce_informe_body_limit),
        Depends(enforce_informe_rate_limit),
    ],
    openapi_extra=_body_openapi(InformeAreaCreate),
)
def crear_informe(
    payload: InformeAreaCreate = Depends(parse_informe_create_body),
    db: Session = Depends(get_db),
    usuario: Any = Depends(_require_operator()),
) -> InformeAreaResponse:
    """202 + the pending row, or the SAME completed row with ``desde_cache``
    when the selection + layer versions already produced one (S4)."""
    row, desde_cache = service.crear_informe(db, payload, usuario_id=usuario.id)
    return respuesta_informe(row, desde_cache=desde_cache)


@router.post(
    "/preview",
    response_model=InformeAreaPreviewResponse,
    summary="Medir una selección mixta (privado)",
    dependencies=[
        Depends(_require_operator()),
        Depends(enforce_informe_body_limit),
    ],
    openapi_extra=_body_openapi(InformeAreaPreviewRequest),
)
def preview_informe(
    payload: InformeAreaPreviewRequest = Depends(parse_informe_preview_body),
    db: Session = Depends(get_db),
    usuario: Any = Depends(_require_operator()),
) -> InformeAreaPreviewResponse:
    """Geometry-only measurement of a zonas + geometrias selection (PR 3).

    The Revisar step's data source now that the selection can carry drawn /
    KML-imported polygons the ficha's zonas-only preview cannot express. No
    rate limiter ON PURPOSE: the POST throttle above prices the background
    informe, this is authenticated statement-timeout-bounded PostGIS per
    selection change — the same reasoning that keeps GET status/list free.
    """
    return service.previsualizar(db, payload)


@router.get("", response_model=InformeAreaListResponse, summary="Mis informes")
def listar_informes(
    db: Session = Depends(get_db),
    usuario: Any = Depends(_require_operator()),
) -> InformeAreaListResponse:
    filas, total = service.listar_informes(db, usuario=usuario)
    return InformeAreaListResponse(items=[respuesta_informe(f) for f in filas], total=total)


@router.get(
    "/{informe_id}",
    response_model=InformeAreaResponse,
    summary="Estado de un informe (creador o admin)",
)
def obtener_informe(
    informe_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Any = Depends(_require_operator()),
) -> InformeAreaResponse:
    return respuesta_informe(service.obtener_informe(db, informe_id, usuario=usuario))


@router.get(
    "/{informe_id}/pdf",
    summary="Descargar el PDF del informe (creador o admin)",
    responses={
        409: {"description": "En progreso o fallido"},
        503: {"description": "Completado sin PDF renderizado"},
    },
)
def descargar_pdf(
    informe_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Any = Depends(_require_operator()),
) -> Response:
    """``application/pdf`` with the stored bytes, filename from the row's nombre.

    A completed row whose PDF never rendered (force-completed or pre-T2)
    still answers the typed 503 — the desglose lives in ``resultado``, but a
    download must never hand back a fabricated empty document.
    """
    contenido, disposition = service.descargar_pdf(db, informe_id, usuario=usuario)
    return Response(
        content=contenido,
        media_type="application/pdf",
        headers={"Content-Disposition": disposition},
    )


@router.get(
    "/{informe_id}/kmz",
    summary="Descargar el KMZ del informe (creador o admin)",
    responses={
        409: {"description": "En progreso o fallido"},
        503: {"description": "Completado sin KMZ renderizado"},
    },
)
def descargar_kmz(
    informe_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Any = Depends(_require_operator()),
) -> Response:
    """``application/vnd.google-earth.kmz`` — same privacy ladder as the PDF.

    S3: the Google Earth export (límite + subcuencas + one folder per theme,
    ``radioFolder`` so one theme is visible at a time). A degraded run that
    finished without the KMZ answers the typed 503, never an empty archive.
    """
    contenido, disposition = service.descargar_kmz(db, informe_id, usuario=usuario)
    return Response(
        content=contenido,
        media_type="application/vnd.google-earth.kmz",
        headers={"Content-Disposition": disposition},
    )


# ── PR 6 (S5): the PUBLIC campo route ────────────────────────────────────────
#
# No ``current_active_user`` here — this is the endpoint a phone reaches by
# scanning the QR on the PDF cover, often with no account and no signal. The
# opaque ``token_publico`` in the path IS the authorization (no personal
# data travels in the URL; the token is unrelated to the informe id), and it
# inherits the row's lifecycle: ``vence_at`` (90 days) and the row's deletion
# both kill it. Mounted under ``/api/v2/public`` by ``app.api.v2.public`` —
# the app's public aggregator — NOT under this router's authenticated prefix.
public_router = APIRouter(prefix="/campo", tags=["Informe de Área — campo"])


@public_router.get(
    "/{token}",
    summary="Paquete de campo por token público (sin autenticación)",
    responses={
        304: {"description": "Paquete sin cambios (ETag coincide)"},
        404: {"description": "Token desconocido, revocado o informe no completado"},
        410: {"description": "El informe venció (retención de 90 días)"},
    },
)
def obtener_paquete_campo(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    """The offline field package JSON — everything ``/campo/:token`` renders.

    404 is the ONLY answer for unknown/revoked/pending tokens (a public
    route must not become an oracle); 410 says the map expired so the phone
    shows an honest message instead of "no existe".
    """
    contenido = service.paquete_campo_por_token(db, token)
    etag = etag_for_body(contenido)
    headers = {
        "Cache-Control": "private, no-cache",
        "ETag": etag,
        "Vary": "Accept-Encoding",
    }
    if if_none_match_hits(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return Response(
        content=contenido,
        media_type="application/json",
        headers=headers,
    )
