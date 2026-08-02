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

WHAT IS WIRED (A3b + A5 + A6): ``tipo=parcela``, ``tipo=poligono`` and
``tipo=canal_buffer`` are all real compute. ``parcela`` resolves the catastro
geometry by ``nomenclatura``; ``poligono`` takes the geometry from the REQUEST
and REPAIRS it in PostGIS (``ST_CollectionExtract(ST_MakeValid(...), 3)``) so a
self-intersecting hand-drawn ring cannot reach ``ST_Intersection``/``rasterio_mask``
raw and yield a silently wrong area (§2.7, JDB-008); ``canal_buffer`` resolves a
curated ``canal_consorcio`` trace by its string id and sweeps it with
``ST_Buffer`` in EPSG:32720 (§2.1, JDB-006); ``canal_cuenca`` reads the
precomputed upstream catchment ``generate_canal_catchments`` stored for that
canal (A7). All four then call ``assert_within_caps`` over the resolved
EPSG:32720 shape — for ``poligono``/``canal_buffer`` the caps are the whole
point, since the resolved AREA is not what the caller sent — commit the audit
row, and run the IDENTICAL soils overlay + flood_risk/drainage_need raster loop
under the semaphore (``_ficha_de_geometria``). The route stays off by default
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
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.logging import get_logger
from app.domains.geo import ficha_errors
from app.domains.geo.class_breaks import RANGE_CONFIGS
from app.domains.geo.composites import extract_zonal_profile, vectorize_zonal_classes
from app.domains.geo.models import GeoLayer
from app.domains.geo.repository import GeoRepository
from app.domains.geo.schemas_ficha import (
    ClaseFicha,
    DatasetFicha,
    FichaOverlayFeature,
    FichaOverlayResponse,
    FichaRequest,
    FichaResponse,
    PrecipitacionFicha,
    PrecipMes,
)
from app.shared.audit_log import write_audit_entry_sync

logger = get_logger(__name__)

# Stateless data-access layer, instantiated once like ``service.py`` does. The
# ficha only needs the month-scoped precip lookup from it (B1b); soils and the
# flood/drainage rasters keep their inline SQL / ``GeoLayer`` queries.
_repo = GeoRepository()

# CHIRPS normals are warped to ~5 km pixels, so a parcel is ALWAYS sub-pixel
# against them; flagging that as low-confidence would fire on every ficha for a
# field that is a smooth interpolated normal, not a coarse sample (JDB-017,
# design §1.3). ``K = 0`` in ``extract_zonal_profile`` never flags.
_PRECIP_K = 0.0

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
        return f"tipo=canal_buffer,ref={payload.canal_ref},buffer_m={payload.buffer_m}"
    return f"tipo=canal_cuenca,ref={payload.canal_ref},variante={payload.variante}"


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


# psycopg2 sets ``pgcode`` to this SQLSTATE when ``statement_timeout`` cancels a
# query; SQLAlchemy surfaces it as ``OperationalError`` with the psycopg2 error
# under ``.orig``.
_SQLSTATE_QUERY_CANCELED = "57014"


@contextmanager
def _traducir_fallas_db() -> Iterator[None]:
    """Map a DB fault to a clean FichaError instead of a bare 500 (R4-001).

    Every resolver/overlay query runs on the sync request session under a LOCAL
    ``statement_timeout`` (``_aplicar_statement_timeout``). A caller-drawn polygon
    too expensive to intersect trips that bound → psycopg2 ``QueryCanceled`` →
    SQLAlchemy ``OperationalError`` (SQLSTATE 57014). That is the design's
    DELIBERATE protective ceiling, not a fault, so it maps to 503
    ``analisis_timeout`` (WARNING). Any OTHER ``DBAPIError`` (connection drop,
    deadlock) is real infrastructure trouble → 503 ``base_de_datos_no_disponible``
    (ERROR).

    Mirrors ``_raster_dataset``: re-raise a ``FichaError`` untouched, translate the
    DB layer, and never let a raw DB exception escape to
    ``generic_exception_handler`` as a 500 + Sentry event.
    """
    try:
        yield
    except ficha_errors.FichaError:
        raise
    except (OperationalError, DBAPIError) as exc:
        pgcode = getattr(getattr(exc, "orig", None), "pgcode", None)
        if pgcode == _SQLSTATE_QUERY_CANCELED:
            raise ficha_errors.analisis_timeout() from exc
        raise ficha_errors.base_de_datos_no_disponible() from exc


# ── geometry resolution (parcela only in this slice; §2, A3b) ───────────────


