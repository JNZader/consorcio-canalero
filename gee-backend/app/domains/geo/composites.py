"""
Composite raster analysis: flood risk, drainage need, and zonal statistics.

Higher-level functions that consume the terrain primitives from processing.py.
Each function takes file paths and returns file paths — no Celery, no DB.
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.features import rasterize as rasterio_rasterize
from rasterio.mask import mask as rasterio_mask
from shapely.geometry import mapping, shape
from shapely.ops import transform as shapely_transform

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Drainage network merge (real waterways + DEM-generated)
# ---------------------------------------------------------------------------

# Default waterways directory inside the geo-worker container
_DEFAULT_WATERWAYS_DIR = "/app/data/waterways"


def merge_drainage_networks(
    auto_drainage_path: str,
    waterways_dir: str = _DEFAULT_WATERWAYS_DIR,
    output_path: str | None = None,
) -> str:
    """Merge DEM-generated drainage with real waterway GeoJSON files.

    Loads the auto-generated drainage network from the DEM pipeline and
    all ``*.geojson`` files from *waterways_dir*, tagging each feature
    with a ``source`` property ("auto" or "real") so downstream
    consumers can distinguish them.

    Args:
        auto_drainage_path: Path to the DEM-extracted drainage.geojson.
        waterways_dir: Directory containing real waterway GeoJSON files.
        output_path: Where to write the combined FeatureCollection.
            Defaults to ``drainage_combined.geojson`` next to *auto_drainage_path*.

    Returns:
        The output path on success.
    """
    if output_path is None:
        output_path = str(Path(auto_drainage_path).parent / "drainage_combined.geojson")

    combined_features: list[dict] = []

    # 1. Load auto-generated drainage
    auto_path = Path(auto_drainage_path)
    if auto_path.exists():
        with open(auto_path) as f:
            auto_data = json.load(f)
        for feat in auto_data.get("features", []):
            feat.setdefault("properties", {})["source"] = "auto"
            combined_features.append(feat)
        logger.info(
            "merge_drainage_networks: loaded %d auto features from %s",
            len(auto_data.get("features", [])),
            auto_drainage_path,
        )
    else:
        logger.warning(
            "merge_drainage_networks: auto drainage not found at %s, skipping",
            auto_drainage_path,
        )

    # 2. Load real waterway files
    waterways_path = Path(waterways_dir)
    if waterways_path.is_dir():
        for geojson_file in sorted(waterways_path.glob("*.geojson")):
            try:
                with open(geojson_file) as f:
                    ww_data = json.load(f)
                count = 0
                for feat in ww_data.get("features", []):
                    feat.setdefault("properties", {})["source"] = "real"
                    feat["properties"].setdefault("waterway_file", geojson_file.stem)
                    combined_features.append(feat)
                    count += 1
                logger.info(
                    "merge_drainage_networks: loaded %d real features from %s",
                    count,
                    geojson_file.name,
                )
            except Exception:
                logger.warning(
                    "merge_drainage_networks: failed to load %s, skipping",
                    geojson_file.name,
                    exc_info=True,
                )
    else:
        logger.warning(
            "merge_drainage_networks: waterways dir not found at %s",
            waterways_dir,
        )

    # 3. Write combined FeatureCollection
    combined = {"type": "FeatureCollection", "features": combined_features}
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(combined, f)

    logger.info(
        "merge_drainage_networks: wrote %d features to %s",
        len(combined_features),
        output_path,
    )
    return output_path


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
    with open(geojson_path) as f:
        geojson_data = json.load(f)

    geometries = [
        (shape(feat["geometry"]), 1)
        for feat in geojson_data.get("features", [])
    ]

    with rasterio.open(reference_tif) as src:
        meta = src.meta.copy()
        out_shape = (src.height, src.width)
        transform = src.transform

    if geometries:
        burned = rasterio_rasterize(
            geometries,
            out_shape=out_shape,
            transform=transform,
            fill=0,
            dtype="uint8",
        )
    else:
        burned = np.zeros(out_shape, dtype=np.uint8)

    meta.update({"dtype": "uint8", "count": 1, "nodata": None, "driver": "GTiff"})
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **meta) as dst:
        dst.write(burned, 1)

    logger.info("rasterize_drainage: wrote %s from %s", output_path, geojson_path)
    return output_path


# ---------------------------------------------------------------------------
# Default weights (Pampas-calibrated)
# ---------------------------------------------------------------------------

DEFAULT_FLOOD_WEIGHTS: dict[str, float] = {
    "twi": 0.30,                # Wetness index
    "hand": 0.30,               # Height above drainage
    "profile_curvature": 0.25,  # Concavities trap water (INVERTED: negative = high risk)
    "tpi": 0.15,                # Depressions (INVERTED: negative = high risk)
}

DEFAULT_DRAINAGE_WEIGHTS: dict[str, float] = {
    "dist_drainage": 0.30,  # Distance to existing drainage
    "flow_acc": 0.25,       # Water accumulation volume
    "hand": 0.20,           # Low-lying areas
    "tpi": 0.25,            # Depressions need drainage (INVERTED)
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
    w = weights or DEFAULT_FLOOD_WEIGHTS.copy()

    # Load input layers
    area = Path(area_dir)
    hand_data, hand_nd, meta = _load_layer(str(area / "hand.tif"))
    twi_data, twi_nd, _ = _load_layer(str(area / "twi.tif"))
    curv_data, curv_nd, _ = _load_layer(str(area / "profile_curvature.tif"))
    tpi_data, tpi_nd, _ = _load_layer(str(area / "tpi.tif"))

    # Combined nodata mask (union of all layers)
    nodata_mask = hand_nd | twi_nd | curv_nd | tpi_nd

    # Invert HAND: lower raw value = higher risk
    hand_inv = np.where(nodata_mask, 0.0, np.max(hand_data[~nodata_mask]) - hand_data)

    # Invert curvature and TPI: negative values = concavities/depressions = HIGH risk
    # Multiply by -1 so that concavities become positive (high risk)
    curv_inv = np.where(nodata_mask, 0.0, -curv_data)
    tpi_inv = np.where(nodata_mask, 0.0, -tpi_data)

    # Normalize each component
    hand_norm = normalize_percentile(hand_inv, nodata_mask)
    twi_norm = normalize_percentile(twi_data, nodata_mask)
    curv_norm = normalize_percentile(curv_inv, nodata_mask)
    tpi_norm = normalize_percentile(tpi_inv, nodata_mask)

    # Weighted sum → scale to 0-100
    composite = (
        w["twi"] * twi_norm
        + w["hand"] * hand_norm
        + w["profile_curvature"] * curv_norm
        + w["tpi"] * tpi_norm
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
    w = weights or DEFAULT_DRAINAGE_WEIGHTS.copy()

    area = Path(area_dir)

    # Validate drainage raster exists — auto-rasterize from GeoJSON if needed
    drainage_path = area / "drainage.tif"
    if not drainage_path.exists():
        geojson_path = area / "drainage.geojson"
        if geojson_path.exists():
            # Find a reference raster for CRS/transform/shape
            reference = area / "flow_acc.tif"
            if not reference.exists():
                reference = area / "hand.tif"
            rasterize_drainage(
                str(geojson_path), str(reference), str(drainage_path)
            )
            logger.info(
                "compute_drainage_need: auto-rasterized drainage.geojson → drainage.tif"
            )
        else:
            raise FileNotFoundError(
                f"drainage.tif not found in {area_dir}. "
                "Run the DEM pipeline first to generate the drainage network."
            )

    # Load input layers
    facc_data, facc_nd, meta = _load_layer(str(area / "flow_acc.tif"))
    hand_data, hand_nd, _ = _load_layer(str(area / "hand.tif"))
    tpi_data, tpi_nd, _ = _load_layer(str(area / "tpi.tif"))

    # Compute distance-to-drainage using WhiteboxTools
    with tempfile.TemporaryDirectory() as tmpdir:
        dist_output = str(Path(tmpdir) / "dist_drainage.tif")
        wbt = _get_wbt()
        wbt.euclidean_distance(str(drainage_path), dist_output)

        dist_data, dist_nd, _ = _load_layer(dist_output)

    # Combined nodata mask (union of all layers)
    nodata_mask = facc_nd | hand_nd | dist_nd | tpi_nd

    # Invert HAND: lower raw value = higher drainage need
    hand_inv = np.where(nodata_mask, 0.0, np.max(hand_data[~nodata_mask]) - hand_data)

    # Invert TPI: negative values = depressions = HIGH drainage need
    tpi_inv = np.where(nodata_mask, 0.0, -tpi_data)

    # Log-scale flow accumulation
    with np.errstate(invalid="ignore"):
        facc_log = np.where(facc_data > 0, np.log1p(facc_data), 0.0)

    # Normalize each component
    facc_norm = normalize_percentile(facc_log, nodata_mask)
    hand_norm = normalize_percentile(hand_inv, nodata_mask)
    dist_norm = normalize_percentile(dist_data, nodata_mask)
    tpi_norm = normalize_percentile(tpi_inv, nodata_mask)

    # Weighted sum → scale to 0-100
    composite = (
        w["flow_acc"] * facc_norm
        + w["hand"] * hand_norm
        + w["dist_drainage"] * dist_norm
        + w["tpi"] * tpi_norm
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
            transformer = Transformer.from_crs(
                src_crs, dst_crs, always_xy=True
            )
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
                abs(src.transform.a) * m_per_deg_lon
                * abs(src.transform.e) * m_per_deg_lat
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
