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
    "slope": (0.0, 1.5),
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
        0: (0, 0, 255, 255),       # Drenaje Natural — azul puro
        1: (255, 0, 0, 255),       # Zona Inundable — rojo puro
        2: (255, 165, 0, 255),     # Necesita Drenaje — naranja brillante
        3: (139, 90, 43, 255),     # Loma/Divisoria — marrón oscuro
        4: (200, 200, 200, 255),   # Terreno Funcional — gris claro
    },
}

# Layer types that use categorical (discrete class) rendering
CATEGORICAL_TYPES = set(CATEGORICAL_COLORS.keys())

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

    if layer.tipo in CATEGORICAL_TYPES:
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

    if encoding == "terrain-rgb":
        # Replace image data with terrain-RGB encoded elevation
        from rio_tiler.models import ImageData

        terrain_data = _encode_terrain_rgb(img.data[0])  # First band = elevation
        img = ImageData(terrain_data, img.mask)
        # Render without colormap for terrain-RGB
        content = img.render(img_format="PNG")
    elif layer.tipo not in CATEGORICAL_TYPES:
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

        cmap_name = colormap or DEFAULT_COLORMAPS.get(layer.tipo, "viridis")
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
