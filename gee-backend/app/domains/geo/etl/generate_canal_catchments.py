"""Precompute the upstream hydrological catchment of every curated canal (A7).

Run it inside the deployed backend container — like ``generate_chirps_normals``
the runner lives under ``app/`` precisely so it exists inside the runtime image
(``gee-backend/Dockerfile`` copies only ``app/`` and ``alembic.ini``)::

    docker compose exec backend python -m app.domains.geo.etl.generate_canal_catchments

The backend container mounts ``geo-data:/data/geo``, so the ``flow_dir`` rasters
this reads and the seed/basins scratch rasters it writes all live on the same
volume the geo-worker produced.

**What it produces.** One ``canal_catchment`` row per curated canal (keyed by
``canal_ref``, the ``canal_consorcio.id`` string): the real upstream watershed of
the canal's trace, precomputed so the ``canal_cuenca`` ficha can look it up instead
of running WBT on the request path (a later slice wires the lookup). The recipe
per canal mirrors the pour-points build in
``calculations_hydrology_support.generar_zonificacion_impl``:

1. Rasterize the canal's LINESTRING onto the ``flow_dir`` grid as int16 seed cells
   — the WHOLE trace is the pour set (NO Jensen snapping, which would collapse the
   trace onto a single high-accumulation cell — JD-A-015).
2. ``wbt.watershed(d8_pntr=<flow_dir>, pour_pts=<seed>, output=<basins>)`` — the
   D8 flow-direction POINTER as arg 1, explicitly NOT the DEM (the historical D8
   miscall this whole feature was blocked on).
3. Polygonize the basins raster, dissolve to one MultiPolygon, measure ``area_ha``
   in EPSG:32720 (the projection the whole ficha uses).
4. Simplify the dissolved basin (topology-preserving, at
   :data:`CATCHMENT_SIMPLIFY_TOLERANCE_M` in EPSG:32720) so the
   raw pixel-boundary staircase — whose vertex count scales with basin perimeter
   and routinely blows past the vertex cap — collapses to a
   low-vertex outline; then gate the SIMPLIFIED geometry against EVERY read-path
   cap ``ficha_service.assert_within_caps(tipo='canal_cuenca')`` enforces:
   ``ficha_max_area_ha`` AND the per-``tipo`` envelope cap
   (``ficha_service.envelope_cap_ha('canal_cuenca')`` →
   ``ficha_max_envelope_ha_cuenca``) AND the per-``tipo`` vertex cap
   (``ficha_service.vertices_cap('canal_cuenca')`` →
   ``ficha_max_vertices_cuenca``).
   If the simplified basin exceeds ANY of those it is ``oversized``: the row is
   stored WITHOUT its geometry (``geometria`` NULL, ``area_ha`` kept for audit).
   A stored (non-oversized) catchment is therefore GUARANTEED to pass
   ``assert_within_caps`` at read time — producer and consumer read the SAME
   settings, so the "stored ⟹ servable" invariant can never drift.
   Every rejection emits ONE ``canal_catchment.oversized`` log event naming the
   canal, the measured ``area_ha`` / ``envelope_ha`` / ``vertices`` (each beside
   its cap) and the ``motivo``(s) that fired — a bare total cannot tell "too big
   by design" apart from "blocked by the envelope or the vertex cap", which is
   exactly the question a re-run has to answer.
5. UPSERT onto ``(canal_ref, variante)``.

**V1 flow_dir policy — one base raster for all 60 canals.** The consorcio manages
41 relevados + 19 propuestos; v1 computes EVERY catchment against the NATURAL
``natural_flow_dir_{area}`` raster — the drainage of the terrain WITHOUT any canal
burned in. That is a deliberate deployment choice, not a shortcut: the operator
distrusts stream burning, so the burned/relevado and escenario variants were pruned
and natural is the only registered, trusted base (see
:func:`_flow_dir_layer_names`, which prefers it and keeps the bare
``flow_dir_{area}`` only as a fallback for a deployment that registered just the
base raster). The per-canal escenario refinement is deferred. ``variante`` is kept
as a column but stamped with the single v1 value :data:`V1_VARIANTE` (``natural``).
The ``--estado`` flag only scopes WHICH ``canal_consorcio`` rows are processed; it
does not change the raster or the stored ``variante``.

**Resumable + idempotent (the ``version`` key).** ``version`` is the id of the
``flow_dir`` ``geo_layers`` row the catchment was derived from. A fresh terrain
run mints a NEW ``geo_layers`` row (a new UUID), so re-running the batch:

* SKIPS a canal whose current ``canal_catchment`` row already carries this
  ``version`` (same pointer → nothing changed), and
* RECOMPUTES (UPSERT) when the ``flow_dir`` pointer changed (new layer id → new
  ``version``).

Progress is committed per canal, so a crash mid-run leaves every finished canal
persisted and a re-run picks up where it stopped. ``--limit`` / ``--canal-ref``
scope a test run.

``--force`` overrides the skip. The version key tracks the POINTER, and NOTHING
else: the read-path caps AND :data:`CATCHMENT_SIMPLIFY_TOLERANCE_M` both live
OUTSIDE it. So after a cap change (the batch-4 envelope widening) or a tolerance
change (batch 4d, 8 m → 20 m) a plain re-run skips all 60 rows and keeps the
previous ``oversized`` verdicts and the previously stored geometries — the new
value is INERT until the rows are recomputed. Re-gating stored catchments against
new caps or a new tolerance therefore requires
``python -m app.domains.geo.etl.generate_canal_catchments --force``, once, by hand
(the weekly cron in ``deploy/etl-refresh.sh`` deliberately does NOT pass it).

Exit codes:
    0  success — every in-scope canal computed or skipped, no failures
    1  prerequisite missing — no base ``flow_dir`` layer for the area, or its
       raster is unreadable (nothing was written)
    2  invalid invocation
    3  one or more canals failed to compute (the rest were still committed) — a
       re-run retries only the failures
"""

