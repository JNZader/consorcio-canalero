"""Ficha territorial service — guards now, compute in A3b.

This module owns the three enforcement steps that must run between "the body
parsed" and "a raster is opened" (design §2.1, §2.4, §2.5):

1. ``assert_within_caps`` — the cap authority. Pydantic only ever sees a
   caller-supplied polygon; ``parcela``, ``canal_buffer`` and ``canal_cuenca``
   all resolve a geometry the caller never sent (a large catastro parcel, an
   unbounded ``ST_Buffer``, a precomputed catchment), so every resolution
   re-checks area / envelope / vertices BEFORE the first raster open
   (JD-A-002, JDB-006).
2. ``escribir_auditoria`` — the Ley 25.326 trace, COMMITTED before compute so a
   failed computation still leaves a row.
3. ``slot_de_computo`` — a process-level ``BoundedSemaphore``: the handler is
   sync and runs on Starlette's threadpool, and rasterio holds real memory per
   call. This is the hard bound on simultaneous raster memory, independent of
   Redis.

WHAT IS ACTUALLY WIRED IN THIS SLICE (be honest about the gap — R2-002):
``assert_within_caps`` is implemented and unit-testable, but NOTHING CALLS IT
yet. It cannot be called: the caps run over a RESOLVED shapely geometry in
EPSG:32720, and geometry resolution is A3b (parcela/poligono), A6
(canal_buffer) and A7 (canal_cuenca). What ``analizar_zona`` wires today is the
audit row, the semaphore and a PLACEHOLDER response — the ORDER of the guards
is real and is what this slice ships; the cap ENFORCEMENT is designed, not
live. The route is therefore off by default (``settings.ficha_enabled``).
"""

from __future__ import annotations

import hashlib
import json
import threading
from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy.orm import Session

from app.config import settings
from app.core.logging import get_logger
from app.domains.geo import ficha_errors
from app.domains.geo.schemas_ficha import (
    DatasetFicha,
    FichaRequest,
    FichaResponse,
    PrecipitacionFicha,
)
from app.shared.audit_log import write_audit_entry_sync

logger = get_logger(__name__)

M2_POR_HA = 10_000.0
SEMAFORO_TIMEOUT_S = 2.0

# Per PROCESS, not per request — and built LAZILY (R3-010) so the bound is read
# from settings at first use instead of at import time. Import-time construction
# froze ``ficha_max_concurrency`` before any test could change it, and the only
# way to exercise saturation was to reach in and rebind the private ``_slots``.
# Mirrors ``router_ficha.get_ficha_rate_limiter``.
_slots: threading.BoundedSemaphore | None = None


def get_ficha_slots() -> threading.BoundedSemaphore:
    """The in-flight bound for raster work. Built on first use."""
    global _slots
    if _slots is None:
        _slots = threading.BoundedSemaphore(settings.ficha_max_concurrency)
    return _slots


def reset_ficha_slots() -> None:
    """Drop the cached semaphore so the next call re-reads the setting (tests)."""
    global _slots
    _slots = None


def _contar_vertices_shapely(geom: Any) -> int:
    partes = getattr(geom, "geoms", None) or [geom]
    total = 0
    for parte in partes:
        exterior = getattr(parte, "exterior", None)
        if exterior is None:
            continue
        total += len(exterior.coords)
        total += sum(len(interior.coords) for interior in parte.interiors)
    return total


def assert_within_caps(geom: Any, *, tipo: str, buffer_m: float | None = None) -> None:
    """Reject a resolved geometry that would cost too much. 422 ``cap_excedido``.

    ``geom`` is a shapely geometry in a METRIC CRS (EPSG:32720 — the same
    projection ``area_ha`` is computed in, so there is no second projection).
    Pure computation: no DB, no file, no network. Valid for the four ``tipo``
    values; ``buffer_m`` is only passed by ``canal_buffer``.
    """
    if buffer_m is not None and buffer_m > settings.ficha_max_buffer_m:
        raise ficha_errors.cap_excedido("buffer_m", settings.ficha_max_buffer_m, buffer_m)

    if geom is None or geom.is_empty:
        raise ficha_errors.geometria_invalida(f"geometria vacia para tipo={tipo}")

    area_ha = geom.area / M2_POR_HA
    if area_ha > settings.ficha_max_area_ha:
        raise ficha_errors.cap_excedido("area_ha", settings.ficha_max_area_ha, area_ha)

    minx, miny, maxx, maxy = geom.bounds
    envelope_ha = abs((maxx - minx) * (maxy - miny)) / M2_POR_HA
    if envelope_ha > settings.ficha_max_envelope_ha:
        raise ficha_errors.cap_excedido("envelope_ha", settings.ficha_max_envelope_ha, envelope_ha)

    vertices = _contar_vertices_shapely(geom)
    if vertices > settings.ficha_max_vertices:
        raise ficha_errors.cap_excedido(
            "vertices", float(settings.ficha_max_vertices), float(vertices)
        )


