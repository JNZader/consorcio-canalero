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
from fastapi import FastAPI, HTTPException, Path as PathParam, Query
from fastapi.responses import Response
from rio_tiler.io import Reader
from rio_tiler.errors import TileOutsideBounds
from app.domains.geo.rescale_policy import (
    rescale_cache_token,
    resolved_rescale,
)
from app.domains.geo.tile_service_support import (
    CATEGORICAL_COLORS,
    CATEGORICAL_TYPES,
    DEFAULT_COLORMAPS,
    DEFAULT_RESCALE,
    ELEVATION_TYPES,
    LOG_SCALE_TYPES,
    RANGE_CONFIGS,
    TERRAIN_SMOOTHING_BUFFER_PX,
    TERRAIN_SMOOTHING_METHODS_DESCRIPTION,
    crop_center as _crop_center,
    get_elevation_baseline as _get_elevation_baseline,
    read_categorical_tile as _read_categorical_tile,
    read_elevation_tile as _read_elevation_tile,
    render_categorical_png as _render_categorical_png,
    render_continuous_with_ranges as _render_continuous_with_ranges,
    render_flat_terrain_rgb_png as _render_flat_terrain_rgb_png,
    render_terrain_rgb_png as _render_terrain_rgb_png,
    smooth_elevation_tile as _smooth_elevation_tile,
    zona_clip_mask as _zona_clip_mask,
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
    # Same bound the public proxy enforces (``router_core.MAX_TILE_ZOOM`` — keep
    # the two numbers in sync). Duplicated on purpose: this service listens on
    # its own port inside the geo-worker, so it must not depend on an upstream
    # having validated ``z`` before ``tile_bounds_3857`` evaluates ``2 ** z``.
    z: int = PathParam(..., ge=0, le=22),
    x: int = PathParam(..., ge=0),
    y: int = PathParam(..., ge=0),
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
    terrain_smoothing: Optional[str] = Query(
        default=None,
        description=TERRAIN_SMOOTHING_METHODS_DESCRIPTION,
    ),
    rescale_min: Optional[float] = Query(
        default=None,
        description="Minimum value for the requested rescale range (continuous layers).",
    ),
    rescale_max: Optional[float] = Query(
        default=None,
        description="Maximum value for the requested rescale range (continuous layers).",
    ),
):
    """Serve a 256x256 PNG tile from a GeoLayer's raster data.

    Returns 204 for tiles outside the layer's bounds (empty tiles).
    """
    from app.core.cache import get_bytes_cache

    def _normalise_csv(value: Optional[str]) -> str:
        """Order-independent normalisation for set-style CSV params.

        ``hide_classes`` / ``hide_ranges`` are parsed as sets downstream, so
        ``"1,2"`` and ``"2,1"`` produce identical renders. Cache them under
        the same key by sorting before stringification.
        """
        if not value:
            return "-"
        parts = sorted({p.strip() for p in value.split(",") if p.strip()})
        return ",".join(parts) if parts else "-"

    # Build a cache key that fully describes the rendered output. Every
    # parameter that influences the bytes must appear here, otherwise we'd
    # serve a cached tile from a different request shape.
    # v2: visual (non terrain-rgb) tiles are clipped to the consorcio zona —
    # bump so pre-clip cached renders never get served.
    # v3: terrain-rgb nodata is feathered down to the baseline instead of being
    # snapped to it, so every previously cached elevation tile that straddles
    # the DEM edge still carries the vertical curtain. Bump to retire them.
    # v4: rescale_min/rescale_max allow monthly/annual CHIRPS normals to share
    # the same layer id with different contrast; previous keys ignored them.
    # v5 (hardening H1): the rescale portion is now a BOUNDED canonical token
    # ("m" / "a" / "-") instead of the raw attacker-controlled float, so the
    # cache-key cardinality is finite and an unbounded rescale range can never
    # be injected into the key. Retire v4 keys.
    cache_key = (
        f"v5:{layer_id}:{z}:{x}:{y}"
        f":enc={encoding or '-'}"
        f":cmap={colormap or '-'}"
        f":hc={_normalise_csv(hide_classes)}"
        f":hr={_normalise_csv(hide_ranges)}"
        f":smooth={terrain_smoothing or '-'}"
        f":r={rescale_cache_token(rescale_min, rescale_max)}"
    )
    bytes_cache = get_bytes_cache()
    cached = bytes_cache.get(cache_key)
    if cached is not None:
        return Response(
            content=cached,
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=3600",
                "X-Cache": "HIT",
            },
        )

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

    # A per-request rescale range lets the same continuous layer (e.g. CHIRPS
    # monthly vs annual normals) render with different contrast without creating
    # separate layer ids. Only a canonical, policy-approved pair is applied;
    # anything else (a single bound, an unsupported range, or a direct call
    # that bypassed the proxy) degrades to the layer's default rescale so the
    # existing default rendering is preserved and the cache key stays bounded.
    _requested_rescale: tuple[float, float] | None = resolved_rescale(
        layer.tipo, rescale_min, rescale_max
    )

    if encoding == "terrain-rgb":
        # Read with a buffer halo only when smoothing is requested, so that
        # the kernel filter sees the neighbouring tile's elevations and the
        # seam between tiles disappears. The halo is cropped before render.
        buffer_px = TERRAIN_SMOOTHING_BUFFER_PX if terrain_smoothing else 0
        tile_data = _read_elevation_tile(file_path, x, y, z, tilesize=256, buffer_px=buffer_px)
        if tile_data is None:
            content = _render_flat_terrain_rgb_png(tilesize=256, elevation=0.0)
            bytes_cache.set(cache_key, content, ttl_seconds=24 * 3600)
            return Response(
                content=content,
                media_type="image/png",
                headers={"Cache-Control": "public, max-age=3600", "X-Cache": "MISS"},
            )

        elevation, valid_mask = tile_data
        baseline = _get_elevation_baseline(str(file_path))
        # Invalid pixels get a 0.0 PLACEHOLDER here only so the smoothing
        # kernels see a finite array; the rendered value for them is decided by
        # ``feather_nodata_elevation`` inside ``render_terrain_rgb_png``, which
        # ramps them down to the baseline instead of snapping them to it.
        normalized_elevation = np.where(valid_mask, elevation - baseline, 0.0)
        normalized_elevation = _smooth_elevation_tile(
            normalized_elevation,
            valid_mask,
            terrain_smoothing,
        )
        # Crop the buffer halo back so the rendered tile is exactly 256×256.
        if buffer_px:
            normalized_elevation = _crop_center(normalized_elevation, buffer_px)
            valid_mask = _crop_center(valid_mask, buffer_px)
        try:
            content = _render_terrain_rgb_png(normalized_elevation, valid_mask)
        except ValueError:
            content = _render_flat_terrain_rgb_png(tilesize=256, elevation=0.0)
    elif layer.tipo in CATEGORICAL_TYPES:
        tile_data = _read_categorical_tile(file_path, x, y, z, tilesize=256)
        if tile_data is None:
            return Response(status_code=204)

        raw, mask = tile_data
        # Clip the visual overlay to the consorcio outline — the pipeline
        # rasters cover the whole processing bbox (terrain-rgb keeps its
        # full extent; only the painted overlay is clipped).
        zona_mask = _zona_clip_mask(x, y, z, tilesize=256)
        if zona_mask is not None:
            mask = mask & zona_mask
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
        zona_mask = _zona_clip_mask(x, y, z, tilesize=256)
        if zona_mask is not None:
            # rio-tiler ≥4 exposes ``mask`` as a COMPUTED property — item
            # assignment mutates a temporary and silently does nothing.
            # Rebuild the underlying masked array instead.
            arr = img.array
            hidden = np.broadcast_to(~zona_mask, arr.shape)
            img.array = np.ma.MaskedArray(arr.data, mask=np.ma.getmaskarray(arr) | hidden)

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
                    rescale=_requested_rescale,
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
                rescale = _requested_rescale or DEFAULT_RESCALE.get(layer.tipo)
                if rescale:
                    img.rescale(((rescale[0], rescale[1]),))

            try:
                from rio_tiler.colormap import cmap as colormap_registry

                cmap_data = colormap_registry.get(cmap_name)
                content = img.render(img_format="PNG", colormap=cmap_data)
            except Exception as e:
                logger.warning(
                    "Colormap '%s' not found in rio-tiler registry, falling back to grayscale: %s",
                    cmap_name,
                    e,
                )
                content = img.render(img_format="PNG")

    # Cache the rendered bytes for 24h — every tunable parameter is in the
    # key, so different requests for the same tile never collide.
    bytes_cache.set(cache_key, content, ttl_seconds=24 * 3600)
    return Response(
        content=content,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=3600",
            "X-Cache": "MISS",
        },
    )


@app.get("/health")
def health():
    """Health check for the tile service."""
    return {"status": "ok", "service": "geo-tile-service"}
