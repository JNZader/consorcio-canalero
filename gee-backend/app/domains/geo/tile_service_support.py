"""Support helpers for tile rendering."""

from __future__ import annotations

import io
import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
import rasterio
from PIL import Image as PILImage
from pyproj import CRS
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject, transform_bounds
from scipy.ndimage import median_filter

try:
    import cv2  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover — cv2 is optional, scipy fallback is used.
    cv2 = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


# Smoothing methods accepted by ``smooth_elevation_tile``. Public so the API
# layer can list them in the OpenAPI description without drifting.
TERRAIN_SMOOTHING_METHODS: tuple[str, ...] = (
    "median3",
    "median5",
    "median9",
    "median15",
    "despike_low",  # threshold 0.5 m  — aggressive, may flatten subtle channel edges
    "despike_med",  # threshold 1.5 m  — balanced, recommended default
    "despike_high",  # threshold 3.0 m  — conservative, only buildings and tall trees
    # Legacy alias maintained for backwards compatibility with older clients
    # that still send the original method name.
    "despike15",
)
TERRAIN_SMOOTHING_METHODS_DESCRIPTION = (
    "Visualization-only DEM smoothing for terrain-rgb tiles. "
    "Supported values: median3, median5, median9, median15 "
    "(plain median filter with the given kernel size); "
    "despike_low | despike_med | despike_high "
    "(15×15 median + replace positive spikes above 0.5/1.5/3.0 m); "
    "despike15 (legacy alias for despike_med)."
)

# Buffer halo (in pixels) read around terrain tiles so that the kernel-based
# smoothing has access to neighbour elevations. Eliminates the seam that
# ``mode="nearest"`` would otherwise produce at tile borders.
TERRAIN_SMOOTHING_BUFFER_PX = 8

# Mapping from public method name → (kernel_size, optional_despike_threshold).
# When ``threshold`` is None this is a plain median; otherwise the despike
# pipeline runs (replace positive spikes whose elevation exceeds local_median
# by ``threshold`` metres).
_SMOOTHING_PARAMS: dict[str, tuple[int, Optional[float]]] = {
    "median3": (3, None),
    "median5": (5, None),
    "median9": (9, None),
    "median15": (15, None),
    "despike_low": (15, 0.5),
    "despike_med": (15, 1.5),
    "despike_high": (15, 3.0),
    "despike15": (15, 1.5),  # legacy alias
}

DEFAULT_COLORMAPS: dict[str, str] = {
    "dem_raw": "terrain",
    "slope": "rdylgn_r",
    "aspect": "hsv",
    "twi": "blues",
    "curvature": "rdbu_r",
    "profile_curvature": "rdbu_r",
    "tpi": "rdbu_r",
    "flow_acc": "ylgnbu",
    "hand": "ylorrd",
    "terrain_class": "_categorical",
    "flow_dir": "spectral",
    "flood_risk": "rdylgn_r",
    "drainage_need": "ylorbr",
}

DEFAULT_RESCALE: dict[str, tuple[float, float]] = {
    "dem_raw": (100.0, 145.0),
    "slope": (0.0, 1.0),
    "twi": (6.0, 19.0),
    "profile_curvature": (-0.001, 0.001),
    "tpi": (-1.5, 1.5),
    "hand": (0.0, 4.0),
    "terrain_class": (0.0, 4.0),
    "flow_dir": (0.0, 128.0),
    "flood_risk": (10.0, 90.0),
    "drainage_need": (20.0, 70.0),
}

CATEGORICAL_COLORS: dict[str, dict[int, tuple[int, int, int, int]]] = {
    "terrain_class": {
        0: (76, 175, 80, 180),
        1: (30, 136, 229, 255),
        2: (211, 47, 47, 255),
        3: (255, 143, 0, 255),
    },
}

CATEGORICAL_TYPES = set(CATEGORICAL_COLORS.keys())

