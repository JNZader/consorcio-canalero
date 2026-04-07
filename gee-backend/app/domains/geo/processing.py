"""
Pure terrain analysis functions using rasterio, numpy, and whiteboxtools.

Each function takes file paths and returns file paths — no Celery, no DB.
These are the computational building blocks for the DEM pipeline.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.warp import Resampling, calculate_default_transform, reproject
from rasterio.features import shapes
from rasterio.mask import mask as rasterio_mask
from shapely.geometry import box, mapping, shape

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# WhiteboxTools singleton (lazy import — only available in geo-worker)
# ---------------------------------------------------------------------------

_wbt: Any | None = None


def _get_wbt() -> Any:
    """Lazily import and initialise WhiteboxTools (only installed in geo-worker)."""
    global _wbt  # noqa: PLW0603
    if _wbt is None:
        from whitebox import WhiteboxTools  # noqa: PLC0415
        _wbt = WhiteboxTools()
        _wbt.set_verbose_mode(False)
    return _wbt


# ---------------------------------------------------------------------------
# 0a) Ensure nodata is set
# ---------------------------------------------------------------------------


def ensure_nodata(
    dem_path: str, output_path: str, nodata_value: float = -32768.0
) -> str:
    """Ensure the DEM has an explicit nodata value set in metadata.

    GEE exports DEMs without nodata metadata. WhiteboxTools assumes -32768
    as nodata and corrupts the raster (99.9% of pixels become NaN) when
    the metadata is missing.

    Args:
        dem_path: Input DEM path.
        output_path: Output DEM path with nodata set.
        nodata_value: Nodata value to assign.

    Returns:
        output_path on success.
    """
    with rasterio.open(dem_path) as src:
        if src.nodata is not None:
            shutil.copy2(dem_path, output_path)
            return output_path
        profile = src.profile.copy()
        data = src.read(1)

    profile.update(nodata=nodata_value)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(data, 1)
    return output_path


# ---------------------------------------------------------------------------
# 0b) Reproject to UTM
# ---------------------------------------------------------------------------


def reproject_to_utm(dem_path: str, output_path: str) -> str:
    """Reproject DEM to UTM for correct metric calculations.

    Auto-detects the appropriate UTM zone from the DEM center coordinates.
    Critical for flat terrain where degree-based area/slope calculations
    are wildly inaccurate (e.g. Argentine Pampas).

    Args:
        dem_path: Input DEM path (EPSG:4326).
        output_path: Output DEM path in UTM.

    Returns:
        output_path on success.
    """
    with rasterio.open(dem_path) as src:
        if src.crs and src.crs.is_projected:
            shutil.copy2(dem_path, output_path)
            return output_path

        bounds = src.bounds
        center_lon = (bounds.left + bounds.right) / 2
        center_lat = (bounds.top + bounds.bottom) / 2

        zone = int((center_lon + 180) / 6) + 1
        epsg = 32600 + zone if center_lat >= 0 else 32700 + zone
        dst_crs = f"EPSG:{epsg}"

        transform, width, height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds
        )
        profile = src.profile.copy()
        profile.update(crs=dst_crs, transform=transform, width=width, height=height)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(output_path, "w", **profile) as dst:
            reproject(
                source=rasterio.band(src, 1),
                destination=rasterio.band(dst, 1),
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=transform,
                dst_crs=dst_crs,
                resampling=Resampling.bilinear,
            )
    return output_path


# ---------------------------------------------------------------------------
# 0c) Clip DEM to polygon geometry
# ---------------------------------------------------------------------------


def clip_to_geometry(
    dem_path: str,
    geometry: dict[str, Any],
    output_path: str,
    geometry_crs: str = "EPSG:4326",
) -> str:
    """Clip a DEM to an arbitrary polygon geometry.

    Reprojects the geometry to the DEM's CRS if they differ, then masks
    pixels outside the polygon to nodata.

    Args:
        dem_path: Input DEM path.
        geometry: GeoJSON geometry dict (Polygon or MultiPolygon).
        output_path: Output clipped DEM path.
        geometry_crs: CRS of the input geometry (default EPSG:4326).

    Returns:
        output_path on success.
    """
    with rasterio.open(dem_path) as src:
        dem_crs = str(src.crs)

        clip_geom = shape(geometry)

        # Reproject geometry to DEM CRS if needed
        if dem_crs != geometry_crs:
            from pyproj import Transformer
            from shapely.ops import transform as shapely_transform

            transformer = Transformer.from_crs(geometry_crs, dem_crs, always_xy=True)
            clip_geom = shapely_transform(transformer.transform, clip_geom)

        out_image, out_transform = rasterio_mask(src, [mapping(clip_geom)], crop=True)
        profile = src.profile.copy()
        profile.update(
            height=out_image.shape[1],
            width=out_image.shape[2],
            transform=out_transform,
        )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(out_image)

    return output_path


# ---------------------------------------------------------------------------
# a) Clip DEM
# ---------------------------------------------------------------------------


def clip_dem(
    dem_path: str,
    bbox: tuple[float, float, float, float],
    output_path: str,
) -> str:
    """Clip a DEM to a bounding box using rasterio.

    Args:
        dem_path: Path to the input DEM GeoTIFF.
        bbox: (minx, miny, maxx, maxy) in the CRS of the DEM.
        output_path: Where to write the clipped raster.

    Returns:
        output_path on success.
    """
    geom = box(*bbox)

    with rasterio.open(dem_path) as src:
        out_image, out_transform = rasterio_mask(src, [mapping(geom)], crop=True)
        out_meta = src.meta.copy()
        out_meta.update(
            {
                "driver": "GTiff",
                "height": out_image.shape[1],
                "width": out_image.shape[2],
                "transform": out_transform,
            }
        )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **out_meta) as dst:
        dst.write(out_image)

    return output_path


# ---------------------------------------------------------------------------
# b0) Remove off-terrain objects (trees, buildings)
# ---------------------------------------------------------------------------


def remove_off_terrain_objects(
    dem_path: str,
    output_path: str,
    filter_size: int = 7,
    slope_threshold: float = 5.0,
) -> str:
    """Remove vegetation and building artifacts from a DSM using WhiteboxTools.

    Copernicus GLO-30 is a DSM — trees and buildings appear as raised spikes.
    This step produces a pseudo-DTM by applying a morphological filter that
    removes upward protrusions smaller than filter_size × pixel_resolution.

    For Copernicus 30m over flat terrain (e.g. Córdoba irrigation zones):
      - filter_size=7 → 210m search window — catches isolated trees/buildings
        without flattening real terrain features (hills, canal embankments)
      - slope_threshold=5.0 → suitable for near-flat agricultural plains;
        raise to 10–15 for hilly terrain

    IMPORTANT: {z}/{x}/{y} are resolved internally by WBT — do not use this
    function on non-projected DEMs; input must already be in UTM.

    Args:
        dem_path: Input DSM path (projected, nodata set).
        output_path: Output filtered DEM path.
        filter_size: Morphological filter kernel size in pixels (default 7).
        slope_threshold: Max expected terrain slope in degrees (default 5.0).

    Returns:
        output_path on success.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    wbt = _get_wbt()
    wbt.remove_off_terrain_objects(
        dem_path,
        output_path,
        filter=filter_size,
        slope=slope_threshold,
    )
    return output_path


