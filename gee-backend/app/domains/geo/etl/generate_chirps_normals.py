"""Generate the CHIRPS monthly precipitation normals as registered rasters.

Run it inside the deployed backend container — like ``load_suelos_catastro`` the
runner lives under ``app/`` precisely so it exists inside the runtime image
(``gee-backend/Dockerfile:107`` copies only ``app/`` and ``alembic.ini``)::

    docker compose exec backend python -m app.domains.geo.etl.generate_chirps_normals

The backend container mounts ``geo-data:/data/geo`` (``docker-compose.yml:99``),
so the 13 GeoTIFFs written here land on the same volume the geo-worker reads.

**Cadence — this is STATIC reference data.** CHIRPS normals change only when the
normals *period* changes (currently 1991-2020) or the consorcio *extent* changes.
There is no scheduled job and none is wanted: regenerate ON DEMAND, by hand, only
for one of those two reasons. Re-running with an unchanged period and extent just
mints a fresh ``version`` over identical pixels.

**What it produces.** 13 rasters for ``area_id``:

    /data/geo/{area_id}/output/precip_normal_01.tif   (January)
    ...
    /data/geo/{area_id}/output/precip_normal_12.tif   (December)
    /data/geo/{area_id}/output/precip_normal_anual.tif (annual total)

Each is warped to **EPSG:32720 at 5 000 m** with nearest-neighbour resampling and
nodata ``-9999.0``. CHIRPS native resolution is 0.05° (~5.5 km); nearest at
~native resolution keeps source values, whereas bilinear upsampling to the 30 m
composite grid would fabricate detail the ficha then reports as if measured
(JDB-018). Nodata ``-9999.0`` matches the composites convention
(``composites_support.py``) so the raster enters ``extract_zonal_profile``
unchanged.

**Registration (JDB-011/JDB-018).** Every raster becomes a ``geo_layers`` row via
``GeoLayerRepository.create_layer`` — an INSERT, never an upsert — with
``tipo = precip_normal`` and::

    metadata_extra = {
        "mes": 1..12 | "anual",
        "normal_period": "<start>-<end> of THIS run",   # e.g. "1991-2020"
        "fuente": "CHIRPS",
        "version": "<UTC ISO8601 of THIS export run>",
        "resolucion_m": 5000,
    }

``normal_period`` / ``fuente`` are not decoration: they are the PROVENANCE the
ficha serves. ``ficha_service._precipitacion_dataset`` reads them off the rows
that actually answered and publishes them as
``precipitacion_mensual.periodo`` / ``.fuente``, so the browser states the age
of the rasters ON DISK rather than the period this module is configured for
(RISK-001). Re-running with ``--start-year/--end-year`` therefore changes what
the UI says, with no frontend or backend edit.

``version`` is the single timestamp of the run, shared by all 13 rows.
Regeneration therefore appends a fresh set of rows carrying a NEW ``version`` and
leaves the previous rows in place — nothing is silently overwritten. The ficha's
month-scoped lookup (:meth:`GeoLayerRepository.get_latest_precip_normals_by_month`)
groups by ``metadata_extra->>'mes'`` and takes the newest ``version`` per month,
so the latest run wins without deleting history. That is what "regeneration
versions the metadata" means here (spec ``precip-normals-pipeline`` ›
"Regeneration versions the metadata").

**Credentials fail loudly (spec › "Missing credentials fail loudly").** The GEE
download URLs are resolved BEFORE any raster is downloaded or any row is written.
Absent/invalid credentials raise while resolving the region and the export URLs,
so the run aborts with a non-zero exit and registers nothing — no partial layer.
The registration loop is additionally all-or-nothing: any download/warp/DB error
rolls the whole batch back.

Exit codes:
    0  success — 13 rasters written and registered
    1  GEE unavailable (missing/invalid credentials, region resolution failed) —
       nothing was written or registered
    2  invalid invocation
    3  a download, warp or database error aborted the batch — the registration
       transaction was rolled back
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any, Callable, Sequence

from sqlalchemy.orm import Session

from app.domains.geo.gee_service import export_chirps_monthly_normals
from app.domains.geo.gee_service_analytics_support import (
    CHIRPS_FUENTE_LABEL,
    CHIRPS_NORMAL_END_YEAR,
    CHIRPS_NORMAL_START_YEAR,
    chirps_normal_period,
)
from app.domains.geo.models import FormatoGeoLayer, FuenteGeoLayer, TipoGeoLayer
from app.domains.geo.repository import GeoRepository

EXIT_OK = 0
EXIT_GEE_FAILED = 1
EXIT_USAGE = 2
EXIT_FAILED = 3

#: Root of the ``geo-data`` volume the backend and geo-worker share.
GEO_DATA_ROOT = "/data/geo"

#: Warp target: CHIRPS is 0.05° (~5.5 km); 5 000 m in EPSG:32720 is ~native, so
#: nearest-neighbour keeps source values instead of fabricating detail (JDB-018).
TARGET_CRS = "EPSG:32720"
TARGET_SRID = 32720
TARGET_RESOLUTION_M = 5000

#: Matches the composites convention so the raster enters ``extract_zonal_profile``
#: unchanged (``composites_support.py``).
NODATA = -9999.0

#: CHIRPS normals period. Distinct year args are surfaced as CLI flags so a period
#: extension is a documented, deliberate re-run. The DEFAULTS are re-exported from
#: the pipeline constants rather than re-typed: the years live in exactly one place
#: (``gee_service_analytics_support``) so the CLI help, the GEE export window and
#: the ``normal_period`` stamped on every row can never disagree.
DEFAULT_START_YEAR = CHIRPS_NORMAL_START_YEAR
DEFAULT_END_YEAR = CHIRPS_NORMAL_END_YEAR

FUENTE_LABEL = CHIRPS_FUENTE_LABEL

#: Default processing-area identifier. Overridable with ``--area-id`` when a
#: deployment partitions its geo data differently.
DEFAULT_AREA_ID = "consorcio"

DOWNLOAD_TIMEOUT_S = 300


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _mes_label(mes: int | str) -> str:
    """``1 -> "01"`` … ``12 -> "12"``; the annual total keeps its ``"anual"`` tag."""
    return f"{mes:02d}" if isinstance(mes, int) else str(mes)


def _output_filename(mes: int | str) -> str:
    return f"precip_normal_{_mes_label(mes)}.tif"


def _ensure_parent_dir(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def _download(url: str, dest: str, *, requests_module: Any) -> str:
    """Stream a GEE GeoTIFF to ``dest`` — mirrors ``download_dem_impl``."""
    _ensure_parent_dir(dest)
    response = requests_module.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT_S)
    response.raise_for_status()
    with open(dest, "wb") as handle:
        for chunk in response.iter_content(chunk_size=8192):
            handle.write(chunk)
    return dest


def _warp_to_target(
    src_path: str,
    dst_path: str,
    *,
    rasterio_module: Any,
    calculate_default_transform_fn: Callable[..., Any],
    reproject_fn: Callable[..., Any],
    resampling_nearest: Any,
) -> str:
    """Warp ``src_path`` to EPSG:32720 at 5 000 m, nearest, nodata ``-9999.0``.

    Mirrors ``reproject_to_utm_impl`` but pins the destination CRS and resolution
    (rather than deriving a UTM zone) and forces nearest resampling — CHIRPS is
    already ~native at 5 000 m, so nearest is the only resampler that does not
    invent sub-pixel detail (JDB-018).
    """
    with rasterio_module.open(src_path) as src:
        transform, width, height = calculate_default_transform_fn(
            src.crs,
            TARGET_CRS,
            src.width,
            src.height,
            *src.bounds,
            resolution=TARGET_RESOLUTION_M,
        )
        profile = src.profile.copy()
        profile.update(
            crs=TARGET_CRS,
            transform=transform,
            width=width,
            height=height,
            count=1,
            dtype="float32",
            driver="GTiff",
            nodata=NODATA,
        )
        _ensure_parent_dir(dst_path)
        with rasterio_module.open(dst_path, "w", **profile) as dst:
            reproject_fn(
                source=rasterio_module.band(src, 1),
                destination=rasterio_module.band(dst, 1),
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=transform,
                dst_crs=TARGET_CRS,
                dst_nodata=NODATA,
                resampling=resampling_nearest,
            )
    return dst_path


def _resolve_raster_io(
    requests_module: Any,
    rasterio_module: Any,
    calculate_default_transform_fn: Callable[..., Any] | None,
    reproject_fn: Callable[..., Any] | None,
    resampling_nearest: Any,
) -> tuple[Any, Any, Callable[..., Any], Callable[..., Any], Any]:
    """Fill any un-injected I/O dependency with the real rasterio/requests one.

    Tests inject fakes for every slot; production passes nothing and gets the real
    modules. Keeping the import lazy avoids paying for rasterio at import time.
    """
    if requests_module is None:
        import requests as requests_module  # noqa: PLC0415 — lazy on purpose
    if (
        rasterio_module is None
        or calculate_default_transform_fn is None
        or reproject_fn is None
        or resampling_nearest is None
    ):
        import rasterio as _rasterio  # noqa: PLC0415
        from rasterio.warp import (  # noqa: PLC0415
            Resampling,
            calculate_default_transform,
            reproject,
        )

        rasterio_module = rasterio_module or _rasterio
        calculate_default_transform_fn = (
            calculate_default_transform_fn or calculate_default_transform
        )
        reproject_fn = reproject_fn or reproject
        resampling_nearest = (
            resampling_nearest if resampling_nearest is not None else Resampling.nearest
        )
    return (
        requests_module,
        rasterio_module,
        calculate_default_transform_fn,
        reproject_fn,
        resampling_nearest,
    )


def generate_normals(
    db: Session,
    *,
    region: dict,
    area_id: str = DEFAULT_AREA_ID,
    start_year: int = DEFAULT_START_YEAR,
    end_year: int = DEFAULT_END_YEAR,
    export_fn: Callable[..., list[dict]] = export_chirps_monthly_normals,
    requests_module: Any = None,
    rasterio_module: Any = None,
    calculate_default_transform_fn: Callable[..., Any] | None = None,
    reproject_fn: Callable[..., Any] | None = None,
    resampling_nearest: Any = None,
    now_fn: Callable[[], datetime] = _utc_now,
) -> list[Any]:
    """Download, warp and register the 13 CHIRPS normal rasters for ``area_id``.

    Returns the registered ``GeoLayer`` rows (12 monthly + annual). Raises on a
    credentials/GEE failure (before any registration) or any download/warp/DB
    error (after rolling the whole batch back) — the caller maps those to exit
    codes.
    """
    # Resolve every download URL FIRST. ``export_fn`` calls ``_ensure_initialized``
    # inside ``gee_service``, so absent/invalid credentials raise here — before a
    # single raster is fetched or a single row written (no partial layer).
    descriptors = export_fn(region, start_year=start_year, end_year=end_year)

    (
        requests_module,
        rasterio_module,
        calculate_default_transform_fn,
        reproject_fn,
        resampling_nearest,
    ) = _resolve_raster_io(
        requests_module,
        rasterio_module,
        calculate_default_transform_fn,
        reproject_fn,
        resampling_nearest,
    )

    version = now_fn().isoformat()
    # Stamped from the years THIS run actually used — not from the module
    # default. A ``--start-year/--end-year`` override therefore travels with the
    # rasters it produced, and the ficha serves that instead of assuming the
    # configured period (RISK-001).
    normal_period = chirps_normal_period(start_year, end_year)
    output_dir = Path(GEO_DATA_ROOT) / area_id / "output"
    repo = GeoRepository()

    registered: list[Any] = []
    try:
        for descriptor in descriptors:
            mes = descriptor["mes"]
            filename = _output_filename(mes)
            warped_path = str(output_dir / filename)
            tmp_path = str(output_dir / f".{filename}.src.tif")

            _download(descriptor["download_url"], tmp_path, requests_module=requests_module)
            _warp_to_target(
                tmp_path,
                warped_path,
                rasterio_module=rasterio_module,
                calculate_default_transform_fn=calculate_default_transform_fn,
                reproject_fn=reproject_fn,
                resampling_nearest=resampling_nearest,
            )
            Path(tmp_path).unlink(missing_ok=True)

            layer = repo.create_layer(
                db,
                nombre=f"precip_normal_{_mes_label(mes)}_{area_id}",
                tipo=TipoGeoLayer.PRECIP_NORMAL.value,
                fuente=FuenteGeoLayer.GEE.value,
                archivo_path=warped_path,
                formato=FormatoGeoLayer.GEOTIFF.value,
                srid=TARGET_SRID,
                metadata_extra={
                    "mes": mes,
                    "normal_period": normal_period,
                    "fuente": FUENTE_LABEL,
                    "version": version,
                    "resolucion_m": TARGET_RESOLUTION_M,
                },
                area_id=area_id,
            )
            registered.append(layer)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return registered


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.domains.geo.etl.generate_chirps_normals",
        description=(
            "Genera los normales mensuales de precipitación CHIRPS (12 mensuales + "
            "1 anual) como rasters EPSG:32720 5 000 m y los registra en geo_layers."
        ),
    )
    parser.add_argument(
        "--area-id",
        default=DEFAULT_AREA_ID,
        help="Identificador del área de procesamiento (subdirectorio de /data/geo "
        f"y columna area_id). Por defecto {DEFAULT_AREA_ID!r}.",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=DEFAULT_START_YEAR,
        help=f"Año inicial del período de normales (por defecto {DEFAULT_START_YEAR}).",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=DEFAULT_END_YEAR,
        help=f"Año final inclusivo del período de normales (por defecto {DEFAULT_END_YEAR}).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.start_year > args.end_year:
        print(
            f"INVOCACIÓN INVÁLIDA: --start-year ({args.start_year}) debe ser <= "
            f"--end-year ({args.end_year})",
            file=sys.stderr,
        )
        return EXIT_USAGE

    # Resolve the consorcio extent from the GEE zona asset. This is the second
    # place credentials fail loudly: a bad key aborts here, before any DB work.
    try:
        from app.domains.geo.gee_service import get_gee_service

        service = get_gee_service()
        region = service.zona.geometry().getInfo()
    except Exception as exc:  # noqa: BLE001 — the exit code IS the handling
        print(
            f"GEE NO DISPONIBLE: {type(exc).__name__}: {exc}\n"
            "no se resolvió el extent ni las URLs de descarga: nada se escribió ni "
            "se registró. Revisar las credenciales de Earth Engine y reintentar.",
            file=sys.stderr,
        )
        return EXIT_GEE_FAILED

    from app.db.session import SessionLocal

    with SessionLocal() as db:
        try:
            layers = generate_normals(
                db,
                region=region,
                area_id=args.area_id,
                start_year=args.start_year,
                end_year=args.end_year,
            )
        except RuntimeError as exc:
            # ``gee_service._ensure_initialized`` raises RuntimeError on bad creds.
            print(
                f"GEE NO DISPONIBLE: {exc}\n"
                "no se registró ninguna capa (falla previa a cualquier escritura).",
                file=sys.stderr,
            )
            return EXIT_GEE_FAILED
        except Exception as exc:  # noqa: BLE001 — the exit code IS the handling
            print(
                f"FALLO EN LA GENERACIÓN: {type(exc).__name__}: {exc}\n"
                "el lote se revirtió por completo: no quedaron capas parciales "
                "registradas.",
                file=sys.stderr,
            )
            return EXIT_FAILED

    print(
        f"registrados {len(layers)} rasters precip_normal para area_id={args.area_id!r} "
        f"(período {args.start_year}-{args.end_year}, EPSG:{TARGET_SRID} @ "
        f"{TARGET_RESOLUTION_M} m) en {GEO_DATA_ROOT}/{args.area_id}/output/"
    )
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover — module entry point
    raise SystemExit(main())