RANGE_CONFIGS: dict[str, list[dict]] = {
    "flood_risk": [
        {"label": "Bajo", "min": 0, "max": 30, "color": "#1a9850"},
        {"label": "Medio", "min": 30, "max": 55, "color": "#fee08b"},
        {"label": "Alto", "min": 55, "max": 75, "color": "#fc8d59"},
        {"label": "Crítico", "min": 75, "max": 100, "color": "#d73027"},
    ],
    "drainage_need": [
        {"label": "Bajo", "min": 0, "max": 30, "color": "#fff7ec"},
        {"label": "Medio", "min": 30, "max": 50, "color": "#fdd49e"},
        {"label": "Alto", "min": 50, "max": 70, "color": "#e34a33"},
        {"label": "Crítico", "min": 70, "max": 100, "color": "#b30000"},
    ],
    "twi": [
        {"label": "Seco", "min": 6, "max": 9, "color": "#f7fbff"},
        {"label": "Normal", "min": 9, "max": 12, "color": "#6baed6"},
        {"label": "Húmedo", "min": 12, "max": 16, "color": "#2171b5"},
        {"label": "Muy Húmedo", "min": 16, "max": 19, "color": "#08306b"},
    ],
    "hand": [
        {"label": "Muy Bajo (<0.5m)", "min": 0, "max": 0.5, "color": "#bd0026"},
        {"label": "Bajo (0.5-1m)", "min": 0.5, "max": 1.0, "color": "#f03b20"},
        {"label": "Medio (1-2m)", "min": 1.0, "max": 2.0, "color": "#fd8d3c"},
        {"label": "Alto (>2m)", "min": 2.0, "max": 4.0, "color": "#ffffb2"},
    ],
    "slope": [
        {
            "label": "Muy baja zona I (<0.5 m/1000m)",
            "min": 0,
            "max": 0.0265,
            "color": "#0b7d3b",
        },
        {
            "label": "Muy baja zona II (0.5-2.1 m/1000m)",
            "min": 0.0265,
            "max": 0.1227,
            "color": "#1a9850",
        },
        {
            "label": "Baja zona (2.1-4.2 m/1000m)",
            "min": 0.1227,
            "max": 0.2420,
            "color": "#91cf60",
        },
        {
            "label": "Suave zona (4.2-6.9 m/1000m)",
            "min": 0.2420,
            "max": 0.3964,
            "color": "#d9ef8b",
        },
        {
            "label": "Moderada zona (6.9-15.3 m/1000m)",
            "min": 0.3964,
            "max": 0.8754,
            "color": "#fc8d59",
        },
        {
            "label": "Alta puntual (>15.3 m/1000m)",
            "min": 0.8754,
            "max": 90.0,
            "color": "#d73027",
        },
    ],
    "dem_raw": [
        {"label": "100-105m", "min": 100, "max": 105, "color": "#08306b"},
        {"label": "105-110m", "min": 105, "max": 110, "color": "#2171b5"},
        {"label": "110-115m", "min": 110, "max": 115, "color": "#6baed6"},
        {"label": "115-120m", "min": 115, "max": 120, "color": "#a1d99b"},
        {"label": "120-125m", "min": 120, "max": 125, "color": "#ffffbf"},
        {"label": "125-130m", "min": 125, "max": 130, "color": "#fdae61"},
        {"label": "130-135m", "min": 130, "max": 135, "color": "#f46d43"},
        {"label": "135-145m", "min": 135, "max": 145, "color": "#a50026"},
    ],
    "flow_acc": [
        {"label": "Mínimo (1 celda)", "min": 1, "max": 1.5, "color": "#ffffcc"},
        {"label": "Muy bajo (2-6)", "min": 1.5, "max": 6, "color": "#d9f0a3"},
        {"label": "Bajo (6-53)", "min": 6, "max": 53, "color": "#addd8e"},
        {"label": "Moderado (53-210)", "min": 53, "max": 210, "color": "#78c679"},
        {"label": "Alto (210-6.525)", "min": 210, "max": 6525.22, "color": "#41b6c4"},
        {
            "label": "Muy alto (>6.525)",
            "min": 6525.22,
            "max": 487848,
            "color": "#0c2c84",
        },
    ],
    "profile_curvature": [
        {"label": "Cóncavo", "min": -0.001, "max": -0.0002, "color": "#b2182b"},
        {"label": "Plano", "min": -0.0002, "max": 0.0002, "color": "#f7f7f7"},
        {"label": "Convexo", "min": 0.0002, "max": 0.001, "color": "#2166ac"},
    ],
    "tpi": [
        {"label": "Valle", "min": -1.5, "max": -0.5, "color": "#b2182b"},
        {"label": "Llano", "min": -0.5, "max": 0.5, "color": "#f7f7f7"},
        {"label": "Cresta", "min": 0.5, "max": 1.5, "color": "#2166ac"},
    ],
}