# ---------------------------------------------------------------------------
# b) Fill sinks
# ---------------------------------------------------------------------------


def fill_sinks(dem_path: str, output_path: str) -> str:
    """Fill depressions in a DEM using WhiteboxTools.

    Replicates QGIS/SAGA "Fill sinks (Wang & Liu)" approach.
    The input DEM MUST have nodata set and be in a projected CRS (UTM).
    Without proper nodata metadata, WBT corrupts the raster.

    Args:
        dem_path: Input DEM path (with nodata set, ideally UTM).
        output_path: Output filled DEM path.

    Returns:
        output_path on success.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    wbt = _get_wbt()
    wbt.fill_depressions(dem_path, output_path)
    return output_path


# ---------------------------------------------------------------------------
# c) Slope
# ---------------------------------------------------------------------------


def compute_slope(dem_path: str, output_path: str) -> str:
    """Calculate slope in degrees from a DEM.

    Formula: slope = arctan(sqrt(dz_dx^2 + dz_dy^2)) * (180 / pi)

    Args:
        dem_path: Input DEM path.
        output_path: Output slope raster path.

    Returns:
        output_path on success.
    """
    with rasterio.open(dem_path) as src:
        dem = src.read(1).astype(np.float64)
        nodata = src.nodata
        transform = src.transform
        meta = src.meta.copy()

    # Cell sizes from the affine transform
    cell_x = abs(transform.a)
    cell_y = abs(transform.e)

    # Gradient (numpy uses row/col order, so axis=1 → x, axis=0 → y)
    dz_dy, dz_dx = np.gradient(dem, cell_y, cell_x)

    slope_rad = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))
    slope_deg = np.degrees(slope_rad).astype(np.float32)

    # Mask nodata
    if nodata is not None:
        nodata_mask = dem == nodata
        slope_deg[nodata_mask] = np.float32(nodata)

    meta.update({"dtype": "float32", "count": 1, "driver": "GTiff", "nodata": nodata})
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **meta) as dst:
        dst.write(slope_deg, 1)

    return output_path


# ---------------------------------------------------------------------------
# d) Aspect
# ---------------------------------------------------------------------------


def compute_aspect(dem_path: str, output_path: str) -> str:
    """Calculate aspect (direction of slope, 0-360 degrees) from a DEM.

    Formula: aspect = arctan2(-dz_dy, dz_dx) * (180 / pi), normalised to 0-360.

    Args:
        dem_path: Input DEM path.
        output_path: Output aspect raster path.

    Returns:
        output_path on success.
    """
    with rasterio.open(dem_path) as src:
        dem = src.read(1).astype(np.float64)
        nodata = src.nodata
        transform = src.transform
        meta = src.meta.copy()

    cell_x = abs(transform.a)
    cell_y = abs(transform.e)

    dz_dy, dz_dx = np.gradient(dem, cell_y, cell_x)
    aspect_deg = np.degrees(np.arctan2(-dz_dy, dz_dx)).astype(np.float32)

    # Normalise to 0-360
    aspect_deg = np.mod(aspect_deg, np.float32(360.0))

    if nodata is not None:
        nodata_mask = dem == nodata
        aspect_deg[nodata_mask] = np.float32(nodata)

    meta.update({"dtype": "float32", "count": 1, "driver": "GTiff", "nodata": nodata})
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **meta) as dst:
        dst.write(aspect_deg, 1)

    return output_path


# ---------------------------------------------------------------------------
# e) Flow direction (D8)
# ---------------------------------------------------------------------------


def compute_flow_direction(filled_dem_path: str, output_path: str) -> str:
    """D8 flow direction using WhiteboxTools.

    Args:
        filled_dem_path: Path to a filled (sink-free) DEM.
        output_path: Output flow direction raster path.

    Returns:
        output_path on success.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    wbt = _get_wbt()
    wbt.d8_pointer(filled_dem_path, output_path)
    return output_path


