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

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.dependencies import current_active_user
from app.config import settings
from app.core.logging import get_logger
from app.core.rate_limit import DistributedRateLimiter
from app.db.session import get_db
from app.domains.geo.informe_area import service
from app.domains.geo.informe_area.schemas import (
    InformeAreaCreate,
    InformeAreaListResponse,
    InformeAreaResponse,
    respuesta_informe,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/informes-area", tags=["Informe de Área"])


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


async def enforce_informe_rate_limit(
    request: Request,  # noqa: ARG001 — kept for dependency symmetry
    usuario: Any = Depends(current_active_user),
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
    dependencies=[Depends(enforce_informe_rate_limit)],
)
def crear_informe(
    payload: InformeAreaCreate,
    db: Session = Depends(get_db),
    usuario: Any = Depends(current_active_user),
) -> InformeAreaResponse:
    """202 + the pending row, or the SAME completed row with ``desde_cache``
    when the selection + layer versions already produced one (S4)."""
    row, desde_cache = service.crear_informe(db, payload, usuario_id=usuario.id)
    return respuesta_informe(row, desde_cache=desde_cache)


@router.get("", response_model=InformeAreaListResponse, summary="Mis informes")
def listar_informes(
    db: Session = Depends(get_db),
    usuario: Any = Depends(current_active_user),
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
    usuario: Any = Depends(current_active_user),
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
    usuario: Any = Depends(current_active_user),
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
