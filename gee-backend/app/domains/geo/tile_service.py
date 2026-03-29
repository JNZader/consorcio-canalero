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

import numpy as np

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
    "flow_acc": "ylgnbu",
    "hand": "ylorrd",
    "terrain_class": "set1",
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
    "hand": (0.0, 4.0),
    "terrain_class": (0.0, 3.0),
    "flow_dir": (0.0, 128.0),
    "flood_risk": (10.0, 90.0),
    "drainage_need": (20.0, 70.0),
}

# Types that need log scaling (extreme skew: P50=2 but max=500k)
LOG_SCALE_TYPES = {"flow_acc"}

# Types that contain elevation data (valid for terrain-RGB encoding)
ELEVATION_TYPES = {"dem_raw"}


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
    else:
        # Log-scale for extremely skewed data (flow accumulation)
        if layer.tipo in LOG_SCALE_TYPES:
            img.data[:] = np.where(
                img.data > 0,
                np.log1p(img.data.astype(np.float64)).astype(np.float32),
                0,
            )
            # Rescale log values: log1p(1)=0.7 to log1p(500000)=13.1
            img.rescale(((0.0, 13.0),))
        else:
            # Apply fixed rescale if defined (ensures consistent colors across tiles)
            rescale = DEFAULT_RESCALE.get(layer.tipo)
            if rescale:
                img.rescale(((rescale[0], rescale[1]),))

        # Resolve colormap
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