# ---------------------------------------------------------------------------
# f) Flow accumulation (D8)
# ---------------------------------------------------------------------------


def compute_flow_accumulation(dem_path: str, output_path: str) -> str:
    """D8 flow accumulation using WhiteboxTools.

    Computes flow accumulation directly from the filled DEM rather than
    from a pre-computed flow direction raster. WBT's d8_flow_accumulation
    with a DEM input uses internal flow routing that handles flat terrain
    much better than the d8_pointer → d8_flow_accumulation chain.

    Args:
        dem_path: Path to the filled DEM (not flow direction).
        output_path: Output flow accumulation raster path.

    Returns:
        output_path on success.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    wbt = _get_wbt()
    wbt.d8_flow_accumulation(dem_path, output_path, out_type="cells")
    return output_path


# ---------------------------------------------------------------------------
# g) Topographic Wetness Index (TWI)
# ---------------------------------------------------------------------------

# Minimum slope in radians to avoid log(inf) when tan(b) ≈ 0.
_MIN_SLOPE_RAD = np.float64(0.001)


def compute_twi(
    slope_path: str,
    flow_acc_path: str,
    output_path: str,
) -> str:
    """Topographic Wetness Index: TWI = ln(a / tan(b)).

    Where:
        a = specific catchment area = flow_acc * cell_size
        b = slope in radians (capped at _MIN_SLOPE_RAD to avoid division by zero)

    Args:
        slope_path: Slope raster in *degrees*.
        flow_acc_path: Flow accumulation raster.
        output_path: Output TWI raster path.

    Returns:
        output_path on success.
    """
    with rasterio.open(slope_path) as src_slope:
        slope_deg = src_slope.read(1).astype(np.float64)
        nodata_slope = src_slope.nodata
        meta = src_slope.meta.copy()
        cell_size = abs(src_slope.transform.a)

    with rasterio.open(flow_acc_path) as src_fa:
        flow_acc = src_fa.read(1).astype(np.float64)
        nodata_fa = src_fa.nodata

    # Build combined nodata mask
    nodata_mask = np.zeros(slope_deg.shape, dtype=bool)
    if nodata_slope is not None:
        nodata_mask |= slope_deg == nodata_slope
    if nodata_fa is not None:
        nodata_mask |= flow_acc == nodata_fa

    slope_rad = np.radians(slope_deg)
    slope_rad = np.maximum(slope_rad, _MIN_SLOPE_RAD)

    specific_area = flow_acc * cell_size
    # Avoid log of non-positive values
    specific_area = np.maximum(specific_area, np.float64(1e-10))

    twi = np.log(specific_area / np.tan(slope_rad)).astype(np.float32)

    out_nodata = np.float32(-9999.0)
    twi[nodata_mask] = out_nodata

    meta.update(
        {"dtype": "float32", "count": 1, "driver": "GTiff", "nodata": float(out_nodata)}
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **meta) as dst:
        dst.write(twi, 1)

    return output_path


# ---------------------------------------------------------------------------
# h) Height Above Nearest Drainage (HAND)
# ---------------------------------------------------------------------------

_DEFAULT_DRAINAGE_THRESHOLD = 1000


def compute_hand(
    dem_path: str,
    flow_dir_path: str,
    flow_acc_path: str,
    output_path: str,
    drainage_threshold: int = _DEFAULT_DRAINAGE_THRESHOLD,
) -> str:
    """Height Above Nearest Drainage using WhiteboxTools.

    Internally extracts a drainage network from flow accumulation (threshold),
    then computes the HAND index.

    Args:
        dem_path: Input DEM path.
        flow_dir_path: D8 flow direction raster path.
        flow_acc_path: Flow accumulation raster path.
        output_path: Output HAND raster path.
        drainage_threshold: Flow accumulation threshold for drainage extraction.

    Returns:
        output_path on success.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # 1. Extract drainage raster via threshold
    with tempfile.TemporaryDirectory() as tmpdir:
        drainage_raster = str(Path(tmpdir) / "drainage.tif")

        with rasterio.open(flow_acc_path) as src:
            fa = src.read(1)
            meta = src.meta.copy()
            nodata_fa = src.nodata

        drainage = np.where(fa >= drainage_threshold, 1, 0).astype(np.int16)
        if nodata_fa is not None:
            drainage[fa == nodata_fa] = 0

        meta.update({"dtype": "int16", "count": 1, "nodata": 0, "driver": "GTiff"})
        with rasterio.open(drainage_raster, "w", **meta) as dst:
            dst.write(drainage, 1)

        # 2. Compute elevation above stream
        wbt = _get_wbt()
        wbt.elevation_above_stream(dem_path, drainage_raster, output_path)

    return output_path