def _resolver_parcela(db: Session, nomenclatura: str) -> tuple[str, str, float]:
    """Look up a parcela geometry by ``nomenclatura``. 404 when absent.

    Returns ``(geojson_4326, geojson_32720, area_m2)``. The 4326 shape drives the
    soils overlay and the raster loop; the 32720 shape is what ``assert_within_caps``
    measures (area/envelope/vertices in metres), and ``area_m2`` (``ST_Area`` in
    EPSG:32720, the projection the whole ficha uses) is both ``area_ha`` and the
    ``geom_area_m2`` the primitive needs for its relative confidence rule.
    """
    with _traducir_fallas_db():
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


# The caller-drawn polygon repaired in PostGIS (§2.7, JDB-008). ``ST_MakeValid``
# fixes a self-intersecting (bow-tie) ring; ``ST_CollectionExtract(..., 3)`` keeps
# only the polygonal component (a bow-tie that collapses to a line/point yields an
# EMPTY polygon here — surfaced as 422 ``geometria_invalida`` by the caller). The
# repaired shape is returned both as 4326 (soils + raster loop) and projected to
# 32720 (the caps measurement + ``area_m2``), mirroring ``_resolver_parcela``.
_POLIGONO_SQL = text(
    """
    WITH reparada AS (
        SELECT ST_CollectionExtract(
                   ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(:geojson), 4326)), 3
               ) AS geom
    )
    SELECT ST_IsEmpty(geom) AS vacio,
           ST_AsGeoJSON(geom) AS g4326,
           ST_AsGeoJSON(ST_Transform(geom, 32720)) AS g32720,
           ST_Area(ST_Transform(geom, 32720)) AS area_m2
    FROM reparada
    """
)


def _resolver_poligono(db: Session, geometry: dict[str, Any]) -> tuple[str, str, float]:
    """Repair a caller-drawn polygon and measure it. 422 when it degenerates.

    The cheap schema validators (``schemas_ficha``) already rejected a malformed
    body — wrong type, unclosed ring, out-of-range coord, over the vertex cap.
    What they CANNOT see is a true self-intersection: a bow-tie ring is
    well-formed GeoJSON. ``ST_MakeValid`` + ``ST_CollectionExtract(..., 3)`` is
    the authority for that class (§2.7, JDB-008). If the repair leaves nothing
    polygonal (empty geometry) or zero area, the drawing is unusable → 422
    ``geometria_invalida``, never a silently wrong intersection.

    Returns ``(geojson_4326, geojson_32720, area_m2)``, same contract as
    ``_resolver_parcela`` so the compute tail is shared.
    """
    with _traducir_fallas_db():
        fila = db.execute(_POLIGONO_SQL, {"geojson": json.dumps(geometry)}).one()
    if fila.vacio or fila.area_m2 is None or float(fila.area_m2) <= 0.0:
        raise ficha_errors.geometria_invalida(
            "la geometria quedo vacia o sin area tras repararla "
            "(posible auto-interseccion o anillo degenerado)"
        )
    return fila.g4326, fila.g32720, float(fila.area_m2)


# The influence strip around a CURATED consorcio canal (§2, §2.1, JDB-006).
# ``canal_consorcio.geom`` is a LineString in EPSG:4326, keyed by the string id
# (e.g. ``canal-ne-sin-intervencion``); the buffer is taken in EPSG:32720
# (metric — a metre is a metre) and the resulting polygon is what the whole ficha
# runs on. ``geom IS NOT NULL`` is defensive (the column is NOT NULL in the
# schema, but a row with no trace has nothing to buffer) → 404, same as a missing
# id. The buffered zone is returned both as 4326 (soils + raster loop) and 32720
# (the caps measurement + ``area_m2``), mirroring
# ``_resolver_parcela``/``_resolver_poligono``.
_CANAL_BUFFER_SQL = text(
    """
    WITH canal AS (
        SELECT ST_Transform(geom, 32720) AS geom_m
        FROM canal_consorcio
        WHERE id = :canal_ref AND geom IS NOT NULL
        LIMIT 1
    ), zona AS (
        SELECT ST_Buffer(geom_m, :buffer_m) AS geom_m FROM canal
    )
    SELECT ST_AsGeoJSON(ST_Transform(geom_m, 4326)) AS g4326,
           ST_AsGeoJSON(geom_m) AS g32720,
           ST_Area(geom_m) AS area_m2
    FROM zona
    """
)


