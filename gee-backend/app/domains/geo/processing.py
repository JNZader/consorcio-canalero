"""
Pure terrain analysis functions using rasterio, numpy, and whiteboxtools.

Each function takes file paths and returns file paths — no Celery, no DB.
These are the computational building blocks for the DEM pipeline.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.features import shapes
from rasterio.mask import mask as rasterio_mask
from rasterio.transform import from_bounds
from shapely.geometry import box, mapping, shape
from whitebox import WhiteboxTools

# ---------------------------------------------------------------------------
# WhiteboxTools singleton
# ---------------------------------------------------------------------------

_wbt: WhiteboxTools | None = None


def _get_wbt() -> WhiteboxTools:
    """Lazily initialise a WhiteboxTools instance (verbose off)."""
    global _wbt  # noqa: PLW0603
    if _wbt is None:
        _wbt = WhiteboxTools()
        _wbt.set_verbose_mode(False)
    return _wbt


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
        out_image, out_transform = rasterio_mask(
            src, [mapping(geom)], crop=True
        )
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
# b) Fill sinks
# ---------------------------------------------------------------------------


def fill_sinks(dem_path: str, output_path: str) -> str:
    """Fill depressions in a DEM using WhiteboxTools.

    Args:
        dem_path: Input DEM path.
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


def compute_flow_accumulation(flow_dir_path: str, output_path: str) -> str:
    """D8 flow accumulation using WhiteboxTools.

    Args:
        flow_dir_path: Path to the D8 flow direction raster.
        output_path: Output flow accumulation raster path.

    Returns:
        output_path on success.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    wbt = _get_wbt()
    wbt.d8_flow_accumulation(flow_dir_path, output_path)
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
    for geom, value in shapes(drainage_binary, mask=drainage_binary, transform=transform):
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
# j) Terrain classification
# ---------------------------------------------------------------------------

# Classification codes
TERRAIN_PLANO_SECO = 0
TERRAIN_PLANO_HUMEDO = 1
TERRAIN_DRENAJE_ACTIVO = 2
TERRAIN_ACUMULACION = 3

_SLOPE_THRESHOLD_DEG = 1.0
_FLOW_ACC_HIGH_THRESHOLD = 5000


def classify_terrain(
    slope_path: str,
    twi_path: str,
    flow_acc_path: str,
    output_path: str,
    slope_threshold: float = _SLOPE_THRESHOLD_DEG,
    flow_acc_threshold: int = _DEFAULT_DRAINAGE_THRESHOLD,
    flow_acc_high_threshold: int = _FLOW_ACC_HIGH_THRESHOLD,
) -> str:
    """Classify terrain into categories based on slope, TWI, and flow accumulation.

    Categories:
        0 = plano_seco:     slope < threshold AND twi < median
        1 = plano_humedo:   slope < threshold AND twi >= median
        2 = drenaje_activo: slope >= threshold AND flow_acc > flow_acc_threshold
        3 = acumulacion:    flow_acc > flow_acc_high_threshold

    The acumulacion class takes priority (checked last, overwrites).

    Args:
        slope_path: Slope raster in degrees.
        twi_path: TWI raster.
        flow_acc_path: Flow accumulation raster.
        output_path: Output classified raster path.
        slope_threshold: Flat terrain threshold in degrees.
        flow_acc_threshold: Flow accumulation threshold for active drainage.
        flow_acc_high_threshold: High flow accumulation threshold for accumulation zones.

    Returns:
        output_path on success.
    """
    with rasterio.open(slope_path) as src:
        slope = src.read(1).astype(np.float64)
        nodata_slope = src.nodata
        meta = src.meta.copy()

    with rasterio.open(twi_path) as src:
        twi = src.read(1).astype(np.float64)
        nodata_twi = src.nodata

    with rasterio.open(flow_acc_path) as src:
        flow_acc = src.read(1).astype(np.float64)
        nodata_fa = src.nodata

    # Combined nodata mask
    nodata_mask = np.zeros(slope.shape, dtype=bool)
    if nodata_slope is not None:
        nodata_mask |= slope == nodata_slope
    if nodata_twi is not None:
        nodata_mask |= twi == nodata_twi
    if nodata_fa is not None:
        nodata_mask |= flow_acc == nodata_fa

    # Compute TWI median only over valid pixels
    valid_twi = twi[~nodata_mask]
    twi_median = float(np.median(valid_twi)) if valid_twi.size > 0 else 0.0

    # Default: plano_seco
    classified = np.full(slope.shape, TERRAIN_PLANO_SECO, dtype=np.uint8)

    flat = slope < slope_threshold
    steep = ~flat

    # plano_humedo: flat + high TWI
    classified[flat & (twi >= twi_median)] = TERRAIN_PLANO_HUMEDO

    # drenaje_activo: steep + high flow accumulation
    classified[steep & (flow_acc > flow_acc_threshold)] = TERRAIN_DRENAJE_ACTIVO

    # acumulacion: very high flow accumulation (overrides previous)
    classified[flow_acc > flow_acc_high_threshold] = TERRAIN_ACUMULACION

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

    dem = ee.Image("COPERNICUS/DEM/GLO30/V20").select("DEM")
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

    response = requests.get(url, stream=True, timeout=300)
    response.raise_for_status()

    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

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

    features: list[dict[str, Any]] = []
    for geom, basin_id in shapes(basin_data, transform=transform):
        if basin_id == 0:
            continue  # skip nodata / background

        poly = shape(geom)
        # 3. Compute area in hectares (approximate for EPSG:4326)
        # Use a rough conversion: 1 degree lat ≈ 111_320 m
        # For better accuracy, reproject — but this is good enough for filtering
        centroid = poly.centroid
        lat_rad = np.radians(centroid.y)
        # meters per degree
        m_per_deg_lat = 111_320.0
        m_per_deg_lon = 111_320.0 * np.cos(lat_rad)

        bounds = poly.bounds  # (minx, miny, maxx, maxy)
        width_m = (bounds[2] - bounds[0]) * m_per_deg_lon
        height_m = (bounds[3] - bounds[1]) * m_per_deg_lat
        # Use shapely area in deg^2, convert to m^2
        area_m2 = poly.area * m_per_deg_lat * m_per_deg_lon
        area_ha = area_m2 / 10_000.0

        if area_ha < min_area_ha:
            continue

        features.append(
            {
                "type": "Feature",
                "geometry": geom,
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
            "properties": {"name": str(crs) if crs else "EPSG:4326"},
        },
        "features": features,
    }

    with open(output_geojson_path, "w") as f:
        json.dump(geojson, f)

    return output_geojson_path