# ---------------------------------------------------------------------------
# i) Extract drainage network (vector)
# ---------------------------------------------------------------------------


def extract_drainage_network(
    flow_acc_path: str,
    threshold: int,
    output_path: str,
) -> str:
    """Extract drainage network as GeoJSON from flow accumulation.

    Cells with flow_acc > threshold are classified as drainage, then
    vectorised to polygon features.

    Args:
        flow_acc_path: Flow accumulation raster.
        threshold: Minimum accumulation value for drainage cells.
        output_path: Output GeoJSON path.

    Returns:
        output_path on success.
    """
    with rasterio.open(flow_acc_path) as src:
        fa = src.read(1)
        nodata = src.nodata
        transform = src.transform
        crs = src.crs

    drainage_mask = fa > threshold
    if nodata is not None:
        drainage_mask &= fa != nodata

    drainage_binary = drainage_mask.astype(np.uint8)

    features = []
    for geom, value in shapes(
        drainage_binary, mask=drainage_binary, transform=transform
    ):
        if value == 1:
            features.append(
                {
                    "type": "Feature",
                    "geometry": geom,
                    "properties": {"class": "drainage"},
                }
            )

    geojson = {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": str(crs) if crs else "EPSG:4326"},
        },
        "features": features,
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(geojson, f)

    return output_path