def _resolver_canal_buffer(db: Session, canal_ref: str, buffer_m: float) -> tuple[str, str, float]:
    """Buffer a curated canal by ``buffer_m`` metres. 404 when the canal is absent.

    ``canal_ref`` is the ``canal_consorcio`` string id. Returns
    ``(geojson_4326, geojson_32720, area_m2)``, same contract as
    ``_resolver_parcela`` so the compute tail is shared. The buffered geometry is
    server-derived — the caller only chose an id and a distance — so
    ``assert_within_caps`` over the returned 32720 shape is the authority on the
    resolved AREA (a 2 km buffer on a long canal is a big polygon; the schema
    caps only the distance, not the area it sweeps — JDB-006).
    """
    with _traducir_fallas_db():
        fila = db.execute(
            _CANAL_BUFFER_SQL, {"canal_ref": canal_ref, "buffer_m": buffer_m}
        ).one_or_none()
    if fila is None or fila.area_m2 is None:
        raise ficha_errors.canal_no_encontrado(canal_ref)
    return fila.g4326, fila.g32720, float(fila.area_m2)


# The precomputed upstream catchment of a curated canal (A7 slice 2). Unlike the
# buffer, the geometry is not derived on the fly — ``generate_canal_catchments``
# stored it in ``canal_catchment`` keyed by ``(canal_ref, variante)``. Two bound
# lookups, in this order, so the three failure modes stay distinct:
#   1. the canal itself is unknown            → 404 canal_no_encontrado
#   2. the canal exists but has no catchment  → 503 cuenca_no_computada
#   3. the catchment is oversized (geom NULL) → 422 cuenca_demasiado_grande
_CANAL_EXISTE_SQL = text("SELECT 1 FROM canal_consorcio WHERE id = :canal_ref LIMIT 1")

_CANAL_CATCHMENT_SQL = text(
    """
    SELECT c.oversized AS oversized,
           c.geometria IS NULL AS geom_null,
           ST_AsGeoJSON(c.geometria) AS g4326,
           ST_AsGeoJSON(ST_Transform(c.geometria, 32720)) AS g32720,
           ST_Area(ST_Transform(c.geometria, 32720)) AS area_m2
    FROM canal_catchment c
    WHERE c.canal_ref = :canal_ref AND c.variante = :variante
    LIMIT 1
    """
)


def _resolver_canal_cuenca(db: Session, canal_ref: str, variante: str) -> tuple[str, str, float]:
    """Resolve a canal's precomputed catchment. Distinct 404 / 503 / 422 by cause.

    Returns ``(geojson_4326, geojson_32720, area_m2)``, same contract as the other
    resolvers so the compute tail is shared. The stored catchment is already
    dissolved and within ``ficha_max_area_ha`` by construction (the batch drops the
    geometry of anything larger and flags it ``oversized``), so this only reads it
    back — the caps still re-run in ``assert_within_caps`` for symmetry.
    """
    with _traducir_fallas_db():
        existe = db.execute(_CANAL_EXISTE_SQL, {"canal_ref": canal_ref}).one_or_none()
    if existe is None:
        raise ficha_errors.canal_no_encontrado(canal_ref)

    with _traducir_fallas_db():
        fila = db.execute(
            _CANAL_CATCHMENT_SQL, {"canal_ref": canal_ref, "variante": variante}
        ).one_or_none()
    if fila is None:
        raise ficha_errors.cuenca_no_computada(canal_ref, variante)
    if fila.oversized or fila.geom_null or fila.area_m2 is None:
        raise ficha_errors.cuenca_demasiado_grande(canal_ref)
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


