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

WHAT IS WIRED (A3b): ``tipo=parcela`` is the real compute. ``analizar_zona``
resolves the catastro geometry, calls ``assert_within_caps`` over the resolved
EPSG:32720 shape (so the cap ENFORCEMENT is now live, not just designed), commits
the audit row, then runs the soils overlay + the flood_risk/drainage_need raster
loop under the semaphore. The other three tipos still resolve a geometry the
caller never sent — a drawn polygon (A5), a canal buffer (A6), a precomputed
catchment (A7) — so they keep the audit + semaphore path and a ``sin_cobertura``
placeholder until those slices land. The route stays off by default
(``settings.ficha_enabled``); tests flip it on via monkeypatch.
"""

from __future__ import annotations

import hashlib
import json
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from shapely.geometry import shape
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.core.logging import get_logger
from app.domains.geo import ficha_errors
from app.domains.geo.class_breaks import RANGE_CONFIGS
from app.domains.geo.composites import extract_zonal_profile
from app.domains.geo.models import GeoLayer
from app.domains.geo.schemas_ficha import (
    ClaseFicha,
    DatasetFicha,
    FichaRequest,
    FichaResponse,
    PrecipitacionFicha,
)
from app.shared.audit_log import write_audit_entry_sync

logger = get_logger(__name__)

M2_POR_HA = 10_000.0
SEMAFORO_TIMEOUT_S = 2.0

# primitive coverage vocabulary → wire vocabulary (design §2, spec). The
# primitive speaks full/partial/none; the ficha speaks total/parcial/sin_cobertura.
_COBERTURA_WIRE = {"full": "total", "partial": "parcial", "none": "sin_cobertura"}

# Roman capability scale I–VIII the suelos legend uses (§3.2). ``detalle`` keeps
# the full subclass (``IVws``); only the prefix groups. Ranks give a stable,
# legend-ordered response; the two synthetic buckets sort last.
_ORDEN_ROMANO = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8}
_SIN_CLASIFICAR = "sin clasificar"
_SIN_DATO = "sin dato"
# A residual smaller than this fraction of the parcel is float noise, not a real
# gap in soil knowledge — do not emit a "sin dato" row for it (§3.1).
_RESIDUAL_MIN_FRAC = 0.005

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


def _aplicar_statement_timeout(db: Session) -> None:
    """Bound this request's DB work transaction-locally (F1 — R1-002 + R4-002).

    ``_resolver_parcela`` (ST_Transform/ST_Area) and ``_suelos_dataset``
    (ST_Intersection over ``suelos_catastro``) run on the sync request session,
    which carries no statement_timeout — and the area cap is a loose 20 000 ha,
    so ONE legitimate giant catastro parcel could pin a DB connection + a
    threadpool thread unbounded.

    ``set_config(..., is_local => true)`` is SET LOCAL semantics but, unlike the
    bare ``SET LOCAL`` statement, accepts a bound parameter — so the value is
    parameterized, transaction-scoped, and never leaks onto the pooled
    connection. It MUST be re-applied after the pre-compute audit COMMIT, which
    ends the first transaction and with it any LOCAL setting made before it.
    """
    db.execute(
        text("SELECT set_config('statement_timeout', :ms, true)"),
        {"ms": str(settings.ficha_statement_timeout_ms)},
    )


# ── geometry resolution (parcela only in this slice; §2, A3b) ───────────────


def _resolver_parcela(db: Session, nomenclatura: str) -> tuple[str, str, float]:
    """Look up a parcela geometry by ``nomenclatura``. 404 when absent.

    Returns ``(geojson_4326, geojson_32720, area_m2)``. The 4326 shape drives the
    soils overlay and the raster loop; the 32720 shape is what ``assert_within_caps``
    measures (area/envelope/vertices in metres), and ``area_m2`` (``ST_Area`` in
    EPSG:32720, the projection the whole ficha uses) is both ``area_ha`` and the
    ``geom_area_m2`` the primitive needs for its relative confidence rule.
    """
    fila = db.execute(
        text(
            "SELECT ST_AsGeoJSON(geometria) AS g4326, "
            "ST_AsGeoJSON(ST_Transform(geometria, 32720)) AS g32720, "
            "ST_Area(ST_Transform(geometria, 32720)) AS area_m2 "
            "FROM parcelas_catastro WHERE nomenclatura = :nom LIMIT 1"
        ),
        {"nom": nomenclatura},
    ).one_or_none()
    if fila is None:
        raise ficha_errors.parcela_no_encontrada(nomenclatura)
    return fila.g4326, fila.g32720, float(fila.area_m2)


# ── soils overlay (PostGIS ST_Intersection, parameterized geometry; §3) ─────

# The 0015 mv_suelos_por_zona SQL SHAPE, re-parameterized by the REQUEST geometry
# instead of ``zonas_operativas`` (§3.4: the MV is keyed to zones and cannot serve
# arbitrary geometry, so the ficha runs the same intersection against ``:geojson``).
_SUELOS_SQL = text(
    """
    WITH g AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geojson), 4326) AS geom)
    SELECT s.cap AS cap,
           ST_Area(ST_Transform(
               ST_CollectionExtract(ST_Intersection(s.geometria, g.geom), 3), 32720
           )) / 10000.0 AS ha
    FROM suelos_catastro s, g
    WHERE ST_Intersects(s.geometria, g.geom)
      AND NOT ST_IsEmpty(ST_CollectionExtract(ST_Intersection(s.geometria, g.geom), 3))
    """
)


def _normalizar_cap(cap: str | None) -> str | None:
    """Roman capability prefix of a ``cap`` value (``IVws`` → ``IV``); ``None`` when unclassified.

    Strips the subclass suffix server-side so the grouping matches the I–VIII
    legend (§3.2, JDB-010 / JDB flagged). A ``cap`` that is NULL or has no leading
    roman numeral is unclassified — it becomes ``"sin clasificar"`` upstream, never
    dropped and never merged into the ``"sin dato"`` residual.
    """
    if cap is None or not cap.strip():
        return None
    prefijo = ""
    for ch in cap.strip().upper():
        if ch in "IVX":
            prefijo += ch
        else:
            break
    return prefijo or None


def _rango_clase(clase: str) -> int:
    if clase == _SIN_CLASIFICAR:
        return 100
    if clase == _SIN_DATO:
        return 101
    return _ORDEN_ROMANO.get(clase, 99)


def _suelos_dataset(db: Session, geojson_4326: str, area_ha: float) -> DatasetFicha:
    """Per-capability-class hectares over the parcel, plus the uncovered residual.

    503 ``dataset_no_cargado`` when ``suelos_catastro`` is empty (§2.6): a ficha
    with no soils product is not a ficha, so that is the hard install dependency.
    Percentages are taken against the WHOLE parcel area, and the uncovered
    remainder is emitted as ``"sin dato"`` so the UI never claims full soil
    knowledge of a parcel the source does not tile (§3.1, JDB-009).
    """
    total = db.execute(text("SELECT count(*) FROM suelos_catastro")).scalar_one()
    if not total:
        raise ficha_errors.dataset_no_cargado("suelos")

    grupos: dict[str, dict[str, Any]] = {}
    for cap, ha in db.execute(_SUELOS_SQL, {"geojson": geojson_4326}).all():
        prefijo = _normalizar_cap(cap)
        clase = prefijo if prefijo else _SIN_CLASIFICAR
        grupo = grupos.setdefault(clase, {"ha": 0.0, "detalles": set()})
        grupo["ha"] += float(ha or 0.0)
        if cap and cap.strip():
            grupo["detalles"].add(cap.strip())

    cubierto_ha = sum(g["ha"] for g in grupos.values())
    residual_ha = max(0.0, area_ha - cubierto_ha)

    clases: list[ClaseFicha] = []
    for clase, grupo in grupos.items():
        detalles = sorted(grupo["detalles"])
        detalle = ",".join(detalles) if detalles and detalles != [clase] else None
        clases.append(
            ClaseFicha(
                clase=clase,
                ha=round(grupo["ha"], 4),
                pct=round(grupo["ha"] / area_ha * 100.0, 2) if area_ha > 0 else 0.0,
                detalle=detalle,
            )
        )
    if area_ha > 0 and residual_ha > _RESIDUAL_MIN_FRAC * area_ha:
        clases.append(
            ClaseFicha(
                clase=_SIN_DATO,
                ha=round(residual_ha, 4),
                pct=round(residual_ha / area_ha * 100.0, 2),
            )
        )
    clases.sort(key=lambda c: _rango_clase(c.clase))

    ratio = min(1.0, cubierto_ha / area_ha) if area_ha > 0 else 0.0
    if cubierto_ha <= 0:
        cobertura = "sin_cobertura"
    elif ratio >= 0.99:
        cobertura = "total"
    else:
        cobertura = "parcial"
    return DatasetFicha(
        cobertura=cobertura,
        clases=clases,
        pixel_count=0,  # soils is a vector overlay, not a raster sample
        low_confidence=False,
        cobertura_ratio=round(ratio, 4),
    )


# ── raster datasets (flood_risk, drainage_need via extract_zonal_profile) ───


def _raster_path(db: Session, tipo: str) -> str | None:
    """Newest registered raster of ``tipo``, preferring its COG (router_analysis pattern).

    ``None`` when nothing is registered or the file is gone — the dataset then
    reports ``sin_cobertura`` (schema R3-007: a missing SECONDARY raster is a
    symmetric no-coverage, never a dropped key and never a 503; the 503 hard
    dependency is ``suelos_catastro``, checked in ``_suelos_dataset``).
    """
    layer = (
        db.query(GeoLayer)
        .filter(GeoLayer.tipo == tipo)
        .order_by(GeoLayer.created_at.desc())
        .first()
    )
    if layer is None:
        # F2 (R4-001): a freshly-provisioned box whose flood/drainage pipeline has
        # not run yet leaves a breadcrumb instead of silently reporting
        # sin_cobertura on every ficha. Distinct from the "registered but file
        # gone" case below, and from the disjoint/all-nodata cases (those live
        # inside extract_zonal_profile). Response is unchanged (still None →
        # sin_cobertura, per R3-007).
        logger.info("raster de ficha no registrado", dataset=tipo)
        return None
    ruta = layer.archivo_path
    if layer.metadata_extra and layer.metadata_extra.get("cog_path"):
        cog = layer.metadata_extra["cog_path"]
        if Path(cog).exists():
            ruta = cog
    if not (ruta and Path(ruta).exists()):
        logger.info("raster de ficha registrado pero archivo ausente", dataset=tipo, ruta=ruta)
        return None
    return ruta


def _raster_dataset(
    db: Session, tipo: str, geom4326: dict[str, Any], area_m2: float
) -> DatasetFicha:
    ruta = _raster_path(db, tipo)
    if ruta is None:
        return _dataset_vacio()
    try:
        perfil = extract_zonal_profile(
            ruta,
            geom4326,
            geom_crs="EPSG:4326",
            breaks=RANGE_CONFIGS.get(tipo),
            geom_area_m2=area_m2,
            low_confidence_pixel_ratio=settings.ficha_low_confidence_pixel_ratio,
        )
    except ficha_errors.FichaError:
        raise
    except Exception as exc:  # noqa: BLE001 — any read failure is 503 raster_ilegible (§2.6)
        logger.error("Raster ilegible para ficha", dataset=tipo, exc_info=True)
        raise ficha_errors.raster_ilegible(tipo) from exc

    clases = [
        ClaseFicha(clase=b["label"], ha=b["ha"], pct=b["pct"])
        for b in perfil["bins"]
        if b["pixels"] > 0
    ]
    return DatasetFicha(
        cobertura=_COBERTURA_WIRE[perfil["coverage"]],
        clases=clases,
        pixel_count=perfil["valid_pixels"],
        low_confidence=perfil["low_confidence"],
        cobertura_ratio=perfil["coverage_ratio"],
    )


# ── orchestration ───────────────────────────────────────────────────────────


def _analizar_parcela(db: Session, payload: Any, *, client_ip: str | None) -> FichaResponse:
    """Real compute for ``tipo=parcela`` (§2.5 enforcement order).

    resolve geometry (404 if absent) → ``assert_within_caps`` (422, outside the
    semaphore) → audit COMMITTED (survives a later compute failure) → semaphore
    (503) → soils overlay + raster loop.
    """
    _aplicar_statement_timeout(db)  # bounds the ST_Transform/ST_Area resolver query
    geojson_4326, geojson_32720, area_m2 = _resolver_parcela(db, payload.nomenclatura)
    geom_metrico = shape(json.loads(geojson_32720))
    assert_within_caps(geom_metrico, tipo="parcela")

    escribir_auditoria(db, payload, client_ip=client_ip)

    with slot_de_computo():
        # The audit COMMIT ended the first transaction (and its LOCAL timeout);
        # re-apply so the soils overlay + raster loop are bounded too (F1).
        _aplicar_statement_timeout(db)
        area_ha = area_m2 / M2_POR_HA
        geom4326 = json.loads(geojson_4326)
        return FichaResponse(
            tipo="parcela",
            area_ha=round(area_ha, 4),
            suelos=_suelos_dataset(db, geojson_4326, area_ha),
            flood_risk=_raster_dataset(db, "flood_risk", geom4326, area_m2),
            drainage_need=_raster_dataset(db, "drainage_need", geom4326, area_m2),
            precipitacion_mensual=PrecipitacionFicha(cobertura="sin_cobertura"),
        )


def analizar_zona(db: Session, payload: FichaRequest, *, client_ip: str | None) -> FichaResponse:
    """Enforcement order (design §2.5): resolve → caps → audit → semaphore → compute.

    Rate limit and the body-size guard already ran as router dependencies, and
    the cheap ``poligono`` validators ran in the schema.

    ``tipo=parcela`` is the real compute this slice ships. The other three tipos
    resolve a geometry the caller never sent — a drawn polygon (A5), a canal
    buffer (A6), a precomputed catchment (A7) — and until those land they keep the
    audit + semaphore path and a ``sin_cobertura`` placeholder (never fabricated
    hectares). The route stays gated by ``settings.ficha_enabled``.
    """
    if payload.tipo == "parcela":
        return _analizar_parcela(db, payload, client_ip=client_ip)

    escribir_auditoria(db, payload, client_ip=client_ip)
    with slot_de_computo():
        return FichaResponse(
            tipo=payload.tipo,
            area_ha=0.0,
            suelos=_dataset_vacio(),
            flood_risk=_dataset_vacio(),
            drainage_need=_dataset_vacio(),
            precipitacion_mensual=PrecipitacionFicha(cobertura="sin_cobertura"),
        )