from __future__ import annotations

import argparse
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any, Callable, Sequence

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.domains.geo.models import TipoGeoLayer
from app.domains.geo.repository import GeoRepository

logger = structlog.get_logger(__name__)

EXIT_OK = 0
EXIT_PREREQ_FAILED = 1
EXIT_USAGE = 2
EXIT_FAILED = 3

#: Root of the ``geo-data`` volume the backend and geo-worker share.
GEO_DATA_ROOT = "/data/geo"

#: Default processing area. The DEM pipeline writes ``flow_dir`` under this area's
#: ``output/`` directory; override with ``--area-id`` for a differently
#: partitioned deployment.
DEFAULT_AREA_ID = "zona_principal"

#: The single ``variante`` v1 stamps on every catchment. All 60 canals are computed
#: against the NATURAL ``flow_dir`` raster (terrain without canals burned in) — the
#: burned/relevado + escenario variants were pruned from this deployment (the
#: operator distrusts stream burning), so natural is the registered + trusted base.
#: The per-canal escenario refinement is deferred (kept as a column for it).
V1_VARIANTE = "natural"

#: ``canal_consorcio.estado`` values that ``--estado`` may scope the run to.
CANAL_ESTADOS = ("relevado", "propuesto")

#: Hectares per square metre denominator (a hectare is 10 000 m²).
M2_PER_HA = 10_000.0

#: Topology-preserving simplify tolerance (metres, EPSG:32720) applied to the
#: dissolved catchment BEFORE it is measured, cap-gated and stored. The raw basin
#: is a pixel-boundary staircase whose vertex count scales with basin perimeter —
#: so any real basin exceeds the vertex cap, and the staircase has to be
#: collapsed before the read-path caps are measured.
#:
#: WHY 20 m AND NOT THE 8 m THIS STARTED AT (batch 4d). The per-motivo breakdown
#: `_read_path_cap_report` added turned "35 oversized" into a measurement:
#: ``{area: 16, envelope: 0, vertices: 35}``. Read it carefully — envelope is
#: ZERO, so the envelope cap rejects NOTHING; all 35 fail the vertex cap, and 19
#: of them have a perfectly sane area (only 16 are genuinely too big by area).
#: Those 19 are rescuable, and the ONE thing standing between them and a servable
#: geometry is vertex count post-simplify. 8 m was inherited from the soils
#: on-map overlay (``ficha_service._SUELOS_OVERLAY_SQL``), where the polygons are
#: small parcels; a canal catchment is a basin of THOUSANDS of hectares, and at
#: the zoom levels a whole-basin ficha is ever drawn at, 20 m of boundary
#: displacement is well under one screen pixel — visually invisible, and still
#: below the flow_dir grid's own cell size (the DEM is COPERNICUS/DEM/GLO30, so
#: the staircase steps are ~30 m), meaning we are shaving rasterization noise,
#: not real basin shape. Raising the tolerance was the cheap lever precisely
#: because it touched NO cap, so the "stored ⟹ servable" invariant enforced by
#: the cap mirror in `_read_path_cap_report` stayed intact. The lesson from the
#: breakdown: relaxing the envelope cap (the intuitive first guess) would have
#: rescued zero canals.
#:
#: WHAT 20 m ACTUALLY RESCUED, AND WHAT IT DID NOT. The re-run at this tolerance
#: recovered 12 of the 19: 7 catchments stayed blocked by the vertex cap ALONE,
#: at 1 008-1 883 vertices against the 1 000 cap (Candil 1 860, La Sara 1 766,
#: N8 1 766, S4 1 206, +3), every one of them well under the area cap
#: (11.4k-19.2k ha). Those 7 are dendritic: their perimeter, not their size,
#: drives the vertex count, so shaving harder would have started eating real
#: basin shape. They were rescued instead by the per-``tipo`` vertex cap
#: (``ficha_max_vertices_cuenca`` = 2 000, read through
#: ``ficha_service.vertices_cap``) — the same per-``tipo`` move as the envelope,
#: and safe for the same reason: a catchment is precomputed server-side, never
#: caller-supplied. The 16 over the area cap remain oversized BY DESIGN; the
#: area cap is still untouched.
CATCHMENT_SIMPLIFY_TOLERANCE_M = 20.0