# ---------------------------------------------------------------------------
# j-1) Profile curvature
# ---------------------------------------------------------------------------


def compute_profile_curvature(filled_dem_path: str, output_dir: str) -> str:
    """Compute profile curvature from a filled DEM using WhiteboxTools.

    Profile curvature measures the rate of change of slope along the
    direction of maximum slope.  Negative values indicate concave
    surfaces (water accumulates), positive values indicate convex
    surfaces (water sheds).

    Args:
        filled_dem_path: Path to the filled (sink-free) DEM.
        output_dir: Directory where profile_curvature.tif will be written.

    Returns:
        Path to the output profile_curvature.tif.
    """
    output_path = str(Path(output_dir) / "profile_curvature.tif")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    wbt = _get_wbt()
    wbt.profile_curvature(filled_dem_path, output_path)
    return output_path


# ---------------------------------------------------------------------------
# j-2) Topographic Position Index (TPI)
# ---------------------------------------------------------------------------


def compute_tpi(
    filled_dem_path: str,
    output_dir: str,
    radius: int = 10,
) -> str:
    """Compute Topographic Position Index (TPI) from a filled DEM.

    TPI = elevation - mean_neighborhood_elevation.
    Negative values indicate depressions/valleys, positive values
    indicate ridges/hilltops.

    Uses WhiteboxTools ``deviation_from_mean_elevation`` which computes
    exactly this: the difference between each cell's elevation and the
    mean elevation of its neighbourhood.

    Args:
        filled_dem_path: Path to the filled (sink-free) DEM.
        output_dir: Directory where tpi.tif will be written.
        radius: Neighbourhood radius in cells (default 10).

    Returns:
        Path to the output tpi.tif.
    """
    output_path = str(Path(output_dir) / "tpi.tif")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    wbt = _get_wbt()
    filterx = radius * 2 + 1
    filtery = radius * 2 + 1
    wbt.dev_from_mean_elev(
        filled_dem_path,
        output_path,
        filterx=filterx,
        filtery=filtery,
    )
    return output_path


# ---------------------------------------------------------------------------
# j) Terrain classification — 5 actionable classes for flat terrain management
# ---------------------------------------------------------------------------

# Classification codes (0-4)
TERRAIN_SIN_RIESGO = 0  # No risk — transparent on map
TERRAIN_DRENAJE_NATURAL = 1  # Natural drainage lines
TERRAIN_RIESGO_ALTO = 2  # High flood risk
TERRAIN_RIESGO_MEDIO = 3  # Moderate flood risk