LOG_SCALE_TYPES = {"flow_acc"}
ELEVATION_TYPES = {"dem_raw"}
WEB_MERCATOR_CRS = CRS.from_epsg(3857)
WEB_MERCATOR_HALF_WORLD = 20037508.342789244


def encode_terrain_rgb(data: np.ndarray) -> np.ndarray:
    elevation = np.clip(data.astype(np.float64), -10000, 1667721.5)
    encoded = ((elevation + 10000.0) * 10.0).astype(np.uint32)
    r = (encoded // 65536).astype(np.uint8)
    g = ((encoded % 65536) // 256).astype(np.uint8)
    b = (encoded % 256).astype(np.uint8)
    return np.stack([r, g, b], axis=0)


@lru_cache(maxsize=32)
def get_elevation_baseline(file_path: str) -> float:
    with rasterio.open(file_path) as src:
        band = src.read(1, masked=True)
        if band.count() == 0:
            return 0.0
        return float(band.min())


def tile_bounds_3857(x: int, y: int, z: int) -> tuple[float, float, float, float]:
    world_span = WEB_MERCATOR_HALF_WORLD * 2.0
    tile_span = world_span / (2**z)
    left = -WEB_MERCATOR_HALF_WORLD + (x * tile_span)
    right = left + tile_span
    top = WEB_MERCATOR_HALF_WORLD - (y * tile_span)
    bottom = top - tile_span
    return left, bottom, right, top


# ── Zona clip mask ───────────────────────────────────────────────────────────
# Visual raster overlays (colormaps/categoricals) are rendered from pipeline
# GeoTIFFs whose extent is the PROCESSING bbox — noticeably larger than the
# consorcio. Only the GEE satellite image was clipped server-side, so every
# other overlay bled over the whole province. This mask clips the rendered
# tiles to the consorcio outline. Terrain-RGB elevation tiles are NOT clipped
# (the 3D mesh geometry must keep its full extent).

ZONA_CLIP_GEOJSON_ENV = "ZONA_CLIP_GEOJSON"
_ZONA_CLIP_DEFAULT_PATH = "/app/data/zona/zona_ampliada.geojson"


@lru_cache(maxsize=1)
def _zona_geometry_3857():
    """Union of the zona polygons reprojected to EPSG:3857, or None.

    Cached for the process lifetime. Missing/invalid file → None, and tiles
    render unclipped (graceful degradation, never a 500 over a mask).
    """
    path = Path(os.environ.get(ZONA_CLIP_GEOJSON_ENV, _ZONA_CLIP_DEFAULT_PATH))
    if not path.exists():
        logger.warning("Zona clip geojson not found at %s — tiles render unclipped", path)
        return None
    try:
        from pyproj import Transformer
        from shapely.geometry import shape
        from shapely.ops import transform as shp_transform, unary_union

        data = json.loads(path.read_text())
        features = data.get("features", [data] if data.get("type") == "Feature" else [])
        geoms = [shape(f["geometry"]) for f in features if f.get("geometry")]
        if not geoms:
            return None
        union = unary_union(geoms)
        to_3857 = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform
        return shp_transform(to_3857, union)
    except Exception as exc:  # pragma: no cover — defensive: bad file must not kill tiles
        logger.warning("Could not load zona clip geometry: %s", exc)
        return None


def zona_clip_mask(x: int, y: int, z: int, tilesize: int = 256) -> Optional[np.ndarray]:
    """Boolean (tilesize, tilesize) mask — True inside the consorcio zona.

    Returns None when the zona geometry is unavailable or the tile does not
    intersect it at all is handled by the all-False mask (renders empty).
    """
    geom = _zona_geometry_3857()
    if geom is None:
        return None
    from rasterio import features as rio_features

    west, south, east, north = tile_bounds_3857(x, y, z)
    tile_transform = from_bounds(west, south, east, north, tilesize, tilesize)
    return rio_features.geometry_mask(
        [geom],
        out_shape=(tilesize, tilesize),
        transform=tile_transform,
        invert=True,
    )


def bounds_intersect(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> bool:
    a_left, a_bottom, a_right, a_top = a
    b_left, b_bottom, b_right, b_top = b
    return not (a_right <= b_left or a_left >= b_right or a_top <= b_bottom or a_bottom >= b_top)


def read_categorical_tile(
    file_path: str | Path,
    x: int,
    y: int,
    z: int,
    *,
    tilesize: int = 256,
    dst_nodata: int = 255,
) -> tuple[np.ndarray, np.ndarray] | None:
    tile_bounds = tile_bounds_3857(x, y, z)
    dst_transform = from_bounds(*tile_bounds, width=tilesize, height=tilesize)
    with rasterio.open(file_path) as src:
        src_bounds_3857 = transform_bounds(src.crs, WEB_MERCATOR_CRS, *src.bounds)
        if not bounds_intersect(tile_bounds, src_bounds_3857):
            return None
        src_nodata = src.nodata if src.nodata is not None else dst_nodata
        tile = np.full((tilesize, tilesize), dst_nodata, dtype=np.uint8)
        reproject(
            source=rasterio.band(src, 1),
            destination=tile,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=src_nodata,
            dst_transform=dst_transform,
            dst_crs=WEB_MERCATOR_CRS,
            dst_nodata=dst_nodata,
            resampling=Resampling.nearest,
        )
    mask = np.where(tile == dst_nodata, 0, 255).astype(np.uint8)
    return tile, mask


def render_categorical_png(
    raw: np.ndarray,
    mask: np.ndarray,
    colors: dict[int, tuple[int, int, int, int]],
    hidden_classes: Optional[set[int]] = None,
) -> bytes:
    rgba = np.zeros((*raw.shape, 4), dtype=np.uint8)
    for cls_val, color in colors.items():
        px = (raw == cls_val) & (mask > 0)
        if px.any():
            rgba[px] = color
    if hidden_classes:
        for cls_val in hidden_classes:
            rgba[raw == cls_val, 3] = 0
    buf = io.BytesIO()
    PILImage.fromarray(rgba, "RGBA").save(buf, format="PNG")
    return buf.getvalue()


def read_elevation_tile(
    file_path: str | Path,
    x: int,
    y: int,
    z: int,
    *,
    tilesize: int = 256,
    buffer_px: int = 0,
) -> tuple[np.ndarray, np.ndarray] | None:
    """Read a Web-Mercator elevation tile from a COG.

    When ``buffer_px > 0`` the returned arrays have shape
    ``(tilesize + 2*buffer_px, tilesize + 2*buffer_px)`` and cover the tile
    plus a halo of ``buffer_px`` pixels on every side. The caller is expected
    to apply per-pixel transforms (e.g. smoothing) and then crop back to the
    center ``tilesize×tilesize`` window. This eliminates seams between
    adjacent tiles when a kernel-based filter is applied, because each tile
    sees the neighbouring elevations instead of synthesising them via
    ``mode="nearest"``.

    For tiles at the edge of the COG, the halo may extend past the raster
    coverage: those pixels come back as ``NaN`` and the ``valid_mask`` flags
    them as ``False`` — callers that consume the buffer (the smoothing
    pipeline) treat invalid pixels accordingly.
    """
    tile_bounds = tile_bounds_3857(x, y, z)
    minx, miny, maxx, maxy = tile_bounds
    if buffer_px > 0:
        # Expand the read window by ``buffer_px`` map units (Web Mercator px ≈ tile px).
        px_size_x = (maxx - minx) / tilesize
        px_size_y = (maxy - miny) / tilesize
        minx -= buffer_px * px_size_x
        maxx += buffer_px * px_size_x
        miny -= buffer_px * px_size_y
        maxy += buffer_px * px_size_y
    width = tilesize + 2 * buffer_px
    height = tilesize + 2 * buffer_px
    dst_transform = from_bounds(minx, miny, maxx, maxy, width=width, height=height)
    with rasterio.open(file_path) as src:
        src_bounds_3857 = transform_bounds(src.crs, WEB_MERCATOR_CRS, *src.bounds)
        if not bounds_intersect((minx, miny, maxx, maxy), src_bounds_3857):
            return None
        tile = np.full((height, width), np.nan, dtype=np.float32)
        reproject(
            source=rasterio.band(src, 1),
            destination=tile,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=src.nodata,
            dst_transform=dst_transform,
            dst_crs=WEB_MERCATOR_CRS,
            dst_nodata=np.nan,
            resampling=Resampling.bilinear,
        )
    return tile, np.isfinite(tile)


def crop_center(arr: np.ndarray, buffer_px: int) -> np.ndarray:
    """Crop a 2D array by removing ``buffer_px`` from every edge."""
    if buffer_px <= 0:
        return arr
    return arr[buffer_px:-buffer_px, buffer_px:-buffer_px]


def _median_blur(arr: np.ndarray, kernel_size: int) -> np.ndarray:
    """Median filter with the fastest available backend.

    For ``kernel_size in (3, 5)`` we use ``cv2.medianBlur`` when OpenCV is
    installed: it accepts float32 directly and is ~30× faster than scipy on
    a 256×256 tile. For kernels ≥7 OpenCV requires uint8, which is too lossy
    for elevation data (1 m resolution would erase the very DSM artefacts we
    want to detect), so we keep scipy for those.
    """
    if cv2 is not None and kernel_size in (3, 5):
        # Avoid an unconditional alloc — the caller commonly already feeds a
        # contiguous float32 array (e.g. the final 3×3 cleanup pass after a
        # ``np.where``), in which case ``ascontiguousarray`` would still
        # allocate a copy.
        if arr.dtype == np.float32 and arr.flags.c_contiguous:
            contiguous = arr
        else:
            contiguous = np.ascontiguousarray(arr, dtype=np.float32)
        return cv2.medianBlur(contiguous, kernel_size)
    return median_filter(arr, size=kernel_size, mode="nearest")


def smooth_elevation_tile(
    elevation: np.ndarray,
    valid_mask: np.ndarray,
    method: str | None,
) -> np.ndarray:
    """Return a visualization-only smoothed elevation tile.

    Used for MapLibre terrain-rgb tiles when exaggerated terrain (e.g. 200×)
    makes local DSM spikes from trees/buildings dominate the visual reading.
    The source DEM is untouched; smoothing is applied only to the rendered
    tile. See ``TERRAIN_SMOOTHING_METHODS_DESCRIPTION`` for accepted method
    names. The input is expected to be a tile already padded with a buffer
    halo (see ``TERRAIN_SMOOTHING_BUFFER_PX``) — the caller is responsible
    for cropping the result back to the visible tile size.
    """
    if method in (None, "", "none"):
        return elevation

    params = _SMOOTHING_PARAMS.get(method)
    if params is None:
        logger.warning("Unknown terrain_smoothing method: %s", method)
        return elevation

    kernel_size, despike_threshold = params

    # Fast path: when every pixel is valid we can skip the NaN-fill round
    # trip (saves ~1-2 ms per tile in the dense interior).
    if valid_mask.all():
        filled = elevation.astype(np.float32, copy=False)
    else:
        if not np.any(valid_mask):
            return elevation
        # Median filters are not NaN-aware. Fill invalid pixels with the
        # median of valid elevations, filter, then restore the invalid mask.
        #
        # IMPORTANT: only consider the CENTER of the tile when there's a
        # buffer halo. The halo may straddle the edge of the COG and contain
        # mostly NaNs (or, worse, neighbouring elevations several metres
        # off), so including it in the fill median pulls the value toward
        # an unrelated regime and creates a visible halo in the rendered
        # 256×256 window. The buffer is always the same per-tile, so we
        # infer it from the array shape rather than threading another param.
        h, w = elevation.shape
        if h > 256 and w > 256 and (h - 256) % 2 == 0 and (w - 256) % 2 == 0:
            by = (h - 256) // 2
            bx = (w - 256) // 2
            center_elev = elevation[by : by + 256, bx : bx + 256]
            center_mask = valid_mask[by : by + 256, bx : bx + 256]
            sample = center_elev[center_mask] if center_mask.any() else elevation[valid_mask]
        else:
            sample = elevation[valid_mask]
        valid_median = float(np.nanmedian(sample))
        filled = np.where(valid_mask, elevation, valid_median).astype(np.float32)

    if despike_threshold is None:
        smoothed = _median_blur(filled, kernel_size)
        return np.where(valid_mask, smoothed, elevation).astype(np.float32)

    # Despike pipeline. DSM artefacts from trees/buildings are mostly
    # positive, localized peaks; we replace those while preserving the
    # broader low-frequency terrain shape captured by the local median.
    local_median = _median_blur(filled, kernel_size)
    positive_spikes = valid_mask & ((filled - local_median) > despike_threshold)
    despiked = np.where(positive_spikes, local_median, filled)
    # A light final 3×3 pass removes single-pixel leftovers without
    # flattening the whole tile as much as a full median15 would.
    despiked = _median_blur(despiked.astype(np.float32), 3)
    return np.where(valid_mask, despiked, elevation).astype(np.float32)


def render_terrain_rgb_png(data: np.ndarray, valid_mask: np.ndarray) -> bytes:
    if not np.any(valid_mask):
        raise ValueError("No valid elevation pixels to render")
    terrain_rgb = encode_terrain_rgb(np.where(valid_mask, data, 0.0))
    rgb = np.zeros((data.shape[0], data.shape[1], 3), dtype=np.uint8)
    rgb[..., 0], rgb[..., 1], rgb[..., 2] = (
        terrain_rgb[0],
        terrain_rgb[1],
        terrain_rgb[2],
    )
    buf = io.BytesIO()
    PILImage.fromarray(rgb, "RGB").save(buf, format="PNG")
    return buf.getvalue()


def render_flat_terrain_rgb_png(*, tilesize: int = 256, elevation: float = 0.0) -> bytes:
    return render_terrain_rgb_png(
        np.full((tilesize, tilesize), elevation, dtype=np.float32),
        np.ones((tilesize, tilesize), dtype=bool),
    )


def render_continuous_with_ranges(
    img,
    layer_tipo: str,
    cmap_name: str,
    hidden_ranges: set[int],
) -> bytes:
    from rio_tiler.colormap import cmap as colormap_registry

    original_data = img.data[0].astype(np.float64).copy()
    nodata_mask = img.mask
    if layer_tipo in LOG_SCALE_TYPES:
        img.data[:] = np.where(
            img.data > 0, np.log1p(img.data.astype(np.float64)).astype(np.float32), 0
        )
        img.rescale(((0.0, 13.0),))
    else:
        rescale = DEFAULT_RESCALE.get(layer_tipo)
        if rescale:
            img.rescale(((rescale[0], rescale[1]),))

    cmap_data = colormap_registry.get(cmap_name)
    rescaled = np.clip(img.data[0], 0, 255).astype(np.uint8)
    h, w = rescaled.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    valid_px = nodata_mask > 0

    for val in range(256):
        px = (rescaled == val) & valid_px
        if px.any():
            rgba[px] = cmap_data.get(val, (0, 0, 0, 255))

    range_cfg = RANGE_CONFIGS.get(layer_tipo, [])
    for idx in hidden_ranges:
        if idx < len(range_cfg):
            r = range_cfg[idx]
            in_range = (
                original_data >= r["min"]
                if idx == len(range_cfg) - 1
                else ((original_data >= r["min"]) & (original_data < r["max"]))
            )
            rgba[in_range, 3] = 0

    buf = io.BytesIO()
    PILImage.fromarray(rgba, "RGBA").save(buf, format="PNG")
    return buf.getvalue()
