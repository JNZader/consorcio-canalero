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
from scipy.ndimage import distance_transform_edt, median_filter

from app.domains.geo.class_breaks import RANGE_CONFIGS

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

# Width (in pixels) of the ramp that carries a terrain-rgb tile from the last
# valid elevation down to the baseline plane over the nodata area. See
# ``feather_nodata_elevation`` for why the ramp exists at all.
#
# CHOSEN, not measured. The arithmetic behind the choice: 24 px is 9.4 % of a
# 256 px tile, and at z15 (where the 3D terrain is actually read) a Web-Mercator
# pixel at the consorcio's latitude is 156543.03 * cos(32.6°) / 2**15 ≈ 4.0 m,
# so the ramp spans ~96 m on the ground — a slope, not a wall, against the tens
# of metres of relief in the DEM. The trade-off runs both ways: a wider ramp is
# gentler but pushes the skirt further past the DEM edge (and grows the residual
# seam described in ``feather_nodata_elevation``), a narrower one hugs the data
# but steepens each step. Safe to tune; it changes pixels only, never geometry
# semantics — but bump the tile cache key when you do.
TERRAIN_NODATA_FEATHER_PX = 24

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

# ``RANGE_CONFIGS`` lives in the leaf module ``class_breaks`` so the API process
# (ficha zonal profiles) can read the same class breaks the tiles are rendered
# with, without importing tile-rendering code. Re-exported here so existing
# importers of ``tile_service_support.RANGE_CONFIGS`` keep working unchanged.

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


def feather_nodata_elevation(
    data: np.ndarray,
    valid_mask: np.ndarray,
    feather_px: int = TERRAIN_NODATA_FEATHER_PX,
) -> np.ndarray:
    """Ramp the nodata area of a terrain tile down to the baseline plane.

    ``data`` is a BASELINE-NORMALIZED elevation tile (``elevation - baseline``),
    so ``0.0`` is the lowest elevation of the whole DEM. Terrain-RGB has no
    alpha channel: every pixel encodes an elevation, and the renderer used to
    hard-assign ``0.0`` to every invalid pixel. Because the interior is
    normalized against the baseline, that put the whole exterior at the DEM
    minimum and turned the edge of the recorte into a VERTICAL CURTAIN whose
    height is the local relief times the viewer's terrain exaggeration.

    The fix keeps the far field exactly where it was — ``0.0``, the same value
    ``render_flat_terrain_rgb_png`` uses for tiles that miss the DEM entirely,
    so no cross-tile discontinuity is introduced — and replaces the ABRUPT
    transition with a linear ramp: each invalid pixel takes the elevation of
    the nearest valid pixel attenuated by its distance to the data edge,
    reaching the baseline plane ``feather_px`` pixels out. The cliff becomes a
    skirt.

    Alternatives considered:

    * plain nearest-valid fill (no attenuation) — removes the cliff at the data
      edge but moves it to the border of the next tile, which has no valid
      pixel at all and stays flat at the baseline;
    * per-row/column edge extension — cheaper, but it smears the border
      elevation along the axes and produces visible cross-shaped artefacts on a
      diagonal DEM boundary;
    * re-normalizing the exterior to a different baseline — does not help: the
      step is the interior relief, not the choice of datum.

    Cost is one EDT over a 256x256 boolean (~0.5 ms) and only on tiles that
    actually straddle the DEM edge; fully valid tiles take the fast path and
    come out byte-identical to the previous renderer.

    Residual (documented on purpose): the ramp is computed per tile, so when
    the DEM edge runs closer than ``feather_px`` to the tile border, the
    neighbouring all-nodata tile is already flat at the baseline while this
    tile still ends part-way down the ramp. The remaining step is bounded by
    the ramp height rather than by the full relief — an order of magnitude
    smaller than the curtain it replaces.
    """
    if valid_mask.all():
        return data.astype(np.float32, copy=False)
    if not valid_mask.any():
        return np.zeros(data.shape, dtype=np.float32)

    distance, indices = distance_transform_edt(  # type: ignore[misc]
        ~valid_mask,
        return_distances=True,
        return_indices=True,
    )
    nearest = data[tuple(indices)]
    weight = np.clip(1.0 - (distance / float(feather_px)), 0.0, 1.0)
    return np.where(valid_mask, data, nearest * weight).astype(np.float32)


def render_terrain_rgb_png(data: np.ndarray, valid_mask: np.ndarray) -> bytes:
    if not np.any(valid_mask):
        raise ValueError("No valid elevation pixels to render")
    terrain_rgb = encode_terrain_rgb(feather_nodata_elevation(data, valid_mask))
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
