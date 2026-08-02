"""Precompute the upstream hydrological catchment of every canal (A7, slice 1).

Run it inside the deployed backend container — like ``generate_chirps_normals``
the runner lives under ``app/`` precisely so it exists inside the runtime image
(``gee-backend/Dockerfile`` copies only ``app/`` and ``alembic.ini``)::

    docker compose exec backend python -m app.domains.geo.etl.generate_canal_catchments

The backend container mounts ``geo-data:/data/geo``, so the ``flow_dir`` rasters
this reads and the seed/basins scratch rasters it writes all live on the same
volume the geo-worker produced.

**What it produces.** One ``canal_catchment`` row per ``canal × variante``: the
real upstream watershed of the canal's trace, precomputed so the ``canal_cuenca``
ficha can look it up instead of running WBT on the request path (slice 2 wires the
lookup). The recipe per canal, mirroring the pour-points build in
``calculations_hydrology_support.generar_zonificacion_impl``:

1. Rasterize the canal's LINESTRING onto the variant's ``flow_dir`` grid as int16
   seed cells — the WHOLE trace is the pour set (NO Jensen snapping, which would
   collapse the trace onto a single high-accumulation cell — JD-A-015).
2. ``wbt.watershed(d8_pntr=<flow_dir>, pour_pts=<seed>, output=<basins>)`` — the
   D8 flow-direction POINTER as arg 1, explicitly NOT the DEM (the historical D8
   miscall this whole feature was blocked on).
3. Polygonize the basins raster, dissolve to one MultiPolygon, measure ``area_ha``
   in EPSG:32720 (the projection the whole ficha uses).
4. If ``area_ha`` exceeds ``settings.ficha_max_area_ha`` (20 000) the basin is
   ``oversized``: the row is stored WITHOUT its multi-MB geometry (the ficha would
   reject it anyway), ``geometria`` NULL, ``area_ha`` kept for audit.
5. UPSERT onto ``(canal_id, variante)``.

**Variante → flow_dir raster.** ``natural`` is the drainage WITHOUT the canal
network burned into the DEM; ``relevado`` is WITH it. They never share a
catchment, so the precompute resolves the matching raster and never silently
falls back across variants:

* ``natural``  → the ``natural_flow_dir_{area}`` layer if it exists; else the base
  ``flow_dir_{area}`` (when no canals were burned the base DEM already IS the
  natural hydrology, so base == natural — a legitimate, not silent, fallback).
* ``relevado`` → the base ``flow_dir_{area}`` layer (burned/operational drainage).

**Resumable + idempotent (the ``version`` key).** ``version`` is the id of the
``flow_dir`` ``geo_layers`` row the catchment was derived from. A fresh terrain
run mints a NEW ``geo_layers`` row (a new UUID), so re-running the batch:

* SKIPS a canal whose current ``canal_catchment`` row already carries this
  ``version`` (same pointer → nothing changed), and
* RECOMPUTES (UPSERT) when the ``flow_dir`` pointer changed (new layer id → new
  ``version``).

Progress is committed per canal, so a crash mid-run leaves every finished canal
persisted and a re-run picks up where it stopped. ``--limit`` / ``--canal-id``
scope a test run.

Exit codes:
    0  success — every in-scope canal computed or skipped, no failures
    1  prerequisite missing — no ``flow_dir`` layer for the area/variante, or its
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

#: Slice 1 defaults to the natural drainage; ``relevado`` is supported but the
#: ficha wiring for it is deferred to slice 2.
DEFAULT_VARIANTE = "natural"
VARIANTES = ("natural", "relevado")

#: Hectares per square metre denominator (a hectare is 10 000 m²).
M2_PER_HA = 10_000.0

#: Log a heartbeat every this many canals.
LOG_EVERY = 50


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
    failed_canal_ids: list[int] = field(default_factory=list)


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


def _flow_dir_layer_name(area_id: str, variante: str) -> str:
    """The ``geo_layers.nombre`` the DEM pipeline registered for this variante."""
    if variante == "natural":
        return f"natural_flow_dir_{area_id}"
    return f"flow_dir_{area_id}"


def resolve_flow_dir_layer(db: Session, area_id: str, variante: str, *, repo: GeoRepository):
    """Return the ``flow_dir`` ``GeoLayer`` for ``(area_id, variante)`` or ``None``.

    ``natural`` prefers the ``natural_flow_dir_{area}`` layer and, only when it is
    absent (no canals were burned, so base == natural), falls back to the base
    ``flow_dir_{area}`` layer. ``relevado`` uses the base layer directly. This is
    a deliberate resolution, never a cross-variant silent fallback.
    """
    layer = repo.get_layer_by_nombre(db, _flow_dir_layer_name(area_id, variante))
    if layer is None and variante == "natural":
        layer = repo.get_layer_by_nombre(db, f"flow_dir_{area_id}")
    if layer is None or layer.tipo != TipoGeoLayer.FLOW_DIR.value:
        return None
    return layer


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


def _canal_line_in_grid_crs(db: Session, canal_id: int, epsg: int):
    """Return the canal trace as a shapely geometry in the flow_dir CRS, or ``None``.

    ``geom IS NULL`` (a topology row with no trace) yields ``None`` — the same
    "no canal" treatment ``canal_buffer`` uses. PostGIS does the reprojection so
    the seed lines up exactly with the metric ``flow_dir`` grid.
    """
    from shapely.geometry import shape  # noqa: PLC0415

    row = db.execute(
        text(
            "SELECT ST_AsGeoJSON(ST_Transform(geom, :epsg)) AS g "
            "FROM canal_network WHERE id = :cid AND geom IS NOT NULL LIMIT 1"
        ),
        {"epsg": epsg, "cid": canal_id},
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


def _upsert_catchment(
    db: Session,
    *,
    canal_id: int,
    variante: str,
    metric_geojson: str | None,
    epsg: int,
    area_ha: float,
    oversized: bool,
    flow_dir_layer_id: uuid.UUID,
    version: str,
) -> None:
    """UPSERT the catchment onto ``(canal_id, variante)``.

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
                (id, canal_id, variante, geometria, area_ha, oversized,
                 flow_dir_layer_id, version)
            VALUES
                (:id, :canal_id, :variante, {geom_sql}, :area_ha, :oversized,
                 :flow_dir_layer_id, :version)
            ON CONFLICT (canal_id, variante) DO UPDATE SET
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
            "canal_id": canal_id,
            "variante": variante,
            "geojson": metric_geojson,
            "epsg": epsg,
            "area_ha": area_ha,
            "oversized": oversized,
            "flow_dir_layer_id": flow_dir_layer_id,
            "version": version,
        },
    )


