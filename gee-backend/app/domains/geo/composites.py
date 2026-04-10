"""
Composite raster analysis: flood risk, drainage need, and zonal statistics.

Higher-level functions that consume the terrain primitives from processing.py.
Each function takes file paths and returns file paths — no Celery, no DB.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.mask import mask as rasterio_mask
from shapely.geometry import mapping, shape
from shapely.ops import transform as shapely_transform
from app.domains.geo.composites_support import (
    DEFAULT_WATERWAYS_DIR as _DEFAULT_WATERWAYS_DIR,
    compute_drainage_need_impl,
    compute_flood_risk_impl,
    merge_drainage_networks_impl,
    rasterize_drainage_impl,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Drainage network merge (real waterways + DEM-generated)
# ---------------------------------------------------------------------------


def merge_drainage_networks(
    auto_drainage_path: str,
    waterways_dir: str = _DEFAULT_WATERWAYS_DIR,
    output_path: str | None = None,
    reference_tif: str | None = None,
) -> str:
    """Merge DEM-generated drainage with real waterway GeoJSON files.

    Loads the auto-generated drainage network from the DEM pipeline and
    all ``*.geojson`` files from *waterways_dir*, tagging each feature
    with a ``source`` property ("auto" or "real") so downstream
    consumers can distinguish them.

    Real waterway files are assumed to be in EPSG:4326.  When a
    *reference_tif* is provided (or auto-detected next to the drainage
    file), waterway geometries are reprojected to match the raster CRS
    so that ``rasterize_drainage`` burns them onto the correct pixels.

    Args:
        auto_drainage_path: Path to the DEM-extracted drainage.geojson.
        waterways_dir: Directory containing real waterway GeoJSON files.
        output_path: Where to write the combined FeatureCollection.
            Defaults to ``drainage_combined.geojson`` next to *auto_drainage_path*.
        reference_tif: Optional reference raster to detect target CRS.
            Falls back to flow_acc.tif or hand.tif in the same directory.

    Returns:
        The output path on success.
    """
    return merge_drainage_networks_impl(
        auto_drainage_path,
        waterways_dir=waterways_dir,
        output_path=output_path,
        reference_tif=reference_tif,
    )


# ---------------------------------------------------------------------------
# WhiteboxTools singleton (reuse pattern from processing.py)
# ---------------------------------------------------------------------------

_wbt = None


def _get_wbt():
    """Lazily initialise a WhiteboxTools instance (verbose off)."""
    global _wbt  # noqa: PLW0603
    if _wbt is None:
        from whitebox import WhiteboxTools

        _wbt = WhiteboxTools()
        _wbt.set_verbose_mode(False)
    return _wbt


# ---------------------------------------------------------------------------
# Drainage vector → raster conversion
# ---------------------------------------------------------------------------


def rasterize_drainage(
    geojson_path: str,
    reference_tif: str,
    output_path: str,
) -> str:
    """Rasterize a drainage GeoJSON into a binary raster matching a reference grid.

    Burns vector features from the GeoJSON as 1 onto a 0-background raster,
    using the CRS, transform, and shape of *reference_tif*.

    Args:
        geojson_path: Path to drainage.geojson (FeatureCollection).
        reference_tif: Any existing GeoTIFF to use as spatial reference.
        output_path: Where to write the binary drainage raster.

    Returns:
        output_path on success.
    """
    return rasterize_drainage_impl(geojson_path, reference_tif, output_path)


# ---------------------------------------------------------------------------
# a) Percentile normalization
# ---------------------------------------------------------------------------


def normalize_percentile(
    data: np.ndarray,
    nodata_mask: np.ndarray,
    low: float = 2.0,
    high: float = 98.0,
) -> np.ndarray:
    """Normalize valid pixels to [0, 1] using percentile clipping.

    Pixels outside the [low, high] percentile range are clamped to 0 or 1.
    Nodata pixels are excluded from percentile computation and set to 0
    in the output (caller applies nodata mask separately).

    Args:
        data: Input raster band as 2D array.
        nodata_mask: Boolean mask where True = nodata pixel.
        low: Lower percentile for clipping (default 2.0).
        high: Upper percentile for clipping (default 98.0).

    Returns:
        Float32 array with values in [0, 1]. All-nodata returns zeros.
    """
    valid = data[~nodata_mask]

    if valid.size == 0:
        logger.warning("normalize_percentile: all pixels are nodata, returning zeros")
        return np.zeros(data.shape, dtype=np.float32)

    p_low = np.percentile(valid, low)
    p_high = np.percentile(valid, high)

    if p_high == p_low:
        # Single-value band — return uniform 0.5
        result = np.full(data.shape, 0.5, dtype=np.float32)
        result[nodata_mask] = 0.0
        return result

    normalized = (data.astype(np.float64) - p_low) / (p_high - p_low)
    result = np.clip(normalized, 0.0, 1.0).astype(np.float32)
    result[nodata_mask] = 0.0

    return result


# ---------------------------------------------------------------------------
# b) Flood risk composite
# ---------------------------------------------------------------------------


def compute_flood_risk(
    area_dir: str,
    output_path: str,
    weights: dict[str, float] | None = None,
) -> str:
    """Compute a flood risk composite raster from terrain analysis layers.

    Combines TWI, HAND (inverted), profile curvature (inverted — concavities
    trap water), and TPI (inverted — depressions accumulate water) into a
    single weighted index scaled to [0, 100].

    Slope was removed because on flat terrain (e.g. Pampas) it provides
    almost no discrimination.  Profile curvature and TPI capture micro-
    topography that drives real water accumulation.

    Higher values indicate higher flood risk.

    Args:
        area_dir: Directory containing the input layers
            (hand.tif, twi.tif, profile_curvature.tif, tpi.tif).
        output_path: Where to write the composite GeoTIFF.
        weights: Optional weight overrides.
            Keys: twi, hand, profile_curvature, tpi.  Must sum to 1.0.

    Returns:
        output_path on success.
    """
    return compute_flood_risk_impl(
        area_dir,
        output_path,
        normalize_percentile,
        weights=weights,
    )


# ---------------------------------------------------------------------------
# c) Drainage need composite
# ---------------------------------------------------------------------------


def compute_drainage_need(
    area_dir: str,
    output_path: str,
    weights: dict[str, float] | None = None,
) -> str:
    """Compute a drainage infrastructure need composite raster.

    Combines flow accumulation (log-scaled), HAND (inverted),
    distance-to-drainage, and TPI (inverted — depressions need drainage)
    into a single weighted index scaled to [0, 100].

    TWI is intentionally excluded because it is highly correlated with
    flow_acc on flat terrain (r=0.93), and flood_risk already uses TWI
    as its primary signal.

    Distance-to-drainage is computed from the binary drainage raster using
    WhiteboxTools euclidean_distance. Higher composite values indicate
    areas with greater need for drainage infrastructure.

    Args:
        area_dir: Directory containing the input layers
            (flow_acc.tif, hand.tif, drainage.tif, tpi.tif).
        output_path: Where to write the composite GeoTIFF.
        weights: Optional weight overrides. Keys: flow_acc, hand,
            dist_drainage, tpi. Must sum to 1.0.

    Returns:
        output_path on success.

    Raises:
        FileNotFoundError: If drainage.tif is missing from area_dir.
    """
    return compute_drainage_need_impl(
        area_dir,
        output_path,
        weights=weights,
        get_wbt_fn=_get_wbt,
        rasterize_drainage_fn=rasterize_drainage,
        normalize_percentile_fn=normalize_percentile,
    )


# ---------------------------------------------------------------------------
# d) Zonal statistics extraction
# ---------------------------------------------------------------------------

# Threshold above which a pixel is considered "high risk" (score > 70 of 100)
_HIGH_RISK_THRESHOLD = 70.0


def extract_composite_zonal_stats(
    composite_path: str,
    zonas: list[dict[str, Any]],
    tipo: str,
    zona_crs: str | CRS = "EPSG:4326",
) -> list[dict[str, Any]]:
    """Extract per-zone statistics from a composite raster.

    For each zona geometry, masks the composite and computes summary
    statistics: mean, max, 90th percentile, and area (ha) where the
    composite score exceeds the high-risk threshold (70).

    Zone geometries are automatically reprojected to match the raster CRS
    when they differ (e.g. zones in EPSG:4326 vs raster in EPSG:32720).

    Args:
        composite_path: Path to a composite GeoTIFF (0-100 scale).
        zonas: List of zone dicts, each with ``id`` and ``geometry``
            (GeoJSON dict or shapely geometry).
        tipo: Composite type identifier (e.g. "flood_risk", "drainage_need").
        zona_crs: CRS of the input zone geometries (default EPSG:4326).

    Returns:
        List of result dicts ready for DB insertion. Zones that fall
        entirely in nodata are skipped (not included in output).
    """
    results: list[dict[str, Any]] = []

    with rasterio.open(composite_path) as src:
        raster_crs = src.crs
        nodata = src.nodata
        pixel_area_m2 = abs(src.transform.a * src.transform.e)

        # Build a reprojection function if zone CRS differs from raster CRS
        _reproject_geom = None
        src_crs = CRS.from_user_input(zona_crs)
        dst_crs = CRS.from_user_input(raster_crs) if raster_crs else None
        if dst_crs and src_crs != dst_crs:
            transformer = Transformer.from_crs(src_crs, dst_crs, always_xy=True)
            _reproject_geom = lambda geom: shapely_transform(  # noqa: E731
                transformer.transform, geom
            )
            logger.info(
                "extract_composite_zonal_stats: reprojecting zones from %s to %s",
                src_crs,
                dst_crs,
            )

        # Convert pixel area to hectares
        if raster_crs and raster_crs.is_projected:
            pixel_area_ha = pixel_area_m2 / 10_000.0
        else:
            # Geographic CRS: approximate using center latitude
            bounds = src.bounds
            center_lat = (bounds.top + bounds.bottom) / 2
            lat_rad = np.radians(center_lat)
            m_per_deg_lat = 111_320.0
            m_per_deg_lon = 111_320.0 * np.cos(lat_rad)
            pixel_area_ha = (
                abs(src.transform.a)
                * m_per_deg_lon
                * abs(src.transform.e)
                * m_per_deg_lat
            ) / 10_000.0

        for zona in zonas:
            zona_id = zona["id"]
            geom = zona["geometry"]

            # Accept both shapely and GeoJSON geometry → shapely object
            if hasattr(geom, "__geo_interface__"):
                geom_shapely = geom
            elif isinstance(geom, dict):
                geom_shapely = shape(geom)
            else:
                logger.warning(
                    "extract_composite_zonal_stats: skipping zona %s — "
                    "unsupported geometry type",
                    zona_id,
                )
                continue

            # Reproject zone geometry to raster CRS if needed
            if _reproject_geom is not None:
                geom_shapely = _reproject_geom(geom_shapely)

            geom_geojson = mapping(geom_shapely)

            try:
                out_image, _ = rasterio_mask(
                    src, [geom_geojson], crop=True, all_touched=True
                )
            except Exception:
                logger.warning(
                    "extract_composite_zonal_stats: failed to mask zona %s, skipping",
                    zona_id,
                    exc_info=True,
                )
                continue

            data = out_image[0].astype(np.float64)

            # Build valid mask (exclude nodata)
            valid_mask = np.ones(data.shape, dtype=bool)
            if nodata is not None:
                valid_mask = data != nodata

            valid = data[valid_mask]

            if valid.size == 0:
                logger.info(
                    "extract_composite_zonal_stats: zona %s is all nodata, skipping",
                    zona_id,
                )
                continue

            mean_score = float(np.mean(valid))
            max_score = float(np.max(valid))
            p90_score = float(np.percentile(valid, 90))
            high_risk_pixels = int(np.sum(valid > _HIGH_RISK_THRESHOLD))
            area_high_risk_ha = float(high_risk_pixels * pixel_area_ha)

            results.append(
                {
                    "zona_id": zona_id,
                    "tipo": tipo,
                    "mean_score": round(mean_score, 2),
                    "max_score": round(max_score, 2),
                    "p90_score": round(p90_score, 2),
                    "area_high_risk_ha": round(area_high_risk_ha, 4),
                    "weights_used": None,  # caller sets from composite weights
                }
            )

    logger.info(
        "extract_composite_zonal_stats: %d/%d zonas produced stats for %s",
        len(results),
        len(zonas),
        tipo,
    )
    return results