#: Log a heartbeat every this many canals.
LOG_EVERY = 50

#: Read-path cap names, as they appear in the ``canal_catchment.oversized`` log
#: event and in the per-motivo breakdown of the run summary.
CAP_MOTIVO_AREA = "area"
CAP_MOTIVO_ENVELOPE = "envelope"
CAP_MOTIVO_VERTICES = "vertices"
#: Evaluation order — also the order ``motivos`` lists them in.
CAP_MOTIVOS = (CAP_MOTIVO_AREA, CAP_MOTIVO_ENVELOPE, CAP_MOTIVO_VERTICES)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class BatchResult:
    """Tally returned by :func:`generate_catchments` and mapped to an exit code."""

    total: int = 0
    computed: int = 0
    skipped: int = 0
    oversized: int = 0
    empty: int = 0
    failed: int = 0
    failed_canal_refs: list[str] = field(default_factory=list)
    #: How many oversized catchments each cap rejected (T6). A catchment that
    #: breaks two caps counts under BOTH, so the values sum to >= ``oversized``.
    oversized_por_motivo: dict[str, int] = field(
        default_factory=lambda: dict.fromkeys(CAP_MOTIVOS, 0)
    )


@dataclass(frozen=True)
class _CapReport:
    """What every read-path cap measured for one catchment, and which ones failed.

    Exists because "35 oversized" is not an actionable number: the operator needs
    to know whether to relax the vertex cap, simplify harder, or accept the
    result — and that depends on WHICH cap rejected each canal.
    """

    area_ha: float
    envelope_ha: float
    vertices: int
    max_area_ha: float
    max_envelope_ha: float
    max_vertices: int
    #: Every failing cap, in :data:`CAP_MOTIVOS` order. Empty ⇒ servable.
    motivos: tuple[str, ...]

    @property
    def oversized(self) -> bool:
        return bool(self.motivos)

    @property
    def motivo(self) -> str | None:
        """The FIRST failing cap — the single-value field for grouping/filters."""
        return self.motivos[0] if self.motivos else None


@dataclass
class _FlowDirGrid:
    """The flow_dir raster's grid — everything the seed rasterization needs."""

    path: str
    epsg: int
    width: int
    height: int
    transform: Any
    seed_meta: dict


# ─────────────────────────────────────────────────────────────────────────────
# Dependency resolution (tests inject fakes; production gets the real modules)
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_io(
    rasterio_module: Any,
    rasterize_fn: Callable[..., Any] | None,
    shapes_fn: Callable[..., Any] | None,
    get_wbt: Callable[[], Any] | None,
) -> tuple[Any, Callable[..., Any], Callable[..., Any], Callable[[], Any]]:
    """Fill any un-injected raster/WBT dependency with the real implementation.

    Keeps the imports lazy — no rasterio or WhiteboxTools at module import time.
    """
    if rasterio_module is None:
        import rasterio as rasterio_module  # noqa: PLC0415
    if rasterize_fn is None or shapes_fn is None:
        from rasterio.features import rasterize as _rasterize  # noqa: PLC0415
        from rasterio.features import shapes as _shapes  # noqa: PLC0415

        rasterize_fn = rasterize_fn or _rasterize
        shapes_fn = shapes_fn or _shapes
    if get_wbt is None:
        from app.domains.geo.intelligence.calculations import _get_wbt  # noqa: PLC0415

        get_wbt = _get_wbt
    return rasterio_module, rasterize_fn, shapes_fn, get_wbt


