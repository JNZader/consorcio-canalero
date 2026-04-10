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
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from rio_tiler.io import Reader
from rio_tiler.errors import TileOutsideBounds
from app.domains.geo.tile_service_support import (
    CATEGORICAL_COLORS,
    CATEGORICAL_TYPES,
    DEFAULT_COLORMAPS,
    DEFAULT_RESCALE,
    ELEVATION_TYPES,
    LOG_SCALE_TYPES,
    RANGE_CONFIGS,
    get_elevation_baseline as _get_elevation_baseline,
    read_categorical_tile as _read_categorical_tile,
    read_elevation_tile as _read_elevation_tile,
    render_categorical_png as _render_categorical_png,
    render_continuous_with_ranges as _render_continuous_with_ranges,
    render_flat_terrain_rgb_png as _render_flat_terrain_rgb_png,
    render_terrain_rgb_png as _render_terrain_rgb_png,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Geo Tile Service",
    description="XYZ tile server for DEM pipeline raster layers",
    version="1.0.0",
)

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
            _hidden_classes = {
                int(c.strip()) for c in hide_classes.split(",") if c.strip()
            }
        except ValueError:
            logger.warning("Invalid hide_classes value: %s", hide_classes)

    # Parse hidden ranges (used for continuous layers with RANGE_CONFIGS)
    _hidden_ranges: set[int] = set()
    if hide_ranges:
        try:
            _hidden_ranges = {
                int(r.strip()) for r in hide_ranges.split(",") if r.strip()
            }
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
                    img,
                    layer.tipo,
                    cmap_name,
                    _hidden_ranges,
                )
            except Exception as e:
                logger.warning(
                    "Error rendering with hidden ranges, falling back to standard: %s",
                    e,
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