def _huella_geometria(geometry: dict[str, Any]) -> str:
    """Stable 16-hex digest of a GeoJSON geometry (F2).

    ``hash()`` was WRONG here in two independent ways, and both defeat the only
    purpose this reference has — correlating audit rows for the same shape:

    * PYTHONHASHSEED is randomised per process, so the same polygon audited
      twice got two different refs across a restart, and never matched between
      the two uvicorn workers;
    * it hashed ``repr(dict)``, which is key-INSERTION ordered, so the same
      geometry with ``{"coordinates":…, "type":…}`` hashed differently from
      ``{"type":…, "coordinates":…}``.

    Canonical JSON (sorted keys, no whitespace) + SHA-256 fixes both. This is a
    correlation id, not a security token: 16 hex chars is ample, and the digest
    is one-way so the geometry itself never lands in the audit table.
    """
    canonico = json.dumps(geometry, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()[:16]


def referencia_auditable(payload: FichaRequest) -> str:
    """``resource`` value for the audit row — never a person, never a geometry."""
    tipo = payload.tipo
    if tipo == "parcela":
        return f"tipo=parcela,ref={payload.nomenclatura}"
    if tipo == "poligono":
        return f"tipo=poligono,ref=geom:{_huella_geometria(payload.geometry)}"
    if tipo == "canal_buffer":
        return f"tipo=canal_buffer,ref={payload.canal_id},buffer_m={payload.buffer_m}"
    return f"tipo=canal_cuenca,ref={payload.canal_id},variante={payload.variante}"


def escribir_auditoria(db: Session, payload: FichaRequest, *, client_ip: str | None) -> None:
    """One row per ACCEPTED request, committed BEFORE compute.

    ``user_id`` stays NULL by design: the endpoint is public.

    FOLLOW-UP, deliberately not handled in this slice (R1-001): ``audit_log``
    has no purge job, and this is its FIRST unauthenticated writer — every
    other writer is gated by a login, so the table has so far grown at
    operator pace. A public endpoint makes row volume a function of internet
    traffic instead. Retention/partitioning is out of scope here and is
    tracked as its own item.
    """
    write_audit_entry_sync(
        db,
        user_id=None,
        action="zona.analisis",
        resource=referencia_auditable(payload),
        client_ip=client_ip,
    )
    db.commit()


@contextmanager
def slot_de_computo() -> Iterator[None]:
    """Bound in-flight raster work; 503 ``sobrecarga`` on timeout."""
    slots = get_ficha_slots()
    if not slots.acquire(timeout=SEMAFORO_TIMEOUT_S):
        logger.warning("Ficha territorial saturada", max_concurrency=settings.ficha_max_concurrency)
        raise ficha_errors.sobrecarga(retry_after=int(SEMAFORO_TIMEOUT_S) or 1)
    try:
        yield
    finally:
        slots.release()


def _dataset_vacio() -> DatasetFicha:
    return DatasetFicha(cobertura="sin_cobertura", clases=[], pixel_count=0, low_confidence=False)


def analizar_zona(db: Session, payload: FichaRequest, *, client_ip: str | None) -> FichaResponse:
    """Enforcement order (design §2.5): caps → audit (committed) → semaphore → compute.

    Rate limit and the body-size guard already ran as router dependencies, and
    the cheap ``poligono`` validators ran in the schema.

    The caps step comes FIRST, and OUTSIDE the semaphore (R3-009), for two
    reasons that the reversed order silently broke:

    * a request that is going to be rejected with 422 ``cap_excedido`` must not
      leave an audit row claiming it was accepted — ``escribir_auditoria`` is
      documented as "one row per ACCEPTED request";
    * cap checking is pure CPU over an already-resolved geometry and opens no
      raster, so holding one of the few compute slots while doing it lets a
      stream of oversized requests starve legitimate ones out of the semaphore
      without ever touching a raster.

    Geometry resolution + the ``assert_within_caps`` call + the raster loop are
    A3b/A6/A7; until then this returns a placeholder with every dataset
    ``sin_cobertura`` — never fabricated hectares — and the route stays gated
    off by ``settings.ficha_enabled``.
    """
    # TODO(A3b): resolve the geometry per ``tipo`` (catastro lookup / ST_Buffer /
    # precomputed catchment) and call ``assert_within_caps(geom, tipo=payload.tipo,
    # buffer_m=...)`` HERE — before the audit row and outside ``slot_de_computo``.
    escribir_auditoria(db, payload, client_ip=client_ip)
    with slot_de_computo():
        # TODO(A3b): run the raster loop and build the real datasets.
        return FichaResponse(
            tipo=payload.tipo,
            area_ha=0.0,
            suelos=_dataset_vacio(),
            flood_risk=_dataset_vacio(),
            drainage_need=_dataset_vacio(),
            precipitacion_mensual=PrecipitacionFicha(cobertura="sin_cobertura"),
        )
