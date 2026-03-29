"""
Composite raster analysis: flood risk, drainage need, and zonal statistics.

Higher-level functions that consume the terrain primitives from processing.py.
Each function takes file paths and returns file paths — no Celery, no DB.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.mask import mask as rasterio_mask
from shapely.geometry import mapping, shape

logger = logging.getLogger(__name__)

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
# Default weights (Pampas-calibrated)
# ---------------------------------------------------------------------------

DEFAULT_FLOOD_WEIGHTS: dict[str, float] = {
    "twi": 0.35,
    "hand": 0.25,
    "flow_acc": 0.25,
    "slope": 0.15,
}

DEFAULT_DRAINAGE_WEIGHTS: dict[str, float] = {
    "flow_acc": 0.30,
    "twi": 0.25,
    "hand": 0.25,
    "dist_drainage": 0.20,
}


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


def _load_layer(path: str) -> tuple[np.ndarray, np.ndarray, dict]:
    """Load a single-band raster, returning (data, nodata_mask, meta).

    Args:
        path: Path to the GeoTIFF file.

    Returns:
        Tuple of (data as float64, boolean nodata mask, rasterio meta dict).
    """
    with rasterio.open(path) as src:
        data = src.read(1).astype(np.float64)
        nodata = src.nodata
        meta = src.meta.copy()

    nodata_mask = np.zeros(data.shape, dtype=bool)
    if nodata is not None:
        nodata_mask = data == nodata

    return data, nodata_mask, meta


def compute_flood_risk(
    area_dir: str,
    output_path: str,
    weights: dict[str, float] | None = None,
) -> str:
    """Compute a flood risk composite raster from terrain analysis layers.

    Combines HAND (inverted), TWI, flow accumulation (log-scaled), and
    slope (inverted) into a single weighted index scaled to [0, 100].

    Higher values indicate higher flood risk.

    Args:
        area_dir: Directory containing the input layers
            (hand.tif, twi.tif, flow_acc.tif, slope.tif).
        output_path: Where to write the composite GeoTIFF.
        weights: Optional weight overrides. Keys: twi, hand, flow_acc, slope.
            Must sum to 1.0.

    Returns:
        output_path on success.
    """
    w = weights or DEFAULT_FLOOD_WEIGHTS.copy()

    # Load input layers
    area = Path(area_dir)
    hand_data, hand_nd, meta = _load_layer(str(area / "hand.tif"))
    twi_data, twi_nd, _ = _load_layer(str(area / "twi.tif"))
    facc_data, facc_nd, _ = _load_layer(str(area / "flow_acc.tif"))
    slope_data, slope_nd, _ = _load_layer(str(area / "slope.tif"))

    # Combined nodata mask (union of all layers)
    nodata_mask = hand_nd | twi_nd | facc_nd | slope_nd

    # Invert HAND and slope: lower raw value = higher risk
    hand_inv = np.where(nodata_mask, 0.0, np.max(hand_data[~nodata_mask]) - hand_data)
    slope_inv = np.where(nodata_mask, 0.0, np.max(slope_data[~nodata_mask]) - slope_data)

    # Log-scale flow accumulation (extreme skew: P50=2 but max=500k)
    facc_log = np.where(facc_data > 0, np.log1p(facc_data), 0.0)

    # Normalize each component
    hand_norm = normalize_percentile(hand_inv, nodata_mask)
    twi_norm = normalize_percentile(twi_data, nodata_mask)
    facc_norm = normalize_percentile(facc_log, nodata_mask)
    slope_norm = normalize_percentile(slope_inv, nodata_mask)

    # Weighted sum → scale to 0-100
    composite = (
        w["twi"] * twi_norm
        + w["hand"] * hand_norm
        + w["flow_acc"] * facc_norm
        + w["slope"] * slope_norm
    ).astype(np.float32) * np.float32(100.0)

    # Apply combined nodata mask
    out_nodata = np.float32(-9999.0)
    composite[nodata_mask] = out_nodata

    # Write output GeoTIFF preserving CRS/transform from input
    meta.update(
        {"dtype": "float32", "count": 1, "driver": "GTiff", "nodata": float(out_nodata)}
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **meta) as dst:
        dst.write(composite, 1)

    logger.info("compute_flood_risk: wrote %s (weights=%s)", output_path, w)
    return output_path


# ---------------------------------------------------------------------------
# c) Drainage need composite
# ---------------------------------------------------------------------------


def compute_drainage_need(
    area_dir: str,
    output_path: str,
    weights: dict[str, float] | None = None,
) -> str:
    """Compute a drainage infrastructure need composite raster.

    Combines flow accumulation (log-scaled), TWI, HAND (inverted), and
    distance-to-drainage into a single weighted index scaled to [0, 100].

    Distance-to-drainage is computed from the binary drainage raster using
    WhiteboxTools euclidean_distance. Higher composite values indicate
    areas with greater need for drainage infrastructure.

    Args:
        area_dir: Directory containing the input layers
            (flow_acc.tif, twi.tif, hand.tif, drainage.tif).
        output_path: Where to write the composite GeoTIFF.
        weights: Optional weight overrides. Keys: flow_acc, twi, hand,
            dist_drainage. Must sum to 1.0.

    Returns:
        output_path on success.

    Raises:
        FileNotFoundError: If drainage.tif is missing from area_dir.
    """
    w = weights or DEFAULT_DRAINAGE_WEIGHTS.copy()

    area = Path(area_dir)

    # Validate drainage raster exists
    drainage_path = area / "drainage.tif"
    if not drainage_path.exists():
        raise FileNotFoundError(
            f"drainage.tif not found in {area_dir}. "
            "Run the DEM pipeline first to generate the drainage network."
        )

    # Load input layers
    facc_data, facc_nd, meta = _load_layer(str(area / "flow_acc.tif"))
    twi_data, twi_nd, _ = _load_layer(str(area / "twi.tif"))
    hand_data, hand_nd, _ = _load_layer(str(area / "hand.tif"))

    # Compute distance-to-drainage using WhiteboxTools
    with tempfile.TemporaryDirectory() as tmpdir:
        dist_output = str(Path(tmpdir) / "dist_drainage.tif")
        wbt = _get_wbt()
        wbt.euclidean_distance(str(drainage_path), dist_output)

        dist_data, dist_nd, _ = _load_layer(dist_output)

    # Combined nodata mask (union of all layers)
    nodata_mask = facc_nd | twi_nd | hand_nd | dist_nd

    # Invert HAND: lower raw value = higher drainage need
    hand_inv = np.where(nodata_mask, 0.0, np.max(hand_data[~nodata_mask]) - hand_data)

    # Log-scale flow accumulation
    facc_log = np.where(facc_data > 0, np.log1p(facc_data), 0.0)

    # Normalize each component
    facc_norm = normalize_percentile(facc_log, nodata_mask)
    twi_norm = normalize_percentile(twi_data, nodata_mask)
    hand_norm = normalize_percentile(hand_inv, nodata_mask)
    dist_norm = normalize_percentile(dist_data, nodata_mask)

    # Weighted sum → scale to 0-100
    composite = (
        w["flow_acc"] * facc_norm
        + w["twi"] * twi_norm
        + w["hand"] * hand_norm
        + w["dist_drainage"] * dist_norm
    ).astype(np.float32) * np.float32(100.0)

    # Apply combined nodata mask
    out_nodata = np.float32(-9999.0)
    composite[nodata_mask] = out_nodata

    # Write output GeoTIFF preserving CRS/transform from input
    meta.update(
        {"dtype": "float32", "count": 1, "driver": "GTiff", "nodata": float(out_nodata)}
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **meta) as dst:
        dst.write(composite, 1)

    logger.info("compute_drainage_need: wrote %s (weights=%s)", output_path, w)
    return output_path


# ---------------------------------------------------------------------------
# d) Zonal statistics extraction
# ---------------------------------------------------------------------------

# Threshold above which a pixel is considered "high risk" (score > 70 of 100)
_HIGH_RISK_THRESHOLD = 70.0


def extract_composite_zonal_stats(
    composite_path: str,
    zonas: list[dict[str, Any]],
    tipo: str,
) -> list[dict[str, Any]]:
    """Extract per-zone statistics from a composite raster.

    For each zona geometry, masks the composite and computes summary
    statistics: mean, max, 90th percentile, and area (ha) where the
    composite score exceeds the high-risk threshold (70).

    Args:
        composite_path: Path to a composite GeoTIFF (0-100 scale).
        zonas: List of zone dicts, each with ``id`` and ``geometry``
            (GeoJSON dict or shapely geometry).
        tipo: Composite type identifier (e.g. "flood_risk", "drainage_need").

    Returns:
        List of result dicts ready for DB insertion. Zones that fall
        entirely in nodata are skipped (not included in output).
    """
    results: list[dict[str, Any]] = []

    with rasterio.open(composite_path) as src:
        raster_crs = src.crs
        nodata = src.nodata
        pixel_area_m2 = abs(src.transform.a * src.transform.e)

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
                abs(src.transform.a) * m_per_deg_lon
                * abs(src.transform.e) * m_per_deg_lat
            ) / 10_000.0

        for zona in zonas:
            zona_id = zona["id"]
            geom = zona["geometry"]

            # Accept both shapely and GeoJSON geometry
            if hasattr(geom, "__geo_interface__"):
                geom_geojson = mapping(geom)
            elif isinstance(geom, dict):
                geom_geojson = geom
            else:
                logger.warning(
                    "extract_composite_zonal_stats: skipping zona %s — "
                    "unsupported geometry type",
                    zona_id,
                )
                continue

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