def _existing_version(db: Session, canal_id: int, variante: str) -> str | None:
    row = db.execute(
        text("SELECT version FROM canal_catchment WHERE canal_id = :cid AND variante = :v LIMIT 1"),
        {"cid": canal_id, "v": variante},
    ).one_or_none()
    return row.version if row is not None else None


def _in_scope_canal_ids(db: Session, *, canal_id: int | None, limit: int | None) -> list[int]:
    clauses = ["geom IS NOT NULL"]
    params: dict[str, Any] = {}
    if canal_id is not None:
        clauses.append("id = :cid")
        params["cid"] = canal_id
    sql = f"SELECT id FROM canal_network WHERE {' AND '.join(clauses)} ORDER BY id"
    if limit is not None:
        sql += " LIMIT :limit"
        params["limit"] = limit
    return [int(r.id) for r in db.execute(text(sql), params)]


def generate_catchments(
    db: Session,
    *,
    area_id: str = DEFAULT_AREA_ID,
    variante: str = DEFAULT_VARIANTE,
    limit: int | None = None,
    canal_id: int | None = None,
    max_area_ha: float | None = None,
    rasterio_module: Any = None,
    rasterize_fn: Callable[..., Any] | None = None,
    shapes_fn: Callable[..., Any] | None = None,
    get_wbt: Callable[[], Any] | None = None,
    log_every: int = LOG_EVERY,
) -> BatchResult:
    """Precompute (or refresh) canal catchments for ``area_id`` and ``variante``.

    Raises ``RuntimeError`` on a prerequisite failure (no flow_dir layer/raster);
    per-canal failures are caught, logged, counted, and do NOT abort the batch —
    a re-run retries only the failures. Progress is committed per canal.
    """
    if variante not in VARIANTES:
        raise ValueError(f"unknown variante {variante!r}; expected one of {VARIANTES}")

    max_area_ha = settings.ficha_max_area_ha if max_area_ha is None else max_area_ha
    rasterio_module, rasterize_fn, shapes_fn, get_wbt = _resolve_io(
        rasterio_module, rasterize_fn, shapes_fn, get_wbt
    )

    repo = GeoRepository()
    flow_dir_layer = resolve_flow_dir_layer(db, area_id, variante, repo=repo)
    if flow_dir_layer is None:
        raise RuntimeError(
            f"no flow_dir layer for area_id={area_id!r} variante={variante!r}; "
            "run the terrain pipeline first"
        )

    version = str(flow_dir_layer.id)
    grid = _open_flow_dir_grid(flow_dir_layer.archivo_path, rasterio_module=rasterio_module)

    canal_ids = _in_scope_canal_ids(db, canal_id=canal_id, limit=limit)
    result = BatchResult(total=len(canal_ids))
    logger.info(
        "canal_catchment.start",
        area_id=area_id,
        variante=variante,
        version=version,
        canales=result.total,
    )

    import tempfile  # noqa: PLC0415

    for index, cid in enumerate(canal_ids, start=1):
        # Heartbeat BEFORE the resume-skip so a long resume (thousands of already
        # done canals) still shows liveness — otherwise the operator sees no log
        # until the first canal that needs recompute.
        if index % log_every == 0:
            logger.info(
                "canal_catchment.progress",
                done=index,
                total=result.total,
                computed=result.computed,
                skipped=result.skipped,
            )
        if _existing_version(db, cid, variante) == version:
            result.skipped += 1
            continue
        try:
            _compute_one(
                db,
                canal_id=cid,
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
            result.failed_canal_ids.append(cid)
            logger.error("canal_catchment.canal_failed", canal_id=cid, exc_info=True)

    logger.info(
        "canal_catchment.done",
        area_id=area_id,
        variante=variante,
        computed=result.computed,
        skipped=result.skipped,
        oversized=result.oversized,
        empty=result.empty,
        failed=result.failed,
    )
    return result


def _compute_one(
    db: Session,
    *,
    canal_id: int,
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

    line = _canal_line_in_grid_crs(db, canal_id, grid.epsg)
    if line is None or line.is_empty:
        # No trace to seed — nothing to compute (treated like a missing canal).
        result.empty += 1
        _upsert_catchment(
            db,
            canal_id=canal_id,
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
            canal_id=canal_id,
            variante=variante,
            metric_geojson=None,
            epsg=grid.epsg,
            area_ha=0.0,
            oversized=False,
            flow_dir_layer_id=flow_dir_layer_id,
            version=version,
        )
        return

    oversized = area_ha > max_area_ha
    metric_geojson = None if oversized else json.dumps(mapping(dissolved))
    _upsert_catchment(
        db,
        canal_id=canal_id,
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
    result.computed += 1


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.domains.geo.etl.generate_canal_catchments",
        description=(
            "Precomputa la cuenca hidrologica aguas-arriba de cada canal "
            "(canal_catchment) usando WBT watershed sobre el puntero D8 flow_dir."
        ),
    )
    parser.add_argument(
        "--area-id",
        default=DEFAULT_AREA_ID,
        help=f"Area de procesamiento (subdirectorio de /data/geo). Por defecto {DEFAULT_AREA_ID!r}.",
    )
    parser.add_argument(
        "--variante",
        choices=VARIANTES,
        default=DEFAULT_VARIANTE,
        help=f"Variante de drenaje (por defecto {DEFAULT_VARIANTE!r}).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Procesar como maximo N canales (para pruebas).",
    )
    parser.add_argument(
        "--canal-id",
        type=int,
        default=None,
        help="Procesar un unico canal por id (para pruebas).",
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
                variante=args.variante,
                limit=args.limit,
                canal_id=args.canal_id,
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

    print(
        f"canal_catchment area_id={args.area_id!r} variante={args.variante!r}: "
        f"{result.computed} calculadas ({result.oversized} oversized, {result.empty} vacias), "
        f"{result.skipped} omitidas, {result.failed} fallidas de {result.total} canales."
    )
    return EXIT_FAILED if result.failed else EXIT_OK


if __name__ == "__main__":  # pragma: no cover — module entry point
    raise SystemExit(main())