TERRAIN_CLASS_LABELS = {
    0: "Drenaje Natural",
    1: "Zona Inundable",
    2: "Necesita Drenaje",
    3: "Loma / Divisoria",
    4: "Terreno Funcional",
}


def classify_terrain(
    filled_dem_path: str,
    output_dir: str,
    hand_path: str | None = None,
    tpi_path: str | None = None,
    curvature_path: str | None = None,
    flow_acc_path: str | None = None,
    twi_path: str | None = None,
) -> str:
    """Classify terrain into 3 actionable risk classes + transparent for canal management.

    Uses HAND, flow accumulation, and TWI to produce a risk-focused
    classification for ultra-flat terrain (Argentine Pampas). "Sin Riesgo"
    renders transparent so only actionable zones appear on the map.

    HAND is the primary discriminator — on flat terrain, height above nearest
    drainage is the most reliable flood predictor. TPI is NOT used because
    the center of wide flat depressions has TPI ≈ 0 (neighbors equally low).

    Classes (applied in PRIORITY ORDER — earlier classes override later):
        0 = SIN_RIESGO:       No flood risk — rendered transparent on map
        1 = DRENAJE_NATURAL:  Natural drainage lines (high flow_acc + low HAND)
        2 = RIESGO_ALTO:      High flood risk (HAND < 0.8m + TWI > P55)
        3 = RIESGO_MEDIO:     Moderate flood risk (HAND < 1.5m + TWI > P35)

    Args:
        filled_dem_path: Path to the filled DEM (used as reference for output metadata).
        output_dir: Directory where terrain_class.tif will be written.
        hand_path: Height Above Nearest Drainage raster.
        tpi_path: Topographic Position Index raster.
        curvature_path: Profile curvature raster (unused in new model, kept for API compat).
        flow_acc_path: Flow accumulation raster.
        twi_path: Topographic Wetness Index raster.

    Returns:
        Path to the output terrain_class.tif.
    """
    output_path = str(Path(output_dir) / "terrain_class.tif")

    # --- Load all input layers ------------------------------------------------
    def _load(path: str | None) -> tuple[np.ndarray | None, float | None]:
        if path is None or not Path(path).exists():
            return None, None
        with rasterio.open(path) as src:
            return src.read(1).astype(np.float64), src.nodata

    # Reference metadata from filled DEM
    with rasterio.open(filled_dem_path) as src:
        ref_shape = (src.height, src.width)
        meta = src.meta.copy()

    hand, nodata_hand = _load(hand_path)
    flow_acc, nodata_fa = _load(flow_acc_path)
    twi, nodata_twi = _load(twi_path)

    # --- Combined nodata mask -------------------------------------------------
    nodata_mask = np.zeros(ref_shape, dtype=bool)
    for data, nodata in [
        (hand, nodata_hand),
        (flow_acc, nodata_fa),
        (twi, nodata_twi),
    ]:
        if data is not None and nodata is not None:
            nodata_mask |= data == nodata
            nodata_mask |= ~np.isfinite(data)
        elif data is not None:
            nodata_mask |= ~np.isfinite(data)

    valid = ~nodata_mask

    # --- Compute percentile thresholds from actual data -----------------------
    def _percentile(data: np.ndarray | None, p: float) -> float:
        if data is None:
            return 0.0
        vals = data[valid]
        return float(np.percentile(vals, p)) if vals.size > 0 else 0.0

    fa_p99 = _percentile(flow_acc, 99)
    twi_p55 = _percentile(twi, 55)
    twi_p35 = _percentile(twi, 35)

    logger.info(
        "classify_terrain thresholds fa_p99=%.2f twi_p55=%.2f twi_p35=%.2f",
        fa_p99, twi_p55, twi_p35,
    )

    # --- Default: SIN_RIESGO (class 0) — transparent on map ------------------
    classified = np.full(ref_shape, TERRAIN_SIN_RIESGO, dtype=np.uint8)

    # --- Class 3: RIESGO_MEDIO — Moderate flood risk -------------------------
    # HAND < 1.5m AND TWI > P35 — low-ish terrain with moderate wetness
    if hand is not None and twi is not None:
        medio_mask = valid & (hand < 1.5) & (twi > twi_p35)
        classified[medio_mask] = TERRAIN_RIESGO_MEDIO

    # --- Class 2: RIESGO_ALTO — High flood risk (overrides medio) ------------
    # HAND < 0.8m AND TWI > P55 — very low terrain, wet
    # No TPI: center of wide flat depressions has TPI ≈ 0, would be missed
    if hand is not None and twi is not None:
        alto_mask = valid & (hand < 0.8) & (twi > twi_p55)
        classified[alto_mask] = TERRAIN_RIESGO_ALTO

    # --- Class 1: DRENAJE_NATURAL — Natural drainage lines (highest priority) -
    # flow_acc > P99 AND HAND < 1.0m — concentrated flow channels
    if flow_acc is not None and hand is not None:
        drenaje_mask = valid & (flow_acc > fa_p99) & (hand < 1.0)
        classified[drenaje_mask] = TERRAIN_DRENAJE_NATURAL

    # --- Nodata ---------------------------------------------------------------
    out_nodata = np.uint8(255)
    classified[nodata_mask] = out_nodata

    meta.update(
        {"dtype": "uint8", "count": 1, "driver": "GTiff", "nodata": int(out_nodata)}
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **meta) as dst:
        dst.write(classified, 1)

    return output_path