def _flow_dir_layer_names(area_id: str) -> tuple[str, ...]:
    """The ``geo_layers.nombre`` candidates for v1, most-preferred first.

    V1 uses the NATURAL ``flow_dir`` (``natural_flow_dir_{area}``) — the drainage of
    the terrain WITHOUT canals burned in. This deployment pruned the burned/relevado
    layer, keeping only natural. The base ``flow_dir_{area}`` is a fallback for a
    deployment that only registered the base raster.
    """
    return (f"natural_flow_dir_{area_id}", f"flow_dir_{area_id}")


def resolve_flow_dir_layer(db: Session, area_id: str, *, repo: GeoRepository):
    """Return the v1 ``flow_dir`` ``GeoLayer`` for ``area_id`` or ``None``.

    Prefers the NATURAL raster (``natural_flow_dir_{area}``), falling back to the base
    ``flow_dir_{area}``. Every catchment is computed against the resolved raster.
    """
    for nombre in _flow_dir_layer_names(area_id):
        layer = repo.get_layer_by_nombre(db, nombre)
        if layer is not None and layer.tipo == TipoGeoLayer.FLOW_DIR.value:
            return layer
    return None


def _open_flow_dir_grid(flow_dir_path: str, *, rasterio_module: Any) -> _FlowDirGrid:
    """Read the flow_dir raster's grid so the canal seed lands on the same cells."""
    with rasterio_module.open(flow_dir_path) as src:
        crs = src.crs
        epsg = crs.to_epsg()
        transform = src.transform
        width, height = src.width, src.height
        meta = src.meta.copy()
    if epsg is None:
        raise RuntimeError(f"flow_dir raster {flow_dir_path} has no EPSG code")
    # area_ha (and the oversized gate that hinges on it) is measured in this CRS.
    # A geographic CRS (degrees) would make both garbage, so refuse to run rather
    # than silently compute nonsense areas. Prod flow_dir is EPSG:32720 (projected)
    # so this never fires there — it guards a misconfigured deployment. We do NOT
    # auto-reproject; a metric CRS is a hard prerequisite.
    from pyproj import CRS as _PyprojCRS  # noqa: PLC0415

    if not _PyprojCRS.from_epsg(int(epsg)).is_projected:
        raise RuntimeError(
            f"flow_dir raster {flow_dir_path} CRS EPSG:{epsg} is geographic, not "
            "projected/metric; area_ha and the oversized gate require a projected "
            "CRS (prod uses EPSG:32720). Refusing to run — reproject the raster to "
            "a metric CRS first."
        )
    meta.update({"dtype": "int16", "count": 1, "nodata": 0})
    return _FlowDirGrid(
        path=flow_dir_path,
        epsg=int(epsg),
        width=int(width),
        height=int(height),
        transform=transform,
        seed_meta=meta,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Per-canal computation
# ─────────────────────────────────────────────────────────────────────────────


def _canal_line_in_grid_crs(db: Session, canal_ref: str, epsg: int):
    """Return the canal trace as a shapely geometry in the flow_dir CRS, or ``None``.

    ``geom IS NULL`` (a row with no trace) yields ``None`` — the same "no canal"
    treatment ``canal_buffer`` uses. PostGIS does the reprojection so the seed lines
    up exactly with the metric ``flow_dir`` grid.
    """
    from shapely.geometry import shape  # noqa: PLC0415

    row = db.execute(
        text(
            "SELECT ST_AsGeoJSON(ST_Transform(geom, :epsg)) AS g "
            "FROM canal_consorcio WHERE id = :ref AND geom IS NOT NULL LIMIT 1"
        ),
        {"epsg": epsg, "ref": canal_ref},
    ).one_or_none()
    if row is None or row.g is None:
        return None
    import json  # noqa: PLC0415

    return shape(json.loads(row.g))


def _dissolve_basins(
    basins_path: str,
    *,
    rasterio_module: Any,
    shapes_fn: Callable[..., Any],
):
    """Polygonize the WBT basins raster and dissolve it to one MultiPolygon.

    Returns ``(multipolygon_or_None, area_ha)`` in the raster's (metric) CRS.
    """
    from shapely.geometry import MultiPolygon, shape  # noqa: PLC0415
    from shapely.ops import unary_union  # noqa: PLC0415

    with rasterio_module.open(basins_path) as src:
        data = src.read(1)
        transform = src.transform

    polygons = [
        shape(geom)
        for geom, value in shapes_fn(data, mask=data > 0, transform=transform)
        if value > 0
    ]
    if not polygons:
        return None, 0.0

    dissolved = unary_union(polygons)
    if dissolved.is_empty:
        return None, 0.0
    if dissolved.geom_type == "Polygon":
        dissolved = MultiPolygon([dissolved])
    area_ha = dissolved.area / M2_PER_HA
    return dissolved, area_ha


def _simplify_catchment(dissolved: Any) -> tuple[Any, float]:
    """Topology-preserving simplify of a dissolved catchment, in its metric CRS.

    ``dissolved`` is a (Multi)Polygon in EPSG:32720. Collapses the pixel staircase
    at :data:`CATCHMENT_SIMPLIFY_TOLERANCE_M` (catchment-only: this tolerance is
    NOT shared with any other consumer — the soils overlay keeps its own 8 m in
    ``ficha_service``), heals any simplify self-touch with
    ``buffer(0)``, and re-coerces to MultiPolygon. Returns ``(simplified, area_ha)``
    measured on the SIMPLIFIED geometry (the value that is stored and gated). Falls
    back to the raw geometry if simplify degenerates to empty (never expected for a
    real basin — the cap gate then still runs on the raw shape).
    """
    from shapely.geometry import MultiPolygon  # noqa: PLC0415

    simplified = dissolved.simplify(CATCHMENT_SIMPLIFY_TOLERANCE_M, preserve_topology=True).buffer(
        0
    )
    if simplified.is_empty:
        return dissolved, dissolved.area / M2_PER_HA
    if simplified.geom_type == "Polygon":
        simplified = MultiPolygon([simplified])
    return simplified, simplified.area / M2_PER_HA


def _read_path_cap_report(geom: Any, area_ha: float, max_area_ha: float) -> _CapReport:
    """Measure ``geom`` against EVERY read-path cap and name the ones it fails.

    Mirrors what ``ficha_service.assert_within_caps`` enforces for
    ``tipo=canal_cuenca`` — area, envelope AND vertices — reusing the SAME
    ``settings`` thresholds and the SAME vertex counter
    (``_contar_vertices_shapely``) so producer and consumer can never drift.

    NO SHORT-CIRCUIT, on purpose (batch 4 / T6): the boolean gate this replaced
    returned at the first failing rule, so a re-run that reported "35 oversized"
    could not say WHICH cap rejected which canal — 19 of those 35 were under the
    area cap and nobody could tell whether the envelope or the vertex count had
    blocked them. Every rule is evaluated and every failure is named; the caller
    logs the report per canal.
    """
    from app.domains.geo.ficha_service import (  # noqa: PLC0415
        _contar_vertices_shapely,
        envelope_cap_ha,
        vertices_cap,
    )

    minx, miny, maxx, maxy = geom.bounds
    envelope_ha = abs((maxx - minx) * (maxy - miny)) / M2_PER_HA
    # Per-``tipo`` envelope cap, read through the read-path helper so the
    # wider catchment envelope can never drift from what the ficha enforces.
    max_envelope_ha = envelope_cap_ha("canal_cuenca")
    vertices = _contar_vertices_shapely(geom)
    # Per-``tipo`` vertex cap, read through the same read-path helper for the
    # same reason as the envelope: the wider catchment cap cannot drift from
    # what the ficha enforces.
    max_vertices = vertices_cap("canal_cuenca")

    motivos: list[str] = []
    if area_ha > max_area_ha:
        motivos.append(CAP_MOTIVO_AREA)
    if envelope_ha > max_envelope_ha:
        motivos.append(CAP_MOTIVO_ENVELOPE)
    if vertices > max_vertices:
        motivos.append(CAP_MOTIVO_VERTICES)

    return _CapReport(
        area_ha=area_ha,
        envelope_ha=envelope_ha,
        vertices=vertices,
        max_area_ha=max_area_ha,
        max_envelope_ha=max_envelope_ha,
        max_vertices=max_vertices,
        motivos=tuple(motivos),
    )


def _exceeds_read_path_caps(geom: Any, area_ha: float, max_area_ha: float) -> bool:
    """True when ``geom`` would fail ``ficha_service.assert_within_caps``.

    Thin boolean view of :func:`_read_path_cap_report` — kept because "does this
    pass?" is the question most callers (and tests) ask.
    """
    return _read_path_cap_report(geom, area_ha, max_area_ha).oversized


def _upsert_catchment(
    db: Session,
    *,
    canal_ref: str,
    variante: str,
    metric_geojson: str | None,
    epsg: int,
    area_ha: float,
    oversized: bool,
    flow_dir_layer_id: uuid.UUID,
    version: str,
) -> None:
    """UPSERT the catchment onto ``(canal_ref, variante)``.

    When ``metric_geojson`` is ``None`` (oversized or empty basin) the geometry is
    stored NULL; otherwise the metric polygon is reprojected to 4326 in PostGIS
    and coerced to MultiPolygon.
    """
    geom_sql = (
        "ST_Multi(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(:geojson), :epsg), 4326))"
        if metric_geojson is not None
        else "NULL"
    )
    db.execute(
        text(
            f"""
            INSERT INTO canal_catchment
                (id, canal_ref, variante, geometria, area_ha, oversized,
                 flow_dir_layer_id, version)
            VALUES
                (:id, :canal_ref, :variante, {geom_sql}, :area_ha, :oversized,
                 :flow_dir_layer_id, :version)
            ON CONFLICT (canal_ref, variante) DO UPDATE SET
                geometria = EXCLUDED.geometria,
                area_ha = EXCLUDED.area_ha,
                oversized = EXCLUDED.oversized,
                flow_dir_layer_id = EXCLUDED.flow_dir_layer_id,
                version = EXCLUDED.version,
                updated_at = now()
            """
        ),
        {
            "id": uuid.uuid4(),
            "canal_ref": canal_ref,
            "variante": variante,
            "geojson": metric_geojson,
            "epsg": epsg,
            "area_ha": area_ha,
            "oversized": oversized,
            "flow_dir_layer_id": flow_dir_layer_id,
            "version": version,
        },
    )


def _existing_version(db: Session, canal_ref: str, variante: str) -> str | None:
    row = db.execute(
        text(
            "SELECT version FROM canal_catchment WHERE canal_ref = :ref AND variante = :v LIMIT 1"
        ),
        {"ref": canal_ref, "v": variante},
    ).one_or_none()
    return row.version if row is not None else None


def _in_scope_canal_refs(
    db: Session, *, canal_ref: str | None, estado: str | None, limit: int | None
) -> list[str]:
    clauses = ["geom IS NOT NULL"]
    params: dict[str, Any] = {}
    if canal_ref is not None:
        clauses.append("id = :ref")
        params["ref"] = canal_ref
    if estado is not None:
        clauses.append("estado = :estado")
        params["estado"] = estado
    sql = f"SELECT id FROM canal_consorcio WHERE {' AND '.join(clauses)} ORDER BY id"
    if limit is not None:
        sql += " LIMIT :limit"
        params["limit"] = limit
    return [str(r.id) for r in db.execute(text(sql), params)]


def generate_catchments(
    db: Session,
    *,
    area_id: str = DEFAULT_AREA_ID,
    estado: str | None = None,
    limit: int | None = None,
    canal_ref: str | None = None,
    force: bool = False,
    max_area_ha: float | None = None,
    rasterio_module: Any = None,
    rasterize_fn: Callable[..., Any] | None = None,
    shapes_fn: Callable[..., Any] | None = None,
    get_wbt: Callable[[], Any] | None = None,
    log_every: int = LOG_EVERY,
) -> BatchResult:
    """Precompute (or refresh) curated-canal catchments for ``area_id``.

    Every catchment is computed against the NATURAL ``natural_flow_dir_{area}``
    raster (terrain without canals burned in — this deployment pruned the burned
    variants; ``flow_dir_{area}`` is only a fallback) and stamped with
    :data:`V1_VARIANTE` (``natural``). ``estado`` optionally scopes which
    ``canal_consorcio`` rows are processed (it does not change the raster or the
    stored variante).

    Raises ``RuntimeError`` on a prerequisite failure (no flow_dir layer/raster);
    per-canal failures are caught, logged, counted, and do NOT abort the batch —
    a re-run retries only the failures. Progress is committed per canal.
    """
    if estado is not None and estado not in CANAL_ESTADOS:
        raise ValueError(f"unknown estado {estado!r}; expected one of {CANAL_ESTADOS}")

    variante = V1_VARIANTE
    max_area_ha = settings.ficha_max_area_ha if max_area_ha is None else max_area_ha
    rasterio_module, rasterize_fn, shapes_fn, get_wbt = _resolve_io(
        rasterio_module, rasterize_fn, shapes_fn, get_wbt
    )

    repo = GeoRepository()
    flow_dir_layer = resolve_flow_dir_layer(db, area_id, repo=repo)
    if flow_dir_layer is None:
        raise RuntimeError(
            f"no flow_dir layer for area_id={area_id!r}; run the terrain pipeline first"
        )

    version = str(flow_dir_layer.id)
    grid = _open_flow_dir_grid(flow_dir_layer.archivo_path, rasterio_module=rasterio_module)

    canal_refs = _in_scope_canal_refs(db, canal_ref=canal_ref, estado=estado, limit=limit)
    result = BatchResult(total=len(canal_refs))
    logger.info(
        "canal_catchment.start",
        area_id=area_id,
        variante=variante,
        estado=estado,
        version=version,
        canales=result.total,
    )

    import tempfile  # noqa: PLC0415

    for index, ref in enumerate(canal_refs, start=1):
        # Heartbeat BEFORE the resume-skip so a long resume (many already done
        # canals) still shows liveness — otherwise the operator sees no log until
        # the first canal that needs recompute.
        if index % log_every == 0:
            logger.info(
                "canal_catchment.progress",
                done=index,
                total=result.total,
                computed=result.computed,
                skipped=result.skipped,
            )
        # ``force`` overrides the resume-skip. The skip key is the flow_dir
        # version, so when NOTHING about the pointer changed but the CAPS did
        # (e.g. the catchment envelope cap was widened), a plain re-run would
        # skip all 60 rows and silently keep the old oversized verdicts.
        if not force and _existing_version(db, ref, variante) == version:
            result.skipped += 1
            continue
        try:
            _compute_one(
                db,
                canal_ref=ref,
                variante=variante,
                grid=grid,
                version=version,
                flow_dir_layer_id=flow_dir_layer.id,
                max_area_ha=max_area_ha,
                result=result,
                rasterio_module=rasterio_module,
                rasterize_fn=rasterize_fn,
                shapes_fn=shapes_fn,
                get_wbt=get_wbt,
                tempfile_module=tempfile,
            )
            db.commit()
        except Exception:
            db.rollback()
            result.failed += 1
            result.failed_canal_refs.append(ref)
            logger.error("canal_catchment.canal_failed", canal_ref=ref, exc_info=True)

    logger.info(
        "canal_catchment.done",
        area_id=area_id,
        variante=variante,
        computed=result.computed,
        skipped=result.skipped,
        oversized=result.oversized,
        # Per-cap breakdown (T6) — a catchment failing two caps counts in both.
        oversized_por_motivo=dict(result.oversized_por_motivo),
        empty=result.empty,
        failed=result.failed,
    )
    return result


def _compute_one(
    db: Session,
    *,
    canal_ref: str,
    variante: str,
    grid: _FlowDirGrid,
    version: str,
    flow_dir_layer_id: uuid.UUID,
    max_area_ha: float,
    result: BatchResult,
    rasterio_module: Any,
    rasterize_fn: Callable[..., Any],
    shapes_fn: Callable[..., Any],
    get_wbt: Callable[[], Any],
    tempfile_module: Any,
) -> None:
    """Compute and upsert ONE canal's catchment. Raises on any failure."""
    import json  # noqa: PLC0415

    from shapely.geometry import mapping  # noqa: PLC0415

    line = _canal_line_in_grid_crs(db, canal_ref, grid.epsg)
    if line is None or line.is_empty:
        # No trace to seed — nothing to compute (treated like a missing canal).
        result.empty += 1
        _upsert_catchment(
            db,
            canal_ref=canal_ref,
            variante=variante,
            metric_geojson=None,
            epsg=grid.epsg,
            area_ha=0.0,
            oversized=False,
            flow_dir_layer_id=flow_dir_layer_id,
            version=version,
        )
        return

    with tempfile_module.TemporaryDirectory() as tmpdir:
        seed_path = str(Path(tmpdir) / "canal_seed.tif")
        basins_path = str(Path(tmpdir) / "canal_basins.tif")

        # The WHOLE canal trace is the pour set (no Jensen snapping — JD-A-015).
        seed = rasterize_fn(
            [(mapping(line), 1)],
            out_shape=(grid.height, grid.width),
            transform=grid.transform,
            fill=0,
            dtype="int16",
            all_touched=True,
        )
        with rasterio_module.open(seed_path, "w", **grid.seed_meta) as dst:
            dst.write(seed, 1)

        # THE D8 POINTER (flow_dir) as arg 1 — explicitly not the DEM.
        get_wbt().watershed(grid.path, seed_path, basins_path)

        dissolved, area_ha = _dissolve_basins(
            basins_path, rasterio_module=rasterio_module, shapes_fn=shapes_fn
        )

    if dissolved is None:
        result.empty += 1
        _upsert_catchment(
            db,
            canal_ref=canal_ref,
            variante=variante,
            metric_geojson=None,
            epsg=grid.epsg,
            area_ha=0.0,
            oversized=False,
            flow_dir_layer_id=flow_dir_layer_id,
            version=version,
        )
        return

    # Simplify FIRST (drops the pixel staircase), then gate the simplified shape
    # against ALL read-path caps assert_within_caps(tipo="canal_cuenca") enforces —
    # area, envelope AND vertices — so a stored (non-oversized) catchment is
    # guaranteed to pass at read time. area_ha is reported off the simplified geom.
    dissolved, area_ha = _simplify_catchment(dissolved)
    report = _read_path_cap_report(dissolved, area_ha, max_area_ha)
    oversized = report.oversized
    metric_geojson = None if oversized else json.dumps(mapping(dissolved))
    _upsert_catchment(
        db,
        canal_ref=canal_ref,
        variante=variante,
        metric_geojson=metric_geojson,
        epsg=grid.epsg,
        area_ha=area_ha,
        oversized=oversized,
        flow_dir_layer_id=flow_dir_layer_id,
        version=version,
    )
    if oversized:
        result.oversized += 1
        for motivo in report.motivos:
            result.oversized_por_motivo[motivo] = result.oversized_por_motivo.get(motivo, 0) + 1
        # ONE structured event per rejected canal (T6). Without it a run could
        # only report a total, and 19 of the 35 rejections in prod were under the
        # area cap with nobody able to say which of the other two caps fired.
        # The measured value AND its cap travel together so the log is readable
        # without going to look up the settings.
        logger.warning(
            "canal_catchment.oversized",
            canal_ref=canal_ref,
            variante=variante,
            motivo=report.motivo,
            motivos=list(report.motivos),
            area_ha=round(report.area_ha, 2),
            max_area_ha=round(report.max_area_ha, 2),
            envelope_ha=round(report.envelope_ha, 2),
            max_envelope_ha=round(report.max_envelope_ha, 2),
            vertices=report.vertices,
            max_vertices=report.max_vertices,
        )
    result.computed += 1


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.domains.geo.etl.generate_canal_catchments",
        description=(
            "Precomputa la cuenca hidrologica aguas-arriba de cada canal curado "
            "del consorcio (canal_catchment) usando WBT watershed sobre el puntero "
            "D8 flow_dir NATURAL (terreno sin canales quemados)."
        ),
    )
    parser.add_argument(
        "--area-id",
        default=DEFAULT_AREA_ID,
        help=f"Area de procesamiento (subdirectorio de /data/geo). Por defecto {DEFAULT_AREA_ID!r}.",
    )
    parser.add_argument(
        "--estado",
        choices=CANAL_ESTADOS,
        default=None,
        help="Acota los canales procesados por estado (relevado/propuesto). Por "
        "defecto procesa los 60. No cambia el raster ni la variante almacenada.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Procesar como maximo N canales (para pruebas).",
    )
    parser.add_argument(
        "--canal-ref",
        default=None,
        help="Procesar un unico canal por id de canal_consorcio (para pruebas).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recalcular incluso las cuencas ya almacenadas para esta version de "
        "flow_dir. Necesario cuando cambian los CAPS o la TOLERANCIA de simplify "
        "(no el puntero): sin esto el resume las omite, el valor nuevo queda "
        "INERTE y se conserva el veredicto oversized anterior.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.limit is not None and args.limit <= 0:
        print(f"INVOCACION INVALIDA: --limit ({args.limit}) debe ser > 0", file=sys.stderr)
        return EXIT_USAGE

    from app.db.session import SessionLocal  # noqa: PLC0415

    with SessionLocal() as db:
        try:
            result = generate_catchments(
                db,
                area_id=args.area_id,
                estado=args.estado,
                limit=args.limit,
                canal_ref=args.canal_ref,
                force=args.force,
            )
        except RuntimeError as exc:
            print(
                f"PREREQUISITO FALTANTE: {exc}\n"
                "no se escribio ninguna cuenca (falla previa a cualquier calculo).",
                file=sys.stderr,
            )
            return EXIT_PREREQ_FAILED
        except Exception as exc:  # noqa: BLE001 — the exit code IS the handling
            print(f"FALLO EN LA GENERACION: {type(exc).__name__}: {exc}", file=sys.stderr)
            return EXIT_FAILED

    # Per-motivo breakdown so the operator can decide (relax vertices / simplify
    # harder / accept) straight off the run summary instead of grepping the logs.
    desglose = ", ".join(
        f"{motivo}={result.oversized_por_motivo.get(motivo, 0)}" for motivo in CAP_MOTIVOS
    )
    # El desglose puede sumar MAS que el total y eso no es un bug: una cuenca que
    # rompe dos caps se cuenta en los dos. Se dice en la misma linea porque el
    # operador la lee sola, sin este archivo al lado.
    print(
        f"canal_catchment area_id={args.area_id!r} variante={V1_VARIANTE!r}: "
        f"{result.computed} calculadas ({result.oversized} oversized "
        f"[{desglose} — la suma puede superar el total: una cuenca puede fallar "
        f"varios caps], {result.empty} vacias), "
        f"{result.skipped} omitidas, {result.failed} fallidas de {result.total} canales."
    )
    return EXIT_FAILED if result.failed else EXIT_OK


if __name__ == "__main__":  # pragma: no cover — module entry point
    raise SystemExit(main())
