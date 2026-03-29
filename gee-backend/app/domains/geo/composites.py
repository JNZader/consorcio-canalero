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