# ---------------------------------------------------------------------------
# k) Download DEM from Google Earth Engine
# ---------------------------------------------------------------------------


def download_dem_from_gee(
    zona_geometry: dict[str, Any],
    output_path: str,
    scale: int = 30,
) -> str:
    """Download Copernicus GLO-30 DEM from GEE, clipped to a zona geometry.

    Uses ``ee.Image.getDownloadURL()`` with GeoTIFF format and ``requests``
    to stream the file to disk.  Suitable for small-to-medium areas
    (~30km x 30km at 30m ≈ 4 MB).

    Args:
        zona_geometry: GeoJSON geometry dict (Polygon/MultiPolygon) defining
            the area of interest.
        output_path: Where to write the downloaded GeoTIFF.
        scale: Pixel resolution in meters (default 30 for GLO-30).

    Returns:
        output_path on success.

    Raises:
        RuntimeError: If GEE is not initialized or the download fails.
    """
    import ee
    import requests

    # Copernicus DEM is an ImageCollection (tiles), not a single Image
    dem = ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM").mosaic()
    region = ee.Geometry(zona_geometry)
    clipped = dem.clip(region)

    url = clipped.getDownloadURL(
        {
            "format": "GEO_TIFF",
            "scale": scale,
            "region": region,
            "crs": "EPSG:4326",
        }
    )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Download to a temporary file first
    tmp_path = str(Path(output_path).with_suffix(".tmp.tif"))

    response = requests.get(url, stream=True, timeout=300)
    response.raise_for_status()

    with open(tmp_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    # Re-compress with DEFLATE (WhiteboxTools doesn't support GEE's compression)
    import rasterio

    with rasterio.open(tmp_path) as src:
        profile = src.profile.copy()
        profile.update(compress="deflate", predictor=2)
        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(src.read())

    Path(tmp_path).unlink(missing_ok=True)

    return output_path


# ---------------------------------------------------------------------------
# l) Delineate watershed basins
# ---------------------------------------------------------------------------


def delineate_basins(
    flow_dir_path: str,
    output_raster_path: str,
    output_geojson_path: str,
    min_area_ha: float = 10.0,
) -> str:
    """Delineate watershed basins from a D8 flow direction raster.

    Steps:
        1. Run WhiteboxTools ``basins()`` on the flow direction raster.
        2. Vectorize the resulting basin raster using ``rasterio.features.shapes``.
        3. Filter out micro-basins smaller than *min_area_ha* hectares.
        4. Write the remaining polygons to a GeoJSON file.

    Args:
        flow_dir_path: Path to D8 flow direction raster (from ``compute_flow_direction``).
        output_raster_path: Where to write the intermediate basin raster.
        output_geojson_path: Where to write the vectorized basin polygons.
        min_area_ha: Minimum basin area in hectares; smaller basins are discarded.

    Returns:
        output_geojson_path on success.
    """
    Path(output_raster_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_geojson_path).parent.mkdir(parents=True, exist_ok=True)

    # 1. Run WBT basins
    wbt = _get_wbt()
    wbt.basins(flow_dir_path, output_raster_path)

    # 2. Vectorize
    with rasterio.open(output_raster_path) as src:
        basin_data = src.read(1)
        transform = src.transform
        crs = src.crs

    # Prepare reprojection to EPSG:4326 if needed (frontend/PostGIS expect 4326)
    need_reproject = crs and crs.is_projected
    if need_reproject:
        from pyproj import Transformer

        transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)

    # Read nodata value to filter out the "nodata basin"
    with rasterio.open(output_raster_path) as src:
        basins_nodata = src.nodata

    features: list[dict[str, Any]] = []
    for geom, basin_id in shapes(basin_data, transform=transform):
        if basin_id == 0 or basin_id == basins_nodata:
            continue  # skip nodata / background

        poly = shape(geom)
        # 3. Compute area in hectares
        if crs and crs.is_projected:
            # UTM: poly.area is already in m²
            area_m2 = poly.area
        else:
            # Geographic CRS: approximate conversion from deg² to m²
            centroid = poly.centroid
            lat_rad = np.radians(centroid.y)
            m_per_deg_lat = 111_320.0
            m_per_deg_lon = 111_320.0 * np.cos(lat_rad)
            area_m2 = poly.area * m_per_deg_lat * m_per_deg_lon
        area_ha = area_m2 / 10_000.0

        if area_ha < min_area_ha:
            continue

        # Reproject geometry to EPSG:4326 for GeoJSON output
        if need_reproject:
            from shapely.ops import transform as shapely_transform

            poly_4326 = shapely_transform(transformer.transform, poly)
            out_geom = mapping(poly_4326)
        else:
            out_geom = geom

        features.append(
            {
                "type": "Feature",
                "geometry": out_geom,
                "properties": {
                    "basin_id": int(basin_id),
                    "area_ha": round(area_ha, 2),
                },
            }
        )

    geojson = {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": "EPSG:4326"},
        },
        "features": features,
    }

    with open(output_geojson_path, "w") as f:
        json.dump(geojson, f)

    return output_geojson_path


