"""Standalone FastAPI tile service for serving XYZ raster tiles from COGs.

Runs on the geo-worker container alongside the Celery worker (via supervisord).
Uses rio-tiler to read Cloud-Optimized GeoTIFFs and render 256x256 PNG tiles.

Endpoint: GET /tiles/{layer_id}/{z}/{x}/{y}.png
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Optional
import io
from functools import lru_cache

import numpy as np
import rasterio
from PIL import Image as PILImage
from pyproj import CRS
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject, transform_bounds

logger = logging.getLogger(__name__)
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response

from rio_tiler.io import Reader
from rio_tiler.errors import TileOutsideBounds

app = FastAPI(
    title="Geo Tile Service",
    description="XYZ tile server for DEM pipeline raster layers",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Default colormaps per layer type
# ---------------------------------------------------------------------------

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
    # terrain_class uses CATEGORICAL_COLORS (handled in separate branch)
    "terrain_class": "_categorical",
    "flow_dir": "spectral",
    "flood_risk": "rdylgn_r",
    "drainage_need": "ylorbr",
}

# Fixed rescale ranges per layer type for consistent visualization.
# Without these, rio-tiler auto-scales each tile independently,
# making flat terrain (e.g. Pampas with 30m range) look uniform.
# Tuned to Bell Ville area: 30m of relief over 30km, slopes < 1°.
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

# Direct class→RGBA mapping for categorical layers.
# Keys are the RAW uint8 values in the raster (no rescale needed).
CATEGORICAL_COLORS: dict[str, dict[int, tuple[int, int, int, int]]] = {
    "terrain_class": {
        0: (76, 175, 80, 180),      # Sin Riesgo — verde semi-transparente
        1: (30, 136, 229, 255),     # Drenaje Natural — azul medio
        2: (211, 47, 47, 255),      # Riesgo Alto — rojo
        3: (255, 143, 0, 255),      # Riesgo Medio — ámbar
    },
}

# Layer types that use categorical (discrete class) rendering
CATEGORICAL_TYPES = set(CATEGORICAL_COLORS.keys())

# ---------------------------------------------------------------------------
# Range configurations for continuous layers (toggleable value ranges)
# ---------------------------------------------------------------------------

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
        {"label": "Muy baja zona I (<0.5 m/1000m)", "min": 0, "max": 0.0265, "color": "#0b7d3b"},
        {"label": "Muy baja zona II (0.5-2.1 m/1000m)", "min": 0.0265, "max": 0.1227, "color": "#1a9850"},
        {"label": "Baja zona (2.1-4.2 m/1000m)", "min": 0.1227, "max": 0.2420, "color": "#91cf60"},
        {"label": "Suave zona (4.2-6.9 m/1000m)", "min": 0.2420, "max": 0.3964, "color": "#d9ef8b"},
        {"label": "Moderada zona (6.9-15.3 m/1000m)", "min": 0.3964, "max": 0.8754, "color": "#fc8d59"},
        {"label": "Alta puntual (>15.3 m/1000m)", "min": 0.8754, "max": 90.0, "color": "#d73027"},
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
        {"label": "Muy alto (>6.525)", "min": 6525.22, "max": 487848, "color": "#0c2c84"},
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

# Types that need log scaling (extreme skew: P50=2 but max=500k)
LOG_SCALE_TYPES = {"flow_acc"}

# Types that contain elevation data (valid for terrain-RGB encoding)
ELEVATION_TYPES = {"dem_raw"}

WEB_MERCATOR_CRS = CRS.from_epsg(3857)
WEB_MERCATOR_HALF_WORLD = 20037508.342789244


# ---------------------------------------------------------------------------
# Database access (lightweight — reuse existing session machinery)
# ---------------------------------------------------------------------------


def _get_layer(layer_id: uuid.UUID):
    """Fetch a GeoLayer record from the database."""
    from app.db.session import SessionLocal
    import app.auth.models  # noqa: F401 — register User for FK resolution
    from app.domains.geo.models import GeoLayer

    db = SessionLocal()
    try:
        from sqlalchemy import select

        stmt = select(GeoLayer).where(GeoLayer.id == layer_id)
        layer = db.execute(stmt).scalar_one_or_none()
        if layer:
            # Detach from session so we can use it after close
            db.expunge(layer)
        return layer
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Terrain-RGB encoding
# ---------------------------------------------------------------------------


def _encode_terrain_rgb(data: np.ndarray) -> np.ndarray:
    """Encode elevation values to Mapbox Terrain-RGB format.

    Formula: encoded = (elevation + 10000) * 10
    R = floor(encoded / 65536)
    G = floor((encoded % 65536) / 256)
    B = floor(encoded % 256)
    """
    # Clamp to valid range for terrain-RGB
    elevation = np.clip(data.astype(np.float64), -10000, 1667721.5)
    encoded = ((elevation + 10000.0) * 10.0).astype(np.uint32)

    r = (encoded // 65536).astype(np.uint8)
    g = ((encoded % 65536) // 256).astype(np.uint8)
    b = (encoded % 256).astype(np.uint8)

    return np.stack([r, g, b], axis=0)


@lru_cache(maxsize=32)
def _get_elevation_baseline(file_path: str) -> float:
    """Return the global minimum valid elevation for a DEM file.

    We use this as the terrain baseline so the lowest DEM point stays at 0 m
    in the 3D viewer, even when MapLibre exaggeration is applied.
    """
    with rasterio.open(file_path) as src:
        band = src.read(1, masked=True)
        if band.count() == 0:
            return 0.0
        return float(band.min())


def _tile_bounds_3857(x: int, y: int, z: int) -> tuple[float, float, float, float]:
    """Return XYZ tile bounds in EPSG:3857."""
    world_span = WEB_MERCATOR_HALF_WORLD * 2.0
    tile_span = world_span / (2**z)
    left = -WEB_MERCATOR_HALF_WORLD + (x * tile_span)
    right = left + tile_span
    top = WEB_MERCATOR_HALF_WORLD - (y * tile_span)
    bottom = top - tile_span
    return left, bottom, right, top


def _bounds_intersect(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> bool:
    """Return True when two bounding boxes intersect."""
    a_left, a_bottom, a_right, a_top = a
    b_left, b_bottom, b_right, b_top = b
    return not (
        a_right <= b_left
        or a_left >= b_right
        or a_top <= b_bottom
        or a_bottom >= b_top
    )


def _read_categorical_tile(
    file_path: str | Path,
    x: int,
    y: int,
    z: int,
    *,
    tilesize: int = 256,
    dst_nodata: int = 255,
) -> tuple[np.ndarray, np.ndarray] | None:
    """Read a categorical tile with rasterio + nearest-neighbor reprojection.

    This bypasses rio-tiler for categorical rasters so raw class ids survive
    unchanged during reprojection from the source CRS into Web Mercator tiles.
    """
    tile_bounds = _tile_bounds_3857(x, y, z)
    dst_transform = from_bounds(*tile_bounds, width=tilesize, height=tilesize)

    with rasterio.open(file_path) as src:
        src_bounds_3857 = transform_bounds(src.crs, WEB_MERCATOR_CRS, *src.bounds)
        if not _bounds_intersect(tile_bounds, src_bounds_3857):
            return None

        src_nodata = src.nodata
        if src_nodata is None:
            src_nodata = dst_nodata

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


def _render_categorical_png(
    raw: np.ndarray,
    mask: np.ndarray,
    colors: dict[int, tuple[int, int, int, int]],
    hidden_classes: Optional[set[int]] = None,
) -> bytes:
    """Render a categorical tile as RGBA PNG from raw class ids."""
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


def _read_elevation_tile(
    file_path: str | Path,
    x: int,
    y: int,
    z: int,
    *,
    tilesize: int = 256,
) -> tuple[np.ndarray, np.ndarray] | None:
    """Read an elevation tile with rasterio reprojection into Web Mercator.

    This bypasses rio-tiler for terrain-rgb output so the final DEM PNGs have a
    deterministic size and resampling path across all neighboring tiles.
    """
    tile_bounds = _tile_bounds_3857(x, y, z)
    dst_transform = from_bounds(*tile_bounds, width=tilesize, height=tilesize)

    with rasterio.open(file_path) as src:
        src_bounds_3857 = transform_bounds(src.crs, WEB_MERCATOR_CRS, *src.bounds)
        if not _bounds_intersect(tile_bounds, src_bounds_3857):
            return None

        tile = np.full((tilesize, tilesize), np.nan, dtype=np.float32)
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

    mask = np.isfinite(tile)
    return tile, mask


def _render_terrain_rgb_png(data: np.ndarray, valid_mask: np.ndarray) -> bytes:
    """Render a terrain-rgb PNG directly from elevation values."""
    if not np.any(valid_mask):
        raise ValueError("No valid elevation pixels to render")

    terrain_rgb = _encode_terrain_rgb(np.where(valid_mask, data, 0.0))

    rgb = np.zeros((data.shape[0], data.shape[1], 3), dtype=np.uint8)
    rgb[..., 0] = terrain_rgb[0]
    rgb[..., 1] = terrain_rgb[1]
    rgb[..., 2] = terrain_rgb[2]

    buf = io.BytesIO()
    PILImage.fromarray(rgb, "RGB").save(buf, format="PNG")
    return buf.getvalue()


def _render_flat_terrain_rgb_png(*, tilesize: int = 256, elevation: float = 0.0) -> bytes:
    """Render a constant-elevation terrain-rgb PNG.

    Returning a real DEM tile instead of HTTP 204 keeps the raster-dem source
    structurally consistent at the edges of the clipped DEM.
    """
    data = np.full((tilesize, tilesize), elevation, dtype=np.float32)
    valid_mask = np.ones((tilesize, tilesize), dtype=bool)
    return _render_terrain_rgb_png(data, valid_mask)


def _render_continuous_with_ranges(
    img,
    layer_tipo: str,
    cmap_name: str,
    hidden_ranges: set[int],
) -> bytes:
    """Render a continuous tile as RGBA PNG, hiding specified value ranges.

    Uses manual PIL rendering (like categorical) because rio-tiler's render()
    ignores mask changes for colormap-based rendering.

    Steps:
    1. Capture original (pre-rescale) data for range comparison
    2. Rescale data to 0-255
    3. Apply colormap from rio-tiler registry
    4. Build RGBA manually
    5. Apply nodata mask
    6. Apply hidden ranges (set alpha to 0)
    """
    from rio_tiler.colormap import cmap as colormap_registry

    # 1. Capture original values before rescale (first band)
    original_data = img.data[0].astype(np.float64).copy()
    nodata_mask = img.mask  # 0 = nodata, 255 = valid

    # 2. Apply log scale or rescale
    if layer_tipo in LOG_SCALE_TYPES:
        img.data[:] = np.where(
            img.data > 0,
            np.log1p(img.data.astype(np.float64)).astype(np.float32),
            0,
        )
        img.rescale(((0.0, 13.0),))
    else:
        rescale = DEFAULT_RESCALE.get(layer_tipo)
        if rescale:
            img.rescale(((rescale[0], rescale[1]),))

    # 3. Get the 256-entry colormap dict from rio-tiler registry
    cmap_data = colormap_registry.get(cmap_name)

    # 4. Clamp rescaled data to 0-255 and build RGBA
    #    Only color pixels that are VALID (mask > 0) to avoid coloring
    #    out-of-bounds areas that should remain transparent.
    rescaled = np.clip(img.data[0], 0, 255).astype(np.uint8)
    h, w = rescaled.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    valid_px = nodata_mask > 0

    for val in range(256):
        px = (rescaled == val) & valid_px
        if px.any():
            color = cmap_data.get(val, (0, 0, 0, 255))
            rgba[px] = color

    # 5. Apply hidden ranges — set alpha to 0 for pixels in hidden value ranges
    range_cfg = RANGE_CONFIGS.get(layer_tipo, [])
    for idx in hidden_ranges:
        if idx < len(range_cfg):
            r = range_cfg[idx]
            is_last_range = idx == len(range_cfg) - 1
            if is_last_range:
                in_range = original_data >= r["min"]
            else:
                in_range = (original_data >= r["min"]) & (original_data < r["max"])
            rgba[in_range, 3] = 0

    buf = io.BytesIO()
    PILImage.fromarray(rgba, "RGBA").save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Tile endpoint
# ---------------------------------------------------------------------------


@app.get("/tiles/{layer_id}/{z}/{x}/{y}.png")
def get_tile(
    layer_id: uuid.UUID,
    z: int,
    x: int,
    y: int,
    colormap: Optional[str] = Query(
        default=None,
        description="Colormap name (e.g. viridis, terrain, RdYlGn_r)",
    ),
    encoding: Optional[str] = Query(
        default=None,
        description="Tile encoding: 'terrain-rgb' for Mapbox elevation encoding",
    ),
    hide_classes: Optional[str] = Query(
        default=None,
        description="Comma-separated class values to hide (e.g. '1,3'). "
        "Only applies to categorical layers like terrain_class.",
    ),
    hide_ranges: Optional[str] = Query(
        default=None,
        description="Comma-separated range indices to hide (e.g. '0,2'). "
        "Only applies to continuous layers with RANGE_CONFIGS.",
    ),
):
    """Serve a 256x256 PNG tile from a GeoLayer's raster data.

    Returns 204 for tiles outside the layer's bounds (empty tiles).
    """
    layer = _get_layer(layer_id)
    if layer is None:
        raise HTTPException(status_code=404, detail="Geo layer no encontrado")

    # Resolve the file path — prefer COG if available
    cog_path = None
    if layer.metadata_extra and isinstance(layer.metadata_extra, dict):
        cog_path = layer.metadata_extra.get("cog_path")

    file_path = cog_path or layer.archivo_path
    if not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado en disco")

    # Validate terrain-RGB encoding is only for elevation layers
    if encoding == "terrain-rgb" and layer.tipo not in ELEVATION_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Terrain-RGB encoding solo disponible para capas de elevacion (tipo={layer.tipo})",
        )

    # Parse hidden classes (used later for categorical rendering)
    _hidden_classes: set[int] = set()
    if hide_classes:
        try:
            _hidden_classes = {int(c.strip()) for c in hide_classes.split(",") if c.strip()}
        except ValueError:
            logger.warning("Invalid hide_classes value: %s", hide_classes)

    # Parse hidden ranges (used for continuous layers with RANGE_CONFIGS)
    _hidden_ranges: set[int] = set()
    if hide_ranges:
        try:
            _hidden_ranges = {int(r.strip()) for r in hide_ranges.split(",") if r.strip()}
        except ValueError:
            logger.warning("Invalid hide_ranges value: %s", hide_ranges)

    if encoding == "terrain-rgb":
        tile_data = _read_elevation_tile(file_path, x, y, z, tilesize=256)
        if tile_data is None:
            content = _render_flat_terrain_rgb_png(tilesize=256, elevation=0.0)
            return Response(content=content, media_type="image/png")

        elevation, valid_mask = tile_data
        baseline = _get_elevation_baseline(str(file_path))
        normalized_elevation = np.where(valid_mask, elevation - baseline, 0.0)
        try:
            content = _render_terrain_rgb_png(normalized_elevation, valid_mask)
        except ValueError:
            content = _render_flat_terrain_rgb_png(tilesize=256, elevation=0.0)
    elif layer.tipo in CATEGORICAL_TYPES:
        tile_data = _read_categorical_tile(file_path, x, y, z, tilesize=256)
        if tile_data is None:
            return Response(status_code=204)

        raw, mask = tile_data
        content = _render_categorical_png(
            raw,
            mask,
            CATEGORICAL_COLORS[layer.tipo],
            _hidden_classes,
        )
    else:
        try:
            with Reader(file_path) as src:
                img = src.tile(x, y, z, tilesize=256)
        except TileOutsideBounds:
            return Response(status_code=204)

    if encoding != "terrain-rgb" and layer.tipo not in CATEGORICAL_TYPES:
        cmap_name = colormap or DEFAULT_COLORMAPS.get(layer.tipo, "viridis")

        # If hiding ranges on a continuous layer, use manual PIL rendering
        if _hidden_ranges and layer.tipo in RANGE_CONFIGS:
            try:
                content = _render_continuous_with_ranges(
                    img, layer.tipo, cmap_name, _hidden_ranges,
                )
            except Exception as e:
                logger.warning(
                    "Error rendering with hidden ranges, falling back to standard: %s", e,
                )
                content = img.render(img_format="PNG")
        else:
            # ── Standard continuous rendering: rescale + rio-tiler colormap ──
            if layer.tipo in LOG_SCALE_TYPES:
                img.data[:] = np.where(
                    img.data > 0,
                    np.log1p(img.data.astype(np.float64)).astype(np.float32),
                    0,
                )
                img.rescale(((0.0, 13.0),))
            else:
                rescale = DEFAULT_RESCALE.get(layer.tipo)
                if rescale:
                    img.rescale(((rescale[0], rescale[1]),))

            try:
                from rio_tiler.colormap import cmap as colormap_registry

                cmap_data = colormap_registry.get(cmap_name)
                content = img.render(img_format="PNG", colormap=cmap_data)
            except Exception as e:
                logger.warning(
                    "Colormap '%s' not found in rio-tiler registry, "
                    "falling back to grayscale: %s",
                    cmap_name,
                    e,
                )
                content = img.render(img_format="PNG")

    return Response(
        content=content,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=3600",
        },
    )


@app.get("/health")
def health():
    """Health check for the tile service."""
    return {"status": "ok", "service": "geo-tile-service"}
