"""Error contract for the informe de área endpoints.

Same FLAT body shape as the ficha territorial (``ficha_errors``, design §2.6)::

    {"detail": "<mensaje humano, en castellano>", "codigo": "<codigo estable>"}

The ficha's own errors (``zona_no_encontrada``, ``cap_excedido``) are raised
verbatim by the shared resolver and caps code, so this module only owns the
codes that are SPECIFIC to the informe lifecycle: privacy 404, in-progress
ceiling, and the not-yet/T2 PDF placeholder. ``app.main`` installs the ficha
handler globally; tests that mount a standalone app must install BOTH (the
ficha handler is what turns a resolver ``FichaError`` into a flat body).
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger(__name__)


class InformeAreaError(Exception):
    """One row of the informe de área error table (flat §2.6 body)."""

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


def informe_no_encontrado() -> InformeAreaError:
    """404 for a missing informe — and, deliberately, for somebody else's.

    S11 makes informes private per user. A foreign informe must answer with
    the SAME body as an absent one: a distinct 403 would confirm to a logged-in
    operator that somebody else's informe id exists, which is exactly the
    disclosure the privacy decision forbids.
    """
    return InformeAreaError(
        status_code=404,
        codigo="informe_no_encontrado",
        detail="No existe un informe de área con ese id",
    )


def limite_en_curso(maximo: int) -> InformeAreaError:
    """429 when the user already holds the ceiling of in-progress informes."""
    return InformeAreaError(
        status_code=429,
        codigo="limite_informes_en_curso",
        detail=(
            f"Ya tenés {maximo} informes en curso. Esperá a que terminen antes de generar otro."
        ),
    )


def pdf_en_progreso() -> InformeAreaError:
    """409 when the PDF is asked for before the informe finished."""
    return InformeAreaError(
        status_code=409,
        codigo="informe_en_progreso",
        detail="El informe todavía se está generando; probá de acá a un rato",
        retry_after=30,
    )


def informe_fallido(error: str | None) -> InformeAreaError:
    """409 when the informe failed — the stored reason travels, readable."""
    motivo = (error or "").strip() or "motivo desconocido"
    return InformeAreaError(
        status_code=409,
        codigo="informe_fallido",
        detail=f"El informe no pudo generarse: {motivo}",
    )


def pdf_no_disponible() -> InformeAreaError:
    """503 while the PDF builder (T2) has not landed for this informe.

    The informe row is ``completed`` — the desglose and totals ARE stored — but
    the byte stream is rendered by ``mapas.py`` + ``builders_informe_area.py``,
    which T2 ships. Until then the content path is wired up to this typed
    error so the route's contract (and its tests) exist before the renderer.
    """
    return InformeAreaError(
        status_code=503,
        codigo="pdf_aun_no_disponible",
        detail="El PDF del informe todavía no está disponible en esta versión",
    )


# ── PR 6: KMZ + campo público ────────────────────────────────────────────────


def kmz_no_disponible() -> InformeAreaError:
    """503 when a completed row's KMZ never rendered (degraded run).

    Same contract as ``pdf_no_disponible``: the informe is there, the export
    is not — an honest typed error, never a fabricated empty archive.
    """
    return InformeAreaError(
        status_code=503,
        codigo="kmz_aun_no_disponible",
        detail="El KMZ del informe no está disponible (la generación se degradó)",
    )


def campo_token_invalido() -> InformeAreaError:
    """404 for an unknown campo token — the ONLY answer an outsider gets.

    Deliberately identical for a token that never existed, a token whose row
    the retention sweep deleted (revocation, S10), and a token whose informe
    is still pending: a public route must not confirm which of the three it
    was, and it must not leak whether SOME informe exists behind a guess.
    """
    return InformeAreaError(
        status_code=404,
        codigo="campo_no_encontrado",
        detail="Este mapa de campo no existe o ya no está disponible",
    )


def campo_vencido() -> InformeAreaError:
    """410 Gone: the token's row outlived its ``vence_at`` (90 days, PR 2).

    Distinct from 404 on purpose: the phone that scanned the QR deserves to
    know the map EXPIRED (and that re-generating the informe re-issues a new
    token), not that it mysteriously vanished. Between ``vence_at`` and the
    daily sweep the row still exists, so this is the honest status.
    """
    return InformeAreaError(
        status_code=410,
        codigo="campo_vencido",
        detail="Este mapa de campo venció (los informes se conservan 90 días)",
    )


# 5xx codes that describe a state somebody CHOSE, not something that broke —
# logged at WARNING so a pending-T2 deployment does not emit an ERROR per
# download attempt (same discipline as ``ficha_errors._ESTADOS_DELIBERADOS``).
_ESTADOS_DELIBERADOS = frozenset({"pdf_aun_no_disponible"})


def _manejador(_: Any, exc: Exception) -> JSONResponse:
    # Starlette types handlers as (Request, Exception); mypy rejects a
    # narrower exc type at add_exception_handler. Narrow inside instead.
    assert isinstance(exc, InformeAreaError)
    if exc.status_code >= 500 and exc.codigo not in _ESTADOS_DELIBERADOS:
        logger.error("Informe de área falló", codigo=exc.codigo, exc_info=True)
    elif exc.status_code >= 500:
        logger.info("Informe de área en estado deliberado", codigo=exc.codigo)
    return JSONResponse(status_code=exc.status_code, content=exc.payload())


def install_informe_area_error_handler(app: FastAPI) -> None:
    """Register the handler. Called by ``app.main`` and by test apps."""
    app.add_exception_handler(InformeAreaError, _manejador)