# ---------------------------------------------------------------------------
# m) Convert GeoTIFF to Cloud-Optimized GeoTIFF (COG)
# ---------------------------------------------------------------------------


def convert_to_cog(input_path: str, output_path: str | None = None) -> str:
    """Convert a GeoTIFF to Cloud-Optimized GeoTIFF (COG) format.

    Uses rio-cogeo for proper COG creation with overviews and tiling.
    If output_path is not provided, creates a .cog.tif alongside the input.

    Args:
        input_path: Path to the input GeoTIFF.
        output_path: Where to write the COG. Defaults to ``{input}.cog.tif``.

    Returns:
        output_path on success.

    Raises:
        RuntimeError: If COG conversion fails.
    """
    from rio_cogeo.cogeo import cog_translate
    from rio_cogeo.profiles import cog_profiles

    if output_path is None:
        p = Path(input_path)
        output_path = str(p.with_suffix(".cog.tif"))

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Use DEFLATE profile — good compression for terrain data
    output_profile = cog_profiles.get("deflate")

    config = {
        "GDAL_NUM_THREADS": "ALL_CPUS",
        "GDAL_TIFF_OVR_BLOCKSIZE": "512",
    }

    cog_translate(
        input_path,
        output_path,
        output_profile,
        overview_level=5,
        overview_resampling="nearest",
        config=config,
        quiet=True,
    )

    return output_path