# Same intersection as ``_SUELOS_SQL`` but EMITS the clipped geometry (not its
# area) as GeoJSON for the on-map overlay (A(b) slice 1). The clip is capped with a
# topology-preserving simplify so a max-area zone crossing many detailed INTA soil
# polygons cannot ship a multi-MB payload on this public endpoint. The tolerance is
# applied in METERS (EPSG:32720) — the geometry is projected, simplified at 8 m
# (well below the ~1:50000 INTA layer's visible detail, so class boundaries stay
# accurate while the vertex count drops), then transformed back to 4326.
# ``ST_CollectionExtract(...,3)`` keeps only the polygonal part; ``ST_MakeValid``
# guards the stair-step self-intersections a clip or a simplify can produce, run
# LAST so the 4326 output is always a valid Polygon/MultiPolygon. Empty clips are
# filtered in the WHERE so no null/empty feature ships.
_SUELOS_OVERLAY_SQL = text(
    """
    WITH g AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geojson), 4326) AS geom)
    SELECT s.cap AS cap,
           ST_AsGeoJSON(
               ST_MakeValid(ST_Transform(
                   ST_SimplifyPreserveTopology(
                       ST_Transform(
                           ST_CollectionExtract(ST_Intersection(s.geometria, g.geom), 3),
                           32720
                       ),
                       8.0
                   ),
                   4326
               ))
           ) AS geojson
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
    with _traducir_fallas_db():
        total = db.execute(text("SELECT count(*) FROM suelos_catastro")).scalar_one()
    if not total:
        raise ficha_errors.dataset_no_cargado("suelos")

    with _traducir_fallas_db():
        filas_suelos = db.execute(_SUELOS_SQL, {"geojson": geojson_4326}).all()
    grupos: dict[str, dict[str, Any]] = {}
    for cap, ha in filas_suelos:
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


# ── precipitation dataset (CHIRPS monthly normals via extract_zonal_profile) ─


def _precip_raster_path(layer: GeoLayer) -> str | None:
    """On-disk path of a registered ``precip_normal`` layer, or ``None`` if gone.

    Mirrors ``_raster_path``'s file-existence check (a registered row whose file
    was pruned reads as missing) but takes the already-resolved ``GeoLayer`` — the
    month-scoped lookup (B1b) hands back one row PER month, so there is no "newest
    of tipo X" query to run here. CHIRPS normals carry no COG variant, so only
    ``archivo_path`` is probed.
    """
    ruta = layer.archivo_path
    if not (ruta and Path(ruta).exists()):
        logger.info("raster precip_normal registrado pero archivo ausente", ruta=ruta)
        return None
    return ruta


def _precipitacion_dataset(
    db: Session, geom4326: dict[str, Any], area_m2: float
) -> PrecipitacionFicha:
    """Monthly precipitation normals for the zone through the SHARED zonal path.

    Reads the 12 monthly (+ annual) CHIRPS normals with ``extract_zonal_profile``
    — the same primitive flood_risk / drainage_need use — and shapes them into the
    typed ``{serie:[{mes, mm}], anual_mm}`` exception (spec delta, JDB-011). No
    bespoke precipitation statistics.

    Coverage rules (spec "Monthly series for a zone" + "Zone outside precipitation
    coverage", design §4):

    * ZERO months registered → 503 ``dataset_no_cargado`` (``precipitacion``): the
      normals pipeline has not run for this deployment. Distinct from
      ``sin_cobertura`` (the dataset IS installed, this zone just has no data).
    * SOME months registered (an incomplete product) → ``sin_cobertura`` for the
      whole dataset: a partial series would be authoritative-looking fiction, and
      the spec forbids fabricating the missing months as zeros.
    * All 12 registered but the zone lies OUTSIDE the normals extent (every month
      reads ``coverage="none"``) → ``sin_cobertura``, empty ``serie`` — again no
      fabricated zeros.
    * All 12 registered AND covered → ``serie`` with 12 entries in CALENDAR order,
      each ``mm`` the raster mean, plus ``anual_mm`` from the annual raster.

    ``K = 0`` per call (``_PRECIP_K``) so a sub-pixel parcel is NEVER flagged
    low-confidence against the ~5 km CHIRPS pixel (JDB-017).
    """
    with _traducir_fallas_db():
        layers = _repo.get_latest_precip_normals_by_month(db, settings.ficha_precip_area_id)

    meses = [layers.get(str(mes)) for mes in range(1, 13)]
    # Guard ORDER is load-bearing: all-None (pipeline never ran → 503) MUST be
    # checked before any-None (incomplete product → sin_cobertura). Reversing them
    # would silently downgrade the "not installed" 503 into sin_cobertura.
    if all(layer is None for layer in meses):
        # Zero monthly normals registered → the CHIRPS ETL has not run for this
        # deployment. SOFT degradation (unlike suelos_catastro): precipitation is
        # an informational dataset, so it reports sin_cobertura and the rest of the
        # ficha (suelos/flood/drainage) keeps serving instead of a whole-request
        # 503. Logged at warning so ops can tell "ETL never ran" apart from a zone
        # genuinely outside the normals extent.
        logger.warning(
            "Normales de precipitacion no cargados (ETL CHIRPS no corrio)",
            area_id=settings.ficha_precip_area_id,
        )
        return PrecipitacionFicha(cobertura="sin_cobertura")
    if any(layer is None for layer in meses):
        # Incomplete product: some months missing. Do NOT fabricate zeros, do NOT
        # publish a partial series as if it were the full year. A half-registered
        # product is an operator-actionable state (interrupted ETL), distinct from
        # a zone genuinely outside the extent — log it so ops can tell them apart.
        registrados = sum(1 for layer in meses if layer is not None)
        logger.warning(
            "Producto de precipitacion incompleto para ficha",
            meses_registrados=registrados,
            area_id=settings.ficha_precip_area_id,
        )
        return PrecipitacionFicha(cobertura="sin_cobertura")

    serie: list[PrecipMes] = []
    coberturas: list[str] = []
    ratios: list[float] = []
    low_confidence = False
    pixel_count = 0
    for mes, layer in enumerate(meses, start=1):
        ruta = _precip_raster_path(layer)  # type: ignore[arg-type]  # None ruled out above
        if ruta is None:
            # A registered layer whose file vanished breaks the 12-month product.
            return PrecipitacionFicha(cobertura="sin_cobertura")
        perfil = _perfil_precip(ruta, geom4326, area_m2)
        coberturas.append(perfil["coverage"])
        ratios.append(perfil["coverage_ratio"])
        low_confidence = low_confidence or perfil["low_confidence"]
        pixel_count = max(pixel_count, perfil["valid_pixels"])
        if perfil["coverage"] != "none" and perfil["mean"] is not None:
            serie.append(PrecipMes(mes=mes, mm=perfil["mean"]))

    if len(serie) < 12:
        # Zone (partly) outside the normals extent — no fabricated zeros for the
        # months that did not resolve. A partial year is reported as no coverage.
        return PrecipitacionFicha(cobertura="sin_cobertura", pixel_count=pixel_count)

    anual_mm = _anual_mm(layers.get("anual"), geom4326, area_m2)
    cobertura = "total" if all(c == "full" for c in coberturas) else "parcial"
    return PrecipitacionFicha(
        cobertura=cobertura,
        low_confidence=low_confidence,
        pixel_count=pixel_count,
        cobertura_ratio=round(min(ratios), 4) if ratios else 0.0,
        serie=serie,
        anual_mm=anual_mm,
    )


def _perfil_precip(ruta: str, geom4326: dict[str, Any], area_m2: float) -> dict[str, Any]:
    """One ``extract_zonal_profile`` call with the precip conventions.

    ``breaks=None`` (precip is a continuous mm field, not a class partition, so
    there are no bins) and ``K = 0`` (never low-confidence). An unreadable raster
    is 503 ``raster_ilegible`` exactly as in ``_raster_dataset``.
    """
    try:
        return extract_zonal_profile(
            ruta,
            geom4326,
            geom_crs="EPSG:4326",
            breaks=None,
            geom_area_m2=area_m2,
            low_confidence_pixel_ratio=_PRECIP_K,
        )
    except ficha_errors.FichaError:
        raise
    except Exception as exc:  # noqa: BLE001 — any read failure is 503 raster_ilegible (§2.6)
        logger.error("Raster de precipitacion ilegible para ficha", ruta=ruta, exc_info=True)
        raise ficha_errors.raster_ilegible("precipitacion") from exc


def _anual_mm(layer: GeoLayer | None, geom4326: dict[str, Any], area_m2: float) -> float | None:
    """Annual-total mean mm for the zone, or ``None`` when unavailable.

    The annual raster is a convenience total registered alongside the 12 monthly
    normals (``mes="anual"``). It is not load-bearing: a missing or uncovered
    annual raster yields ``None``, never an error and never a fabricated value.
    """
    if layer is None:
        return None
    ruta = _precip_raster_path(layer)
    if ruta is None:
        return None
    perfil = _perfil_precip(ruta, geom4326, area_m2)
    if perfil["coverage"] == "none" or perfil["mean"] is None:
        return None
    return perfil["mean"]


# ── orchestration ───────────────────────────────────────────────────────────


def _ficha_de_geometria(
    db: Session,
    *,
    tipo: str,
    geojson_4326: str,
    area_m2: float,
    variante: str | None = None,
    geometria_cuenca: dict[str, Any] | None = None,
) -> FichaResponse:
    """Shared compute tail: soils overlay + raster loop under the semaphore.

    All four tipos reduce to the same computation once the geometry is resolved
    and the caps have passed — the design's "N rasters × 1 geometry (rasterio) + 1
    vector overlay × 1 geometry (PostGIS)". Keeping it in one place is what makes
    the datasets byte-compatible across tipos (the spec's "uniform response
    shape") instead of parallel paths that can drift.

    ``variante`` / ``geometria_cuenca`` are the ``canal_cuenca``-only additive
    fields (echoed back so the frontend can draw the catchment outline); they stay
    ``None`` for the other three tipos.

    The caller has ALREADY committed the audit row, so the LOCAL statement_timeout
    set before that commit is gone; it is re-applied here so the soils overlay +
    raster loop are bounded too (F1).
    """
    with slot_de_computo():
        _aplicar_statement_timeout(db)
        area_ha = area_m2 / M2_POR_HA
        geom4326 = json.loads(geojson_4326)
        return FichaResponse(
            tipo=tipo,
            area_ha=round(area_ha, 4),
            suelos=_suelos_dataset(db, geojson_4326, area_ha),
            flood_risk=_raster_dataset(db, "flood_risk", geom4326, area_m2),
            drainage_need=_raster_dataset(db, "drainage_need", geom4326, area_m2),
            precipitacion_mensual=_precipitacion_dataset(db, geom4326, area_m2),
            variante=variante,
            geometria_cuenca=geometria_cuenca,
        )


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
    return _ficha_de_geometria(db, tipo="parcela", geojson_4326=geojson_4326, area_m2=area_m2)


def _analizar_poligono(db: Session, payload: Any, *, client_ip: str | None) -> FichaResponse:
    """Real compute for ``tipo=poligono`` — geometry comes from the REQUEST (A5).

    Same §2.5 order as ``parcela``, but the geometry is caller-supplied, so the
    two guards that were unreachable for a server-derived shape are LIVE here:

    * ``_resolver_poligono`` repairs the drawing and rejects a degenerate result
      → 422 ``geometria_invalida`` (JDB-008);
    * ``assert_within_caps`` over the resolved 32720 shape → 422 ``cap_excedido``
      (area / envelope / vertices) — the caps are the whole reason they exist for
      a user-drawn polygon (§2.1).

    Both fire BEFORE the audit commit and BEFORE the semaphore, i.e. before any
    raster is opened. There is no 404: there is no parcel to not-find.
    """
    _aplicar_statement_timeout(db)  # bounds the ST_MakeValid/ST_Transform resolver query
    geojson_4326, geojson_32720, area_m2 = _resolver_poligono(db, payload.geometry)
    geom_metrico = shape(json.loads(geojson_32720))
    assert_within_caps(geom_metrico, tipo="poligono")

    escribir_auditoria(db, payload, client_ip=client_ip)
    return _ficha_de_geometria(db, tipo="poligono", geojson_4326=geojson_4326, area_m2=area_m2)


def _analizar_canal_buffer(db: Session, payload: Any, *, client_ip: str | None) -> FichaResponse:
    """Real compute for ``tipo=canal_buffer`` — a curated canal's influence strip.

    Same §2.5 order as the other tipos, but the geometry is doubly server-derived:
    the caller sends a ``canal_ref`` + a ``buffer_m``, and the service resolves the
    curated ``canal_consorcio`` trace and sweeps it. That makes ``assert_within_caps``
    LOAD-BEARING here for a reason the schema cannot cover: the schema caps
    ``buffer_m`` (the cheap distance check), but the AREA a 2 km buffer sweeps
    along a long canal is what actually costs, so the cap runs over the RESOLVED
    buffered polygon in EPSG:32720 — after the buffer, before any raster open
    (§2.1, JDB-006).

    ``buffer_m`` is passed to ``assert_within_caps`` too, so the distance cap is
    re-checked defensively even though the schema already rejected an over-cap
    value. There is a 404 (``canal_no_encontrado``) but no ``geometria_invalida``:
    the trace comes from ``canal_consorcio``, not from a caller-drawn ring.
    """
    _aplicar_statement_timeout(db)  # bounds the ST_Transform/ST_Buffer/ST_Area resolver query
    geojson_4326, geojson_32720, area_m2 = _resolver_canal_buffer(
        db, payload.canal_ref, payload.buffer_m
    )
    geom_metrico = shape(json.loads(geojson_32720))
    assert_within_caps(geom_metrico, tipo="canal_buffer", buffer_m=payload.buffer_m)

    escribir_auditoria(db, payload, client_ip=client_ip)
    return _ficha_de_geometria(db, tipo="canal_buffer", geojson_4326=geojson_4326, area_m2=area_m2)


def _analizar_canal_cuenca(db: Session, payload: Any, *, client_ip: str | None) -> FichaResponse:
    """Real compute for ``tipo=canal_cuenca`` — a canal's precomputed catchment (A7).

    Same §2.5 order as the other tipos. The geometry is neither caller-drawn nor
    derived on the fly: ``_resolver_canal_cuenca`` reads the dissolved catchment
    ``generate_canal_catchments`` stored for ``(canal_ref, variante)``, raising the
    three distinct coded failures (404 unknown canal / 503 not computed / 422
    oversized) BEFORE the audit commit and any raster open. The resolved catchment
    then runs the IDENTICAL shared tail as parcela/poligono/buffer, and the
    catchment outline is echoed back as ``geometria_cuenca`` so the map can draw it.
    """
    _aplicar_statement_timeout(db)  # bounds the catchment lookup queries
    geojson_4326, geojson_32720, area_m2 = _resolver_canal_cuenca(
        db, payload.canal_ref, payload.variante
    )
    geom_metrico = shape(json.loads(geojson_32720))
    assert_within_caps(geom_metrico, tipo="canal_cuenca")

    escribir_auditoria(db, payload, client_ip=client_ip)
    return _ficha_de_geometria(
        db,
        tipo="canal_cuenca",
        geojson_4326=geojson_4326,
        area_m2=area_m2,
        variante=payload.variante,
        geometria_cuenca=json.loads(geojson_4326),
    )


def analizar_zona(db: Session, payload: FichaRequest, *, client_ip: str | None) -> FichaResponse:
    """Enforcement order (design §2.5): resolve → caps → audit → semaphore → compute.

    Rate limit and the body-size guard already ran as router dependencies, and
    the cheap ``poligono`` validators ran in the schema.

    All four tipos are real compute now: ``parcela``/``poligono`` resolve a parcel
    or a drawn ring, ``canal_buffer`` sweeps a curated canal, and ``canal_cuenca``
    reads its precomputed catchment (A7). The route stays gated by
    ``settings.ficha_enabled``.
    """
    if payload.tipo == "parcela":
        return _analizar_parcela(db, payload, client_ip=client_ip)
    if payload.tipo == "poligono":
        return _analizar_poligono(db, payload, client_ip=client_ip)
    if payload.tipo == "canal_buffer":
        return _analizar_canal_buffer(db, payload, client_ip=client_ip)
    return _analizar_canal_cuenca(db, payload, client_ip=client_ip)


# ── on-map overlay (A(b) slice 1: soils vector) ─────────────────────────────


def _resolver_geometria_overlay(db: Session, payload: FichaRequest) -> tuple[str, str] | None:
    """Resolve the analysis geometry the same way the ficha does, for the overlay.

    Returns ``(geojson_4326, geojson_32720)`` — the 4326 shape feeds the soils
    clip, the 32720 shape feeds ``assert_within_caps``. All four tipos resolve a
    geometry now: ``canal_cuenca`` resolves to its precomputed catchment (A7) so
    the on-map overlay clips to the catchment, with the SAME distinct 404 / 503 /
    422 coded failures as the ficha compute path.
    """
    tipo = payload.tipo
    if tipo == "parcela":
        geojson_4326, geojson_32720, _area_m2 = _resolver_parcela(db, payload.nomenclatura)
        return geojson_4326, geojson_32720
    if tipo == "poligono":
        geojson_4326, geojson_32720, _area_m2 = _resolver_poligono(db, payload.geometry)
        return geojson_4326, geojson_32720
    if tipo == "canal_buffer":
        geojson_4326, geojson_32720, _area_m2 = _resolver_canal_buffer(
            db, payload.canal_ref, payload.buffer_m
        )
        return geojson_4326, geojson_32720
    geojson_4326, geojson_32720, _area_m2 = _resolver_canal_cuenca(
        db, payload.canal_ref, payload.variante
    )
    return geojson_4326, geojson_32720


def _clip_suelos(db: Session, geojson_4326: str) -> list[FichaOverlayFeature]:
    """Clip ``suelos_catastro`` to the geometry, one Feature per intersecting soil.

    ``clase`` reuses ``_normalizar_cap`` so the wire label matches the ficha soils
    panel exactly (``IVws`` → ``IV``; unclassified → ``"sin clasificar"``). Grouping
    is applied to the LABEL only: several soil polygons may share a ``clase``, which
    the frontend colors identically — the geometry is not re-unioned, so the
    already-valid PostGIS clip ships untouched. No intersecting rows → empty list.
    """
    with _traducir_fallas_db():
        filas = db.execute(_SUELOS_OVERLAY_SQL, {"geojson": geojson_4326}).all()

    features: list[FichaOverlayFeature] = []
    for cap, geojson in filas:
        if not geojson:  # defensive: WHERE already excludes empty clips
            continue
        prefijo = _normalizar_cap(cap)
        clase = prefijo if prefijo else _SIN_CLASIFICAR
        features.append(
            FichaOverlayFeature(properties={"clase": clase}, geometry=json.loads(geojson))
        )
    return features


def _overlay_suelos(
    db: Session, payload: FichaRequest, *, client_ip: str | None
) -> FichaOverlayResponse:
    """Soils overlay for a resolved geometry — SAME guard chain as the ficha.

    resolve geometry (404 if absent) → ``assert_within_caps`` (422, outside the
    semaphore) → audit COMMITTED (survives a later failure) → semaphore (503) →
    soils clip. Mirrors ``_ficha_de_geometria``: the LOCAL statement_timeout set
    before the audit commit is gone after it, so it is re-applied inside the
    semaphore before the clip (F1). The ``canal_cuenca`` stub has no geometry yet,
    so it keeps the audit + semaphore path and returns an EMPTY FeatureCollection.
    """
    _aplicar_statement_timeout(db)  # bounds the resolver query
    resuelto = _resolver_geometria_overlay(db, payload)
    if resuelto is None:
        escribir_auditoria(db, payload, client_ip=client_ip)
        with slot_de_computo():
            return FichaOverlayResponse(dataset="suelos", features=[])

    geojson_4326, geojson_32720 = resuelto
    geom_metrico = shape(json.loads(geojson_32720))
    assert_within_caps(geom_metrico, tipo=payload.tipo, buffer_m=getattr(payload, "buffer_m", None))

    escribir_auditoria(db, payload, client_ip=client_ip)
    with slot_de_computo():
        _aplicar_statement_timeout(db)  # re-apply: the audit COMMIT ended the prior LOCAL
        return FichaOverlayResponse(dataset="suelos", features=_clip_suelos(db, geojson_4326))


# ── on-map overlay (A(b) slice 2: flood_risk / drainage_need rasters) ────────


def _clip_raster(db: Session, tipo: str, geojson_4326: str) -> list[FichaOverlayFeature]:
    """Vectorize a raster (``flood_risk`` / ``drainage_need``) to per-class Features.

    Mirrors ``_raster_dataset``: resolve the newest registered raster (``None`` →
    ``sin_cobertura``, i.e. an EMPTY overlay, never a 503 — the 503 hard dependency
    is ``suelos_catastro``), then vectorize the SAME classified pixels the panel bins
    into dissolved GeoJSON polygons. ``clase`` is the ``RANGE_CONFIGS[tipo]`` label
    (Bajo/Medio/Alto/Crítico), so an overlay class equals the panel's ``RiesgoBins``
    class exactly. An unreadable raster is 503 ``raster_ilegible`` (§2.6), same as the
    ficha compute path; a zone that is empty / all-nodata / disjoint yields no features.
    """
    ruta = _raster_path(db, tipo)
    if ruta is None:
        return []
    try:
        vectorizado = vectorize_zonal_classes(
            ruta,
            json.loads(geojson_4326),
            RANGE_CONFIGS.get(tipo) or [],
            geom_crs="EPSG:4326",
        )
    except ficha_errors.FichaError:
        raise
    except Exception as exc:  # noqa: BLE001 — any read failure is 503 raster_ilegible (§2.6)
        logger.error("Raster ilegible para overlay de ficha", dataset=tipo, exc_info=True)
        raise ficha_errors.raster_ilegible(tipo) from exc

    return [
        FichaOverlayFeature(properties={"clase": feat["clase"]}, geometry=feat["geometry"])
        for feat in vectorizado
    ]


def _overlay_raster(
    db: Session, payload: FichaRequest, dataset: str, *, client_ip: str | None
) -> FichaOverlayResponse:
    """Raster overlay (flood_risk / drainage_need) — SAME guard chain as the soils overlay.

    resolve geometry (404 if absent) → ``assert_within_caps`` (422, outside the
    semaphore) → audit COMMITTED (survives a later failure) → semaphore (503) →
    raster vectorization. This is a SECOND raster mask pass (the ficha compute already
    masks flood/drainage for their bins), acceptable because it runs opt-in only, on
    the toggle, per the design. The ``canal_cuenca`` stub has no geometry yet, so it
    keeps the audit + semaphore path and returns an EMPTY FeatureCollection.
    """
    _aplicar_statement_timeout(db)  # bounds the resolver query
    resuelto = _resolver_geometria_overlay(db, payload)
    if resuelto is None:
        escribir_auditoria(db, payload, client_ip=client_ip)
        with slot_de_computo():
            return FichaOverlayResponse(dataset=dataset, features=[])

    geojson_4326, geojson_32720 = resuelto
    geom_metrico = shape(json.loads(geojson_32720))
    assert_within_caps(geom_metrico, tipo=payload.tipo, buffer_m=getattr(payload, "buffer_m", None))

    escribir_auditoria(db, payload, client_ip=client_ip)
    with slot_de_computo():
        _aplicar_statement_timeout(db)  # re-apply: the audit COMMIT ended the prior LOCAL
        return FichaOverlayResponse(
            dataset=dataset, features=_clip_raster(db, dataset, geojson_4326)
        )


def overlay_zona(
    db: Session, payload: FichaRequest, *, dataset: str, client_ip: str | None
) -> FichaOverlayResponse:
    """Opt-in on-map overlay of the analysis clipped to the zone (A(b)).

    Reuses the ficha's geometry resolvers, caps, audit and semaphore/timeout chain.
    ``dataset`` is validated in the router (422 otherwise) to one of ``suelos``
    (exact PostGIS vector clip) or ``flood_risk`` / ``drainage_need`` (raster
    vectorization per class). One dataset per call — the map paints a single overlay.
    """
    if dataset == "suelos":
        return _overlay_suelos(db, payload, client_ip=client_ip)
    return _overlay_raster(db, payload, dataset, client_ip=client_ip)
